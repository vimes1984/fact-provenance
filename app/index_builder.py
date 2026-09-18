#!/usr/bin/env python3
"""Build the fact-provenance search index (SQLite FTS5) from REAL pages.

Prototype for the "search the provenance facts" surface. Two inputs:

  --urls FILE   one URL per line -> polite live fetch, claim extraction
  --warc-csv F  rows from claim_probe.py (bulk Common Crawl mode)

For every claim we store: the claim sentence, its kind(s), the page it came from,
the page digest, publication date where declared, and — where the page itself
cites a source adjacent to the sentence (Wikipedia reference anchors) — the cited
URL. The cited URL is the page's own citation, NOT a verification; the UI labels
it as such.

Stdlib only. Reuses the claim taxonomy from ../claim_probe.py.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import urllib.robotparser
import gzip

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "FactProvenanceBot/0.1 (+prototype; contact: open an issue in this repository)"

# Same taxonomy as claim_probe.py, as str patterns for extracted text.
CLAIM_RX = {
    "quantity": re.compile(r"\b\d[\d,]*\.?\d*\s?(?:%|per cent|percent|million|billion|bn|trillion|thousand)\b", re.I),
    "measure": re.compile(r"\b\d[\d,]*\.?\d*\s?(?:kg|km|metres?|meters?|tonnes?|MW\b|GW\b|kWh|Mbps|°C|degrees|hectares?|acres?)\b", re.I),
    "dateclaim": re.compile(r"\b(?:in|since|by|as of|until|from)\s(?:1[6-9]|20)\d{2}\b", re.I),
    "attrib": re.compile(r"\b(?:according to|reported by|data from|per the|a study (?:by|published)|research(?:ers)? (?:at|by|from)|the report)\b", re.I),
    "superl": re.compile(r"\bthe (?:first|largest|biggest|highest|lowest|only|most|longest|smallest|fastest)\b", re.I),
}

REF_RE = re.compile(r"(?is)<sup[^>]*class=\"[^\"]*reference[^\"]*\"[^>]*>.*?</sup>")
DROP_RE = re.compile(r"(?is)<(script|style|noscript|svg|iframe)[^>]*>.*?</\1>")
BLOCK_RE = re.compile(r"(?is)<(p|div|li|h[1-6]|tr|br|section|td)\b[^>]*>")
TAG_RE = re.compile(r"(?s)<[^>]+>")
SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
REFM = re.compile(r"\[\[REF:([^\]]*)\]\]")
META_DATE = [
    re.compile(r'(?is)<meta[^>]+property="(?:article:published_time|og:updated_time|article:modified_time)"[^>]+content="([^"]+)"'),
    re.compile(r'(?is)<meta[^>]+name="(?:date|pubdate|publish-date|dc.date)"[^>]+content="([^"]+)"'),
    re.compile(r'(?is)<time[^>]+datetime="([^"]+)"'),
]
TITLE_RE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")


def fetch(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-IE,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(6_000_000)
        ctype = r.headers.get("Content-Type", "")
    return raw, ctype


_ROBOTS: dict[str, urllib.robotparser.RobotFileParser] = {}


def robots_ok(url: str) -> bool:
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    rp = _ROBOTS.get(base)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(base + "/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None  # unreachable robots => treat as allowed, log it
        _ROBOTS[base] = rp
    if rp is None:
        return True
    try:
        return rp.can_fetch(UA, url)
    except Exception:
        return True


def latest_crawl(fallback: str) -> str:
    """Newest Common Crawl release id. The archive gains a crawl roughly monthly;
    pinning an id means the nightly job silently stops finding new pages."""
    try:
        raw, _ = fetch("https://index.commoncrawl.org/collinfo.json")
        ids = [c["id"] for c in json.loads(raw.decode("utf-8", "replace")) if c.get("id")]
        if ids:
            return ids[0]
    except Exception as exc:
        print(f"[crawl] collinfo lookup failed ({exc}); falling back to {fallback}")
    return fallback


def cc_index_lookup(domain: str, crawl: str, limit: int = 40):
    """Ask the Common Crawl index for pages of a domain. Reading CC's archive is
    what the lead-gen rail already does — no live crawl, no robots problem."""
    q = urllib.parse.quote(f"{domain}/*", safe="")
    url = (f"https://index.commoncrawl.org/{crawl}-index?url={q}"
           f"&output=json&limit={limit}&filter=status:200&filter=mime:text/html")
    raw, _ = fetch(url)
    out = []
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def cc_get_record(rec: dict) -> bytes:
    """Range-fetch one gzip'd WARC record out of the CC archive."""
    off = int(rec["offset"])
    ln = int(rec["length"])
    req = urllib.request.Request(f"https://data.commoncrawl.org/{rec['filename']}",
                                headers={"User-Agent": UA, "Range": f"bytes={off}-{off + ln - 1}"})
    with urllib.request.urlopen(req, timeout=40) as r:
        blob = r.read()
    body = gzip.decompress(blob) if blob[:2] == b"\x1f\x8b" else blob
    hdr_end = body.find(b"\r\n\r\n")
    if hdr_end < 0:
        return body
    payload = body[hdr_end + 4:]
    if payload[:5] == b"HTTP/":
        p2 = payload.find(b"\r\n\r\n")
        if p2 >= 0:
            payload = payload[p2 + 4:]
    return payload


def to_text_with_refs(h: str) -> str:
    """HTML -> text, keeping <sup class=reference> hrefs as [[REF:url]] markers."""
    def marker(m):
        href = re.search(r'href="([^"]+)"', m.group(0))
        return f" [[REF:{html.unescape(href.group(1))}]]" if href else " [[REF:]]"
    h = REF_RE.sub(marker, h)
    h = DROP_RE.sub(" ", h)
    h = BLOCK_RE.sub("\n", h)
    h = TAG_RE.sub(" ", h)
    h = html.unescape(h)
    h = re.sub(r"[ \t\xa0]+", " ", h)
    h = re.sub(r"\n\s*\n+", "\n", h)
    return h


def meta_date(h: str):
    for rx in META_DATE:
        m = rx.search(h)
        if m:
            raw = m.group(1).strip()
            if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
                return raw[:10]
    return None


def claims_from_page(raw: bytes, url: str, max_claims: int = 300):
    h = raw.decode("utf-8", "replace")
    title = ""
    m = TITLE_RE.search(h)
    if m:
        title = re.sub(r"\s+", " ", html.unescape(TAG_RE.sub("", m.group(1)))).strip()[:180]
    date = meta_date(h)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    txt = to_text_with_refs(h)
    out = []
    for block in txt.split("\n"):
        block = block.strip()
        if len(block) < 80 or len(block) > 6000:
            continue
        sents = SENT_RE.split(block)
        for i, s in enumerate(sents):
            s = s.strip()
            if not (45 <= len(s) <= 420):
                continue
            kinds = [k for k, rx in CLAIM_RX.items() if rx.search(s)]
            if not kinds:
                continue
            cited = None
            nxt = sents[i + 1] if i + 1 < len(sents) else ""
            for cand in (s, nxt):
                rm = REFM.search(cand)
                if rm:
                    cited = rm.group(1) or None
                    break
            clean = re.sub(r"\s+", " ", REFM.sub("", s)).strip()
            if not clean:
                continue
            ctx = re.sub(r"\s+", " ", REFM.sub("", block))[:600]
            out.append({
                "text": clean, "kind": ",".join(kinds), "url": url,
                "domain": urllib.parse.urlparse(url).netloc,
                "title": title, "pubdate": date, "digest": digest,
                "cited_url": cited, "context": ctx,
            })
            if len(out) >= max_claims:
                return out
    return out


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS claims (
  id INTEGER PRIMARY KEY,
  text TEXT NOT NULL, kind TEXT, url TEXT, domain TEXT, title TEXT,
  pubdate TEXT, digest TEXT, cited_url TEXT, context TEXT, fetched_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS claims_uniq ON claims(digest, text);
CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5(
  text, title, content='claims', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS claims_ai AFTER INSERT ON claims BEGIN
  INSERT INTO claims_fts(rowid, text, title) VALUES (new.id, new.text, new.title);
END;
CREATE TABLE IF NOT EXISTS pages (
  url TEXT PRIMARY KEY, domain TEXT, status TEXT, http TEXT, claims INTEGER,
  title TEXT, pubdate TEXT, fetched_at TEXT, note TEXT
);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls")
    ap.add_argument("--cc-domains", help="file of domains to mine from the Common Crawl archive")
    ap.add_argument("--crawl", default="auto",
                    help="'auto' = newest Common Crawl release (recommended) or pin e.g. CC-MAIN-2026-34")
    ap.add_argument("--cc-limit", type=int, default=25)
    ap.add_argument("--warc-csv")
    ap.add_argument("--db", default=os.path.join(HERE, "provenance.db"))
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--max-pages", type=int, default=200)
    a = ap.parse_args()
    if a.crawl == "auto":
        a.crawl = latest_crawl("CC-MAIN-2026-34")
        print(f"[crawl] auto-resolved newest Common Crawl release -> {a.crawl}")

    con = sqlite3.connect(a.db)
    con.executescript(SCHEMA)
    added = pages_ok = 0
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if a.urls:
        urls = [u.strip() for u in open(a.urls) if u.strip() and not u.startswith("#")]
        for url in urls[: a.max_pages]:
            if not robots_ok(url):
                con.execute("INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?,?,?,?)",
                            (url, urllib.parse.urlparse(url).netloc, "blocked", "", 0, "", "", now, "robots.txt disallow"))
                print(f"ROBOTS  {url}", flush=True)
                continue
            try:
                raw, ctype = fetch(url)
                if "html" not in ctype.lower():
                    raise ValueError(f"not html: {ctype}")
                rows = claims_from_page(raw, url)
            except Exception as e:
                con.execute("INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?,?,?,?)",
                            (url, urllib.parse.urlparse(url).netloc, "error", "", 0, "", "", now, str(e)[:160]))
                print(f"ERROR   {url} :: {e}", flush=True)
                time.sleep(a.delay)
                continue
            for r in rows:
                try:
                    con.execute(
                        "INSERT OR IGNORE INTO claims (text,kind,url,domain,title,pubdate,digest,cited_url,context,fetched_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (r["text"], r["kind"], r["url"], r["domain"], r["title"], r["pubdate"],
                         r["digest"], r["cited_url"], r["context"], now))
                    added += 1
                except sqlite3.IntegrityError:
                    pass
            cited = sum(1 for r in rows if r["cited_url"])
            pages_ok += 1
            con.execute("INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?,?,?,?)",
                        (url, r["domain"] if rows else urllib.parse.urlparse(url).netloc, "ok", "",
                         len(rows), rows[0]["title"] if rows else "", rows[0]["pubdate"] if rows else "", now,
                         f"cited={cited}"))
            print(f"OK      {len(rows):4d} claims (cited {cited:3d})  {url}", flush=True)
            con.commit()
            time.sleep(a.delay)

    if a.cc_domains:
        doms = [d.strip() for d in open(a.cc_domains) if d.strip() and not d.startswith("#")]
        for dom in doms:
            try:
                recs = cc_index_lookup(dom, a.crawl, a.cc_limit)
            except Exception as e:
                print(f"CC-ERR  {dom} :: {e}", flush=True)
                continue
            got = 0
            for rec in recs[: a.cc_limit]:
                url = rec.get("url", "")
                try:
                    payload = cc_get_record(rec)
                    rows = claims_from_page(payload, url)
                except Exception as e:
                    print(f"CC-page-err {url} :: {str(e)[:90]}", flush=True)
                    continue
                ts = rec.get("timestamp", "")
                pdate = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 else None
                for r in rows:
                    r["pubdate"] = r["pubdate"] or pdate
                    try:
                        con.execute(
                            "INSERT OR IGNORE INTO claims (text,kind,url,domain,title,pubdate,digest,cited_url,context,fetched_at)"
                            " VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (r["text"], r["kind"], r["url"], r["domain"], r["title"], r["pubdate"],
                             r["digest"], r["cited_url"], r["context"], now))
                        added += 1
                    except sqlite3.IntegrityError:
                        pass
                got += 1
                pages_ok += 1
                con.execute("INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?,?,?,?)",
                            (url, r["domain"] if rows else urllib.parse.urlparse(url).netloc, "ok", "",
                             len(rows), rows[0]["title"] if rows else "", pdate or "", now,
                             f"cc:{a.crawl} cited={sum(1 for x in rows if x['cited_url'])}"))
                con.commit()
            print(f"CC-OK   {dom:34s} pages={got:3d}", flush=True)

    if a.warc_csv:
        with open(a.warc_csv) as f:
            for row in csv.DictReader(f):
                try:
                    con.execute(
                        "INSERT OR IGNORE INTO claims (text,kind,url,domain,title,pubdate,digest,cited_url,context,fetched_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (row.get("claim", ""), row.get("kinds", ""), row.get("url", ""), row.get("domain", ""),
                         row.get("url", ""), row.get("first_claim", "") or "", "", "", "", now))
                    added += 1
                except sqlite3.IntegrityError:
                    pass
        con.commit()

    con.commit()
    n = con.execute("SELECT count(*) FROM claims").fetchone()[0]
    ncited = con.execute("SELECT count(*) FROM claims WHERE cited_url IS NOT NULL AND cited_url<>''").fetchone()[0]
    ndom = con.execute("SELECT count(DISTINCT domain) FROM claims").fetchone()[0]
    print(json.dumps({"db": a.db, "claims": n, "with_cited_source": ncited,
                      "domains": ndom, "pages_ok": pages_ok, "inserted_this_run": added}, indent=2))


if __name__ == "__main__":
    main()
