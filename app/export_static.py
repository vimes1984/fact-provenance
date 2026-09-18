#!/usr/bin/env python3
"""Export the provenance search UI as ONE self-contained HTML file (no backend).

  python3 export_static.py --db provenance.db --out dist/fact-provenance.html

Why: this is the static-host shape (object storage, Pages, any CDN). Same index.html UI, but a shim is
injected *before* the page's script that answers /api/stats, /api/search and
/api/claim/<id> from an embedded copy of the index. Nothing is rewritten, so the
static build can never drift from the live UI.
"""
import argparse
import json
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))

SHIM = r"""
<script>
/* static-build data layer: answers the three /api routes from embedded data */
const __FP = %s;
window.fetch = async function (url) {
  const u = String(url);
  const J = (o) => ({ ok: true, status: 200, json: async () => o });
  if (u.indexOf("/api/stats") === 0) return J(__FP.stats);
  if (u.indexOf("/api/domains") === 0) return J({ domains: __FP.domains });
  if (u.indexOf("/api/search") === 0) {
    const qs = new URLSearchParams(u.split("?")[1] || "");
    const q = (qs.get("q") || "").trim().toLowerCase();
    const kind = qs.get("kind") || "";
    const domain = qs.get("domain") || "";
    const limit = parseInt(qs.get("limit") || "25", 10);
    const offset = parseInt(qs.get("offset") || "0", 10);
    const terms = q.split(/\s+/).filter(Boolean);
    let rows = __FP.claims;
    if (terms.length) rows = rows.filter((c) => { const t = c.text.toLowerCase(); return terms.every((w) => t.indexOf(w) >= 0); });
    if (kind) rows = rows.filter((c) => (c.kind || "").split(",").indexOf(kind) >= 0);
    if (domain) rows = rows.filter((c) => c.domain === domain);
    const total = rows.length;
    const page = rows.slice(offset, offset + limit).map((c) => Object.assign({}, c, {
      score: 0, prov_url: "/api/claim/" + c.id,
    }));
    return J({ query: q, kind: kind, domain: domain, total: total, limit: limit, offset: offset, results: page });
  }
  if (u.indexOf("/api/claim/") === 0) {
    const id = parseInt(u.split("/").pop(), 10);
    return J(__FP.prov[id] || {});
  }
  return J({});
};
</script>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(HERE, "provenance.db"))
    ap.add_argument("--out", default=os.path.join(HERE, "dist", "fact-provenance.html"))
    ap.add_argument("--page-title", default="Fact Provenance — claim index")
    ap.add_argument("--allow-domains",
                    help="licence gate: file of domains allowed in this build (e.g. cc_domains.txt)")
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    claims = []
    prov = {}
    for r in con.execute("select * from claims order by pubdate desc, id desc"):
        claims.append({
            "id": r["id"], "text": r["text"], "kind": r["kind"], "domain": r["domain"],
            "url": r["url"], "title": r["title"], "pubdate": r["pubdate"],
            "cited_url": r["cited_url"],
        })
        import hashlib
        prov[str(r["id"])] = {
            "@context": {"prov": "http://www.w3.org/ns/prov#", "dct": "http://purl.org/dc/terms/",
                         "fp": "https://factprovenance.org/ns#"},
            "@id": f"https://factprovenance.org/claim/{r['id']}",
            "@type": ["prov:Entity", "fp:Claim"],
            "rdfs:label": r["text"][:160] if r["text"] else "",
            "fp:claimKind": (r["kind"] or "").split(","),
            "fp:extractedFrom": {"@type": "prov:Entity", "prov:value": r["url"],
                                 "fp:contentDigest": "sha256:" + (r["digest"] or ""),
                                 "fp:retrievedFrom": (r["context"] or "")},
            "fp:citedSourceInPage": r["cited_url"],
            "prov:wasGeneratedBy": {"@type": "prov:Activity", "fp:method": "regex-claim-extract"},
            "dct:created": (r["pubdate"] or r["fetched_at"] or ""),
            "fp:verificationStatus": "unverified",
        }

    if a.allow_domains:
        allowed_hosts = {d.strip().split("/")[0] for d in open(a.allow_domains)
                         if d.strip() and not d.strip().startswith("#")}
        before = len(claims)
        claims = [c for c in claims if c["domain"] in allowed_hosts]
        keep_ids = {str(c["id"]) for c in claims}
        prov = {k: v for k, v in prov.items() if k in keep_ids}
        print(f"licence gate: {len(claims)} of {before} claims pass the allow-list "
              f"({before - len(claims)} withheld from this build)")

    kinds = {}
    doms = {}
    cited = 0
    for c in claims:
        for k in (c["kind"] or "").split(","):
            if k:
                kinds[k] = kinds.get(k, 0) + 1
        doms[c["domain"]] = doms.get(c["domain"], 0) + 1
        if c["cited_url"]:
            cited += 1
    stats = {
        "claims": len(claims), "domains": len(doms), "with_cited_source": cited,
        "pages_ok": len({c["url"] for c in claims}),
        "by_kind": dict(sorted(kinds.items(), key=lambda kv: -kv[1])[:12]),
        "by_domain": sorted(doms.items(), key=lambda kv: -kv[1])[:12],
    }
    domains = [{"domain": d, "claims": n} for d, n in sorted(doms.items(), key=lambda kv: -kv[1])]

    payload = json.dumps({"claims": claims, "prov": prov, "stats": stats, "domains": domains},
                         ensure_ascii=False)
    html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
    html = html.replace("<title>Fact Provenance — claim index</title>", f"<title>{a.page_title}</title>", 1)
    marker = "<script>"
    i = html.index(marker)
    html = html[:i] + (SHIM % payload) + html[i:]

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(html)
    print(json.dumps({"out": a.out, "bytes": os.path.getsize(a.out),
                      "claims": stats["claims"], "domains": stats["domains"],
                      "with_cited_source": cited}, indent=2))


if __name__ == "__main__":
    main()
