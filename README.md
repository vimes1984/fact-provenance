# fact-provenance

[![release gate](https://github.com/vimes1984/fact-provenance/actions/workflows/pii.yml/badge.svg)](https://github.com/vimes1984/fact-provenance/actions/workflows/pii.yml)
[![docs](https://github.com/vimes1984/fact-provenance/actions/workflows/docstrings.yml/badge.svg)](https://github.com/vimes1984/fact-provenance/actions/workflows/docstrings.yml)
[![release](https://img.shields.io/github/v/release/vimes1984/fact-provenance?label=release&color=4a84fe)](https://github.com/vimes1984/fact-provenance/releases)
[![python](https://img.shields.io/badge/python-3.9%2B-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](#quick-start)
[![code licence](https://img.shields.io/badge/code-MIT-blue)](LICENSE)
[![data licence](https://img.shields.io/badge/data-CC%20BY--SA%204.0-lightgrey)](DATA-LICENCE.md)
[![last commit](https://img.shields.io/github/last-commit/vimes1984/fact-provenance)](https://github.com/vimes1984/fact-provenance/commits/main)

**origin, not truth: give a claim a return address so rumour has a paper trail.**

fact-provenance is a small, searchable index of factual claims taken from public
sources. Every claim keeps a return address: the page it came from, the sentence
around it, a digest of that page, the date the page declared for itself, when we
first saw the page — and, where the page cited a source of its own next to the
sentence, the URL that page cited.

It does not tell you whether a claim is true. It tells you where the sentence came
from, so you can go and check. A claim with an origin can be argued with. A claim
without one is just a rumour with good posture.

Records are served as W3C PROV-O over JSON-LD. Standard library only — no database
server, no framework, no build step, no dependencies.

**In one line:** ingest a public page → keep the sentence, the page, its digest and
its own citations → search it, and resolve any claim id to a PROV-O record.

## Contents

- [What it is](#what-it-is)
- [Repository map](#repository-map)
- [Quick start](#quick-start)
- [HTTP surface](#http-surface)
- [The data](#the-data)
- [What the data is not](#what-the-data-is-not)
- [The provenance model](#the-provenance-model)
- [Documentation](#documentation)
- [The two gates](#the-two-gates)
- [Continuous integration](#continuous-integration)
- [Licences](#licences)
- [Citation](#citation)
- [Honest gaps](#honest-gaps)
- [Contributing](#contributing)
- [Keywords](#keywords)

## What it is

Three parts, each replaceable:

```
public pages ──┬── live fetch (robots-checked, 2s apart) ──┐
               └── Common Crawl archive (bulk, no load) ───┴──► claim extraction
                                                              (regex over sentence shape)
                                                                     │
                                                                     ▼
                                                        provenance.db  (SQLite + FTS5)
                                                              ├──► app/serve.py       HTTP: UI, JSON API, PROV-O
                                                              └──► export_static.py   one self-contained HTML file
```

1. **Ingest** (`app/index_builder.py`) walks pages, stores the sentence that carries
   a checkable shape — a quantity, a measure, a dated statement, an attribution, a
   superlative — with the page it came from and a digest of that page.
2. **Store** (`provenance.db`) is one SQLite file with an FTS5 index over claim text.
   The database is not shipped: build one, or bring your own.
3. **Serve** (`app/serve.py`) is read-only: a search UI, three JSON routes, and a
   PROV-O record per claim.

The licence gate (`app/cc_domains.txt`) is the same file as the crawl allow-list, so
the set of sources that may be crawled and the set that may be published cannot
drift apart.

## Repository map

```
app/serve.py           read-only HTTP server: search UI, JSON API, PROV-O records
app/index.html         the search UI (served at /)
app/index_builder.py   ingest: page fetch -> text -> claim extraction -> SQLite FTS5 index
app/export_static.py   export one self-contained HTML file, licence-gated
app/cc_domains.txt     the source allow-list: crawl list and licence gate in one file
plans/                 the published strategy page (the internal build is not in this repo)
tools/pii_scan.py      release gate: fails the build on any internal marker
tools/doc_coverage.py  documentation gate: fails the build on an undocumented object
docs/architecture.md   schema, ingest rails, server routes, and what was not verified
docs/PUBLICATION-NOTES.md  what the gates prove, what they do not, and this repo's history
CONTRIBUTING.md        ground rules, how to add a source domain, how to run things
DATA-LICENCE.md        the data licence and the per-source licence mapping
CITATION.cff           how to cite this index
LICENSE                MIT, for the code
```

`tools/pii-markers.local` is deliberately **not** in this repository: the private
half of the release gate's marker list lives outside the published tree, so the gate
can look for our own identifiers without publishing them. See
[the two gates](#the-two-gates).

## Quick start

Python 3.9+ (developed and run on 3.12.3), standard library only. The database is not
shipped.

```bash
git clone https://github.com/vimes1984/fact-provenance.git && cd fact-provenance

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

# 4. before you publish anything: both gates
python3 tools/pii_scan.py
python3 tools/doc_coverage.py
```

`--help` on any script lists its flags. There is no config file and no environment
variable: paths are arguments.

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

```bash
# search
curl -s 'http://127.0.0.1:8095/api/search?q=emissions&limit=3' | python3 -m json.tool

# one claim as linked data
curl -s -H 'Accept: application/ld+json' http://127.0.0.1:8095/claim/1 | python3 -m json.tool
```

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
route-by-route walkthrough are in [`docs/architecture.md`](docs/architecture.md).

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

## The provenance model

Every claim id resolves to a W3C PROV-O record in JSON-LD, served at
`https://factprovenance.org/claim/<id>` and mirrored by `/api/claim/<id>`. Shape as
served (abridged):

```json
{
  "@context": {
    "prov": "http://www.w3.org/ns/prov#",
    "dct": "http://purl.org/dc/terms/",
    "schema": "http://schema.org/",
    "fp": "https://factprovenance.org/ns#"
  },
  "@id": "https://factprovenance.org/claim/1",
  "@type": ["prov:Entity", "fp:Claim"],
  "fp:claimText": "…the sentence as published…",
  "fp:claimKind": ["quantity", "measure"],
  "fp:verificationStatus": "unverified",
  "fp:verificationNote": "Indexed from the published page. Quote-match against the cited source has not been run yet.",
  "prov:wasDerivedFrom": {
    "@type": ["prov:Entity", "schema:CreativeWork"],
    "@id": "https://example.gov.ie/some/page",
    "schema:name": "…the page's own title…",
    "fp:publicationDate": "2026-09-01",
    "fp:contentDigest": "sha256:…",
    "fp:retrievedAt": "2026-09-18T02:17:02Z"
  },
  "prov:wasGeneratedBy": {
    "@type": "prov:Activity",
    "fp:method": "regex-extract",
    "fp:agent": "fp-extractor/0.1"
  },
  "dct:created": "2026-09-18T02:17:02Z",
  "fp:citedSource": {
    "@id": "https://example.org/the-source-the-page-cited",
    "fp:citationKind": "as-published",
    "fp:note": "candidate pointer only — not verified by this index"
  }
}
```

Two choices worth knowing about, because they are the honesty of the format:

* `fp:verificationStatus` is always `unverified`. The index carries origins, not
  verdicts, and a machine-readable record has to say so rather than leave a reader
  to assume otherwise.
* The cited source is typed `fp:citationKind: "as-published"` with a note that it is
  a pointer only. It is the page's claim about its own sourcing, not a check we ran.

## Documentation

| Where | What |
| --- | --- |
| [`docs/architecture.md`](docs/architecture.md) | the store, the two ingest rails, the server, the UI, the export, and a section on what was **not** verified |
| [`docs/PUBLICATION-NOTES.md`](docs/PUBLICATION-NOTES.md) | what the gates prove and what they cannot, and the history of this repository |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | ground rules, adding a source domain, running things, commit style |
| `--help` on every script | flags, defaults, and the reasoning where a default is opinionated |
| docstrings, everywhere | every module, class and function, including nested helpers |

"The code is documented" is checked here, not asserted:

```bash
python3 tools/doc_coverage.py            # every .py file git tracks
python3 tools/doc_coverage.py PATH       # explicit files or directories
python3 tools/doc_coverage.py --min 90   # allow a floor (CI uses the default, 100%)
```

Current state: **42/42 objects documented (100%)** — 5 files, modules and nested
helpers included.

## The two gates

Both gates are commands with exit statuses, because "the public build carries no
internal detail" and "the code is documented" are claims about a whole tree, and
claims about a whole tree are exactly the kind that rot.

### Release gate — `tools/pii_scan.py`

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
* The marker list has two halves. The markers that are harmless to publish (being
  the words an internal build carries: its scope label, filesystem paths, host
  identifiers) live in `tools/pii_scan.py`, where you can read them. The markers
  that would themselves be a disclosure — our own names and addresses — live in
  `tools/pii-markers.local`, which is gitignored, and are merged in at run time.
  Publishing a guard cannot mean publishing what it guards against.
* The guard skips exactly one file when scanning the tree: itself, because a list of
  things that must never be published has to contain the things it looks for. The
  skip is printed on every run, and it is the guard's one structural weakness. See
  [`docs/PUBLICATION-NOTES.md`](docs/PUBLICATION-NOTES.md).

### Documentation gate — `tools/doc_coverage.py`

Parses every tracked `.py` file with `ast` and requires a docstring on each module,
class and function. It prints what it found, names what is missing with a line
number, and fails below the floor (100% by default). Nested helpers are not exempt.

## Continuous integration

| Workflow | Job | What it refuses |
| --- | --- | --- |
| [`.github/workflows/pii.yml`](.github/workflows/pii.yml) | `pii-guard` | any tracked file carrying an internal marker, and any binary that cannot be certified as text |
| [`.github/workflows/docstrings.yml`](.github/workflows/docstrings.yml) | `docstrings` | any module, class or function without a docstring |

Both run on every push and every pull request. The release gate runs its self-test
first, so a guard that has quietly stopped working fails the build instead of passing
everything.

## Licences

Code: MIT ([`LICENSE`](LICENSE)). Data: CC BY-SA 4.0
([`DATA-LICENCE.md`](DATA-LICENCE.md)), which also records the licence gate: public
builds carry only public-dump-safe sources (Wikipedia CC BY-SA, Irish and UK OGL, US
public domain, EU CC BY 4.0) and news domains stay out of the public build until the
licence question is settled. `app/cc_domains.txt` is that list;
`export_static.py --allow-domains` enforces it and prints what it withheld.

## Citation

[`CITATION.cff`](CITATION.cff) — GitHub's "Cite this repository" button reads it.
Cite the index as *fact-provenance: an open index of where web claims come from*,
version 0.1.0. When you quote claims from it, cite the **source page** as well: the
origin is the point, and the licence it carries is the source's, not ours.

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

See [`CONTRIBUTING.md`](CONTRIBUTING.md). The short version: keep the return
address, add sources that are safe to publish, and run both gates before you push.

```bash
python3 tools/pii_scan.py && python3 tools/doc_coverage.py
```

## Keywords

`provenance` · `PROV-O` · `JSON-LD` · `linked-data` · `RDF` · `claim-extraction` ·
`fact-checking` · `misinformation` · `open-data` · `transparency` · `civic-tech` ·
`data-journalism` · `SQLite` · `FTS5` · `Python` · `stdlib-only` · `W3C` ·
`knowledge-graph` · `accountability`

The same list is set as this repository's GitHub topics.

## Status

**0.1.0 — prototype, published early on purpose.** Ingest, store, search and the
PROV-O surface work end to end and are covered by the two gates above. Known next
steps, in the order they matter: per-claim digests instead of per-page (gap 2),
hostname normalisation in the licence gate (gap 5), quote-matching the cited sources
so `fp:verificationStatus` can stop saying `unverified` for the ones that hold up
(gap 3), and tests around the extractor (gap 8).

Live instance: **https://factprovenance.org**
