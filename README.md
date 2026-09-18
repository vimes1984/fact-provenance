# fact-provenance

**origin, not truth: give a claim a return address so rumour has a paper trail.**

fact-provenance is a small, searchable index of factual claims taken from public
sources. Every claim keeps a return address: the page it came from, the sentence
around it, a digest of that page, the date the page declared for itself, when we
first saw the page — and, where the page cited a source of its own next to the
sentence, the URL that page cited.

It does not tell you whether a claim is true. It tells you where the sentence came
from, so you can go and check. A claim with an origin can be argued with. A claim
without one is just a rumour with good posture.

Standard library only. No database server, no framework, no build step.

## What is in here

```
app/serve.py           read-only HTTP server: search UI, JSON API, PROV-O records
app/index.html         the search UI (served at /)
app/index_builder.py   ingest: page fetch -> text -> claim extraction -> SQLite FTS5 index
app/export_static.py   export one self-contained HTML file, licence-gated
app/cc_domains.txt     the source allow-list: crawl list and licence gate in one file
plans/                 the published strategy page (the internal build is not in this repo)
tools/pii_scan.py      release gate: fails the build on any internal marker
docs/                  architecture and publication notes
```

## Quick start

Python 3, no dependencies (developed and run on 3.12.3). The database is not
shipped — build one, or bring your own.

```bash
git clone <this-repo> fact-provenance && cd fact-provenance

# 1. ingest. Pick a rail:
printf 'https://example.gov.ie/some/page\n' > urls.txt
python3 app/index_builder.py --urls urls.txt --db site/provenance.db --delay 2
#    or mine the Common Crawl archive for the domains in the gate file:
python3 app/index_builder.py --cc-domains app/cc_domains.txt --crawl auto \
        --cc-limit 500 --db site/provenance.db
#    (--crawl auto resolves the newest release; on this run it chose CC-MAIN-2026-34)

# 2. serve it
python3 app/serve.py --db site/provenance.db --host 127.0.0.1 --port 8095
#    open http://127.0.0.1:8095

# 3. or export a single self-contained HTML file, licence-gated
python3 app/export_static.py --db site/provenance.db \
        --allow-domains app/cc_domains.txt --out public/index.html

# 4. before you publish anything: the release gate
python3 tools/pii_scan.py
```

`--help` on any script lists its flags. There is no config file and no
environment variable: paths are arguments.

### HTTP surface

| Route | What it returns |
| --- | --- |
| `/` | the search UI |
| `/api/search?q=&kind=&domain=&limit=&offset=` | JSON: matching claims + total (FTS5) |
| `/api/stats` | JSON: counts by domain and kind, last fetch time |
| `/api/claim/<id>` | one claim as JSON (alias of `/claim/<id>`) |
| `/claim/<id>` | the same record: HTML for browsers, PROV-O JSON-LD for `Accept: application/ld+json` |
| `/healthz` | liveness |
| anything else | the UI (bookmarks and typos land somewhere useful); unknown `/api/*` is a 404 |

## The data

Snapshot used for the figures below: a copy of `provenance.db` taken
2026-09-18, 3,260,416 bytes, md5 `53b1b288a4d9c6327db63e55ea5143fb`. The index is
live, so a database you build yourself will be larger.

| | |
| --- | --- |
| claims | 2,239 |
| source domains | 20 |
| pages fetched | 882 rows recorded (`/api/stats` reports 329 as `pages_ok`) |
| distinct page digests | 364 |
| claims carrying a cited source | 514 (23%) |
| claims passing the licence gate | 1,904 (85%) |
| first/last page seen | 2026-09-16T23:10:11Z → 2026-09-18T02:17:02Z |

Per claim we store: `text`, `kind` (one or more of `quantity`, `measure`,
`dateclaim`, `attrib`, `superl`), `url`, `domain`, `title`, `pubdate`, `digest`,
`cited_url`, a short `context` window, and `fetched_at`. Full-text search is a
SQLite FTS5 table (`claims_fts`) kept in step by triggers. Schema details and the
route-by-route walkthrough are in `docs/architecture.md`.

### What the data is not

Read this part as carefully as the numbers.

* **First seen by us is not first in the world.** `fetched_at` is when our
  crawler read the page, not when the claim was published, and not when the event
  happened. `pubdate` is whatever the page declared for itself, if anything.
* **Coverage, not proof.** This is a sample of a handful of public sites. A claim
  being in the index says nothing about the claim being true, current, or
  representative. A claim being absent says nothing at all.
* **A cited source is not our verification.** `cited_url` is the citation the
  source page itself printed next to the sentence. We did not open it, read it, or
  agree with it. The UI labels it as the page's own citation for that reason.

## Licences

Code: MIT (`LICENSE`). Data: CC BY-SA 4.0 (`DATA-LICENCE.md`), which also records
the licence gate: public builds carry only public-dump-safe sources (Wikipedia
CC BY-SA, Irish and UK OGL, US public domain, EU CC BY 4.0) and news domains stay
out of the public build until the licence question is settled. `app/cc_domains.txt`
is that list; `export_static.py --allow-domains` enforces it and prints what it
withheld.

## The release gate

`tools/pii_scan.py` exists so that "the public build carries no internal detail"
is a command, not a promise.

```bash
python3 tools/pii_scan.py --self-test   # proves the guard can fail on a bait file
python3 tools/pii_scan.py               # scans every file git tracks
python3 tools/pii_scan.py PATH          # scans an explicit file or directory
```

* Scope is `git ls-files`: ignored local state (databases, logs, an `evidence/`
  directory) is out of scope, and a file that was accidentally `git add`ed is not.
* A binary artefact is reported **UNSCANNED and fails the build**. Compressed
  formats hide their text from a byte scan, so "could not read it" must never be
  reported as "clean" — that is the hole the rule closes.
* The guard skips exactly one file when scanning the tree: itself, because a list
  of things that must never be published has to contain the things it looks for.
  The skip is printed on every run, and it is the guard's one structural
  weakness. See `docs/PUBLICATION-NOTES.md`.

CI (`.github/workflows/pii.yml`) runs the self-test and the scan on every push
and pull request.

## Honest gaps

Measured, not guessed — these are the things I would want to know before trusting
this index, and they are the reason it is published early rather than late.

1. **It is small.** 20 domains, 2,239 claims, 882 pages. Nothing about it is
   comprehensive, and the absence of a claim is not evidence of anything.
2. **The digest is per page, not per claim.** 2,239 claims share 364 digests, so
   an edit anywhere on a page changes the identity of every claim on it.
3. **Most claims have no cited source.** 514 of 2,239 (23%) do, and those are the
   page's own citations, not ours.
4. **Extraction is regex-based.** Kinds are heuristics over sentence shape; 167
   claims carry more than one kind. There is no model of negation, tense, hedging,
   or whether the sentence is even about this world rather than a hypothetical.
5. **The licence gate matches hostnames exactly, and it costs real coverage.**
   `www.teagasc.ie` and `www.hse.ie` are on the allow-list, but the stored hosts
   are `teagasc.ie` (52 claims) and `www2.hse.ie` (36), so 88 claims from Irish
   public bodies are withheld over spelling. `ourworldindata.org` (226 claims,
   published under CC BY 4.0) is not on the list at all. Measured 2026-09-18:
   1,904 of 2,239 claims pass.
6. **The live-fetch rail and Wikipedia disagree.** A one-URL live run was refused
   with `robots.txt disallow` for a Wikipedia article page; Python's standard
   `robotparser` refuses every Wikipedia article URL tried, for `*` as well as for
   our user-agent, while the file's `User-agent: *` section does not appear to
   disallow that path. Cause not diagnosed. Practical effect: Wikimedia coverage
   in this index comes from the Common Crawl rail, not live fetching.
7. **The bulk rail is not self-contained.** `--warc-csv` consumes rows produced by
   a sibling tool that is not part of this repository, so that path cannot be
   reproduced from this repo alone.
8. **The server is a prototype.** No authentication, no rate limiting, no TLS, no
   cache, no tests, and it binds `0.0.0.0` by default. It reads the database
   read-only per request, but SQLite is single-writer: put it behind a reverse
   proxy and serve a copy, not your only database.
9. **Figures quoted elsewhere may be older than this README.** Numbers travel and
   this index grows; the snapshot above is dated and hashed for that reason.

## Contributing

See `CONTRIBUTING.md`. The short version: keep the return address, add sources
that are safe to publish, and run `tools/pii_scan.py` before you push.
