#!/usr/bin/env python3
"""Fact-provenance search UI server — stdlib only, deployable anywhere.

  python3 serve.py --db provenance.db --port 8095

Routes
  /                     search UI (index.html)
  /api/search?q=&kind=&domain=&limit=&offset=
  /api/stats            index counts
  /api/claim/<id>       one claim as a PROV-O / JSON-LD record
  /healthz

Deliberately reads only: the database is opened read-only per request.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "provenance.db")
NS = {
    "prov": "http://www.w3.org/ns/prov#",
    "dct": "http://purl.org/dc/terms/",
    "schema": "https://schema.org/",
    "fp": "https://factprovenance.org/ns#",
}
FTS_SAFE = re.compile(r"[^\w\s\-'\"*]", re.UNICODE)


def fts_query(q: str) -> str:
    """Turn user input into a safe FTS5 MATCH expression (phrase + prefix)."""
    q = FTS_SAFE.sub(" ", q).strip()
    terms = [t for t in q.split() if t]
    if not terms:
        return ""
    quoted = [f'"{t}"' for t in terms[:-1]]
    return " ".join(quoted + [f'"{terms[-1]}"*'])


def connect():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)


FAVICON_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
               b'<rect width="64" height="64" fill="#0d1117"/>'
               b'<rect x="1" y="1" width="62" height="62" fill="none"'
               b' stroke="rgba(240,246,252,0.10)" stroke-width="2"/>'
               b'<path d="M18 34l10 10 20-24" stroke="#4a84fe" stroke-width="6"'
               b' fill="none" stroke-linecap="round"/></svg>')


def claim_html(rec: dict) -> str:
    """Human-readable view for a claim identifier. /claim/<id> dereferences for both
    audiences: browsers (Accept: text/html) get this page, data clients get JSON-LD."""
    from html import escape as e

    src = rec.get("prov:wasDerivedFrom") or {}
    cited = rec.get("fp:citedSource") or {}
    rows = [
        ("kind", ", ".join(rec.get("fp:claimKind") or []) or "—"),
        ("source page", str(src.get("@id") or "—")),
        ("page title", str(src.get("schema:name") or "—")),
        ("published", str(src.get("fp:publicationDate") or "—")),
        ("retrieved", str(src.get("fp:retrievedAt") or "—")),
        ("content digest", str(src.get("fp:contentDigest") or "—")),
        ("cited source", str(cited.get("@id") or "none recorded on the page")),
        ("verification", str(rec.get("fp:verificationStatus") or "unverified")),
    ]
    dl = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in rows)
    ident = e(str(rec.get("@id", "")))
    css = ("body{background:#0d1117;color:#e6edf3;margin:0;"
           "padding:32px 28px;font:15px/1.55 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;"
           "color-scheme:dark}"
           "*{box-sizing:border-box;border-radius:0}"
           "a{color:#4a84fe;text-decoration:none;border-bottom:1px solid rgba(74,132,254,.32)}"
           "a:hover{border-bottom-color:#4a84fe}"
           ".claim{font-size:17px;line-height:1.5;margin:1rem 0}"
           "h1{font:400 12px/1.4 ui-monospace,Menlo,monospace;color:#7d8590;letter-spacing:.04em;"
           "margin:0 0 1.4rem;padding-bottom:.6rem;border-bottom:1px solid rgba(240,246,252,.10)}"
           "h2{font:400 10.5px/1.4 ui-monospace,Menlo,monospace;text-transform:uppercase;"
           "letter-spacing:.09em;color:#7d8590;margin:2rem 0 .6rem;padding-bottom:.4rem;"
           "border-bottom:1px solid rgba(240,246,252,.055)}"
           "pre{background:#010409;border:1px solid rgba(240,246,252,.055);padding:.9rem;"
           "overflow:auto;font:11.5px/1.5 ui-monospace,Menlo,monospace;color:#c9d1d9}"
           "dl{display:grid;grid-template-columns:10rem 1fr;gap:.35rem 1rem;margin:1.2rem 0;"
           "font-size:13.5px}"
           "dt{font-family:ui-monospace,Menlo,monospace;font-size:11px;text-transform:uppercase;"
           "letter-spacing:.06em;color:#7d8590}"
           "dd{margin:0;overflow-wrap:anywhere}")
    return ('<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Claim {ident} — Fact Provenance</title>'
            f'<link rel="canonical" href="{ident}">'
            f'<link rel="alternate" type="application/ld+json" href="{ident}">'
            f'<style>{css}</style></head><body>'
            '<p><a href="/">← Fact Provenance index</a></p>'
            f'<h1>{ident}</h1>'
            f'<p class="claim">{e(str(rec.get("fp:claimText") or ""))}</p>'
            f'<dl>{dl}</dl>'
            '<h2>PROV-O record</h2>'
            f'<pre>{e(json.dumps(rec, ensure_ascii=False, indent=2))}</pre>'
            '</body></html>\n')


def prov_record(row) -> dict:
    (cid, text, kind, url, domain, title, pubdate, digest, cited, ctx, fetched) = row
    rec = {
        "@context": NS,
        "@id": f"https://factprovenance.org/claim/{cid}",
        "@type": ["prov:Entity", "fp:Claim"],
        "fp:claimText": text,
        "fp:claimKind": (kind or "").split(","),
        "fp:verificationStatus": "unverified",
        "fp:verificationNote": "Indexed from the published page. Quote-match against the "
                               "cited source has not been run yet.",
        "prov:wasDerivedFrom": {
            "@type": ["prov:Entity", "schema:CreativeWork"],
            "@id": url,
            "schema:name": title or None,
            "fp:publicationDate": pubdate or None,
            "fp:contentDigest": digest or None,
            "fp:retrievedAt": fetched,
        },
        "prov:wasGeneratedBy": {
            "@type": "prov:Activity",
            "fp:method": "regex-extract",
            "fp:agent": "hermes-owl",
        },
        "dct:created": fetched,
    }
    if cited:
        rec["fp:citedSource"] = {
            "@id": cited,
            "fp:citationKind": "as-published",
            "fp:note": "candidate pointer only — not verified by this index",
        }
    return rec


class Handler(BaseHTTPRequestHandler):
    server_version = "FactProvUI/0.1"

    def log_message(self, fmt, *args):
        pass  # quiet

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, indent=2).encode())

    def _file(self, path, ctype, code=200):
        """Serve a file from disk. Used for the internal strategy page."""
        try:
            with open(path, "rb") as fh:
                self._send(code, fh.read(), ctype)
        except FileNotFoundError:
            self._send(404, b"page not deployed", "text/plain; charset=utf-8")

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        path = u.path
        try:
            if path in ("/", "/index.html"):
                p = os.path.join(HERE, "index.html")
                self._send(200, open(p, "rb").read(), "text/html; charset=utf-8")
            elif path == "/healthz":
                self._json({"ok": True, "db": os.path.basename(DB)})
            elif path == "/api/stats":
                self._json(self.stats())
            elif path == "/api/search":
                self._json(self.search(qs))
            elif path.startswith("/claim/"):
                # the PROV-O identifier: HTML for browsers, JSON-LD for data clients
                rec = self.claim(path.rsplit("/", 1)[-1])
                if rec.get("error"):
                    self._json(rec, 404)
                elif "text/html" in (self.headers.get("Accept") or ""):
                    self._send(200, claim_html(rec).encode(), "text/html; charset=utf-8")
                else:
                    self._send(200, json.dumps(rec, ensure_ascii=False, indent=2).encode(),
                               "application/ld+json")
            elif path.startswith("/api/claim/"):
                self._json(self.claim(path.rsplit("/", 1)[-1]))
            elif path == "/api/domains":
                self._json(self.domains())
            elif path == "/favicon.ico":
                self._send(200, FAVICON_SVG, "image/svg+xml")
            elif path in ("/plan", "/plan/", "/stratplan"):
                # internal strategy document — not part of the public build
                self._file(os.path.join(HERE, "stratplan.html"), "text/html; charset=utf-8")
            elif path.startswith("/api/"):
                self._json({"error": "not found", "path": path}, 404)
            else:
                # Every other path (bookmarks, /search?q=..., typos) lands on the UI
                # instead of a bare 404. API paths stay strictly 404.
                p = os.path.join(HERE, "index.html")
                self._send(200, open(p, "rb").read(), "text/html; charset=utf-8")
        except Exception as e:  # never 500-spam the log
            self._json({"error": str(e)[:200]}, 500)

    def stats(self):
        con = connect()
        c = con.execute
        return {
            "claims": c("SELECT count(*) FROM claims").fetchone()[0],
            "domains": c("SELECT count(DISTINCT domain) FROM claims").fetchone()[0],
            "with_cited_source": c("SELECT count(*) FROM claims WHERE cited_url IS NOT NULL AND cited_url<>''").fetchone()[0],
            "pages_ok": c("SELECT count(DISTINCT url) FROM claims").fetchone()[0],
            "by_kind": dict(c("SELECT kind, count(*) FROM claims GROUP BY kind ORDER BY 2 DESC LIMIT 12").fetchall()),
            "by_domain": c("SELECT domain, count(*) FROM claims GROUP BY domain ORDER BY 2 DESC LIMIT 12").fetchall(),
            "last_fetch": (c("SELECT max(fetched_at) FROM claims").fetchone() or [None])[0],
        }

    def domains(self):
        con = connect()
        rows = con.execute("SELECT domain, count(*) c FROM claims GROUP BY domain ORDER BY c DESC"
                           ).fetchall()
        return {"domains": [{"domain": d, "claims": n} for d, n in rows]}

    def search(self, qs):
        q = (qs.get("q") or [""])[0]
        kind = (qs.get("kind") or [""])[0]
        domain = (qs.get("domain") or [""])[0]
        limit = min(int((qs.get("limit") or ["25"])[0]), 100)
        offset = max(int((qs.get("offset") or ["0"])[0]), 0)
        where, args = [], []
        if kind:
            where.append("(',' || c.kind || ',') LIKE ?")
            args.append(f"%,{kind},%")
        if domain:
            where.append("c.domain = ?")
            args.append(domain)
        con = connect()
        con.row_factory = sqlite3.Row
        match = fts_query(q)
        if match:
            sql = ("SELECT c.*, bm25(claims_fts) AS score FROM claims_fts f "
                   "JOIN claims c ON c.id = f.rowid WHERE claims_fts MATCH ?")
            args = [match] + args
        else:
            sql = "SELECT c.*, 0 AS score FROM claims c WHERE 1=1"
        if where:
            sql += " AND " + " AND ".join(where)
        sql += " ORDER BY score, c.pubdate DESC LIMIT ? OFFSET ?"
        rows = con.execute(sql, args + [limit, offset]).fetchall()
        total = con.execute(
            "SELECT count(*) FROM claims_fts f JOIN claims c ON c.id=f.rowid "
            + ("WHERE claims_fts MATCH ?" if match else "WHERE 1=1")
            + (" AND " + " AND ".join(where) if where else ""),
            ([match] if match else []) + args[1:] if match else args).fetchone()[0]
        return {"query": q, "match": match, "kind": kind, "domain": domain,
                "total": total, "limit": limit, "offset": offset,
                "results": [{
                    "id": r["id"], "text": r["text"], "kind": r["kind"], "domain": r["domain"],
                    "url": r["url"], "title": r["title"], "pubdate": r["pubdate"],
                    "cited_url": r["cited_url"], "score": r["score"],
                    "prov_url": f"/api/claim/{r['id']}",
                } for r in rows]}

    def claim(self, cid):
        if not cid.isdigit():
            return {"error": "bad id"}
        con = connect()
        row = con.execute("SELECT id,text,kind,url,domain,title,pubdate,digest,cited_url,context,fetched_at"
                          " FROM claims WHERE id=?", (int(cid),)).fetchone()
        if not row:
            return {"error": "not found", "id": cid}
        return prov_record(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--port", type=int, default=8095)
    ap.add_argument("--host", default="0.0.0.0")
    a = ap.parse_args()
    globals()["DB"] = a.db
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(json.dumps({"serving": f"http://{a.host}:{a.port}", "db": DB}, indent=2), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
