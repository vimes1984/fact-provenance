# Architecture

Written by reading the code in this repository, not from a design document. Where
something is asserted that the code does not show, it says so.

Six moving parts: one ingest script, one SQLite file, one read-only server, one
UI page, one exporter, one release gate.

## 1. The store: `provenance.db` (SQLite, FTS5)

Three objects matter:

* **`pages`** — one row per page the crawler touched: `url, domain, status, http,
  claims, title, pubdate, fetched_at, note`. `status` records what happened
  (`blocked` with a note like `robots.txt disallow` is a first-class outcome, not
  an error), `http` the status code, `claims` how many claims that page yielded.
* **`claims`** — one row per extracted sentence: `id, text, kind, url, domain,
  title, pubdate, digest, cited_url, context, fetched_at`. `kind` is a
  comma-separated list where a sentence matches more than one shape.
* **`claims_fts`** — an FTS5 table over the claim text, kept in step with
  `claims` by triggers declared in the same schema (`index_builder.SCHEMA`).

The database is created by the ingest script, on first write. It is never
committed (`.gitignore`).

## 2. Ingest: `app/index_builder.py`

Two rails into the same schema:

* `--urls FILE` — one URL per line, fetched live, politely (`--delay`), after a
  `robots_ok()` check (`urllib.robotparser`, cached per host, with an unreachable
  robots.txt treated as allowed and logged).
* `--cc-domains FILE` — bulk mining of the Common Crawl archive: resolve the
  newest release (`--crawl auto`, or pin one like `CC-MAIN-2026-34`), look the
  domains up in the crawl's index, range-fetch the WARC records, extract text.
  `--cc-limit` / `--max-pages` bound the run. A third rail, `--warc-csv`,
  consumes rows from a sibling tool kept outside this repository.

Extraction is a set of regular expressions over the page text, with reference
anchors turned into `cited_url`: where the sentence sits next to a citation the
page itself printed, that citation is stored as the page's claim, never as ours.
`to_text_with_refs()` and `claims_from_page()` in `index_builder.py` are the
place to look; the taxonomy reuses the project's earlier probe tooling.

What it does not do: no JavaScript execution, no PDF or table parsing, no
deduplication of near-identical sentences, no entity resolution, no opinion about
truth. A page that cannot be fetched is recorded and skipped.

## 3. Serve: `app/serve.py`

Standard library only: `http.server.ThreadingHTTPServer` plus `sqlite3`.

* The database is opened **read-only per request**; nothing is written by the
  server.
* Query text is sanitised before it reaches FTS5 (`fts_query`), because raw user
  input is FTS5 syntax.
* Routes: `/` and `/index.html` (the UI), `/healthz`, `/api/stats`,
  `/api/search`, `/api/claim/<id>`, `/claim/<id>`, `/favicon.ico` (inline SVG).
  Any other path serves the UI, except unknown `/api/*`, which is a strict 404.
* Content negotiation: `/claim/<id>` returns HTML to a browser and a PROV-O
  JSON-LD record to `Accept: application/ld+json` (a `@context` mapping `prov:`,
  `dct:`, `schema:` and `fp:`, with the claim's origin as `prov:wasDerivedFrom`).
* The UI is read from the directory `serve.py` lives in, so the app is portable:
  `--db`, `--host` (default `0.0.0.0`), `--port` are the whole configuration.

## 4. UI: `app/index.html`

A single self-contained page: it calls `/api/search`, `/api/claim/<id>`,
`/api/stats` and `/api/domains` and renders claims with their origin. No
framework, no build step, no external assets beyond the server's own favicon.
The origin block is deliberately the loudest thing on the page: the point of the
project is that you can go and look.

## 5. Export: `app/export_static.py`

Produces one self-contained HTML file with the claims and a small fetch shim
(stubbed answers for the `/api/*` calls the UI makes), so a copy of this project's
data can be opened from a filesystem or hosted anywhere with no server.

**It is also the licence gate.** `--allow-domains FILE` takes the same file the
crawler uses (`app/cc_domains.txt`); claims whose `domain` is not on that list are
left out of the artefact, and the script prints the arithmetic:

```
licence gate: 1904 of 2239 claims pass the allow-list (335 withheld from this build)
```

The match is an exact string comparison against the stored hostname. See
`DATA-LICENCE.md`.

## 6. Release gate: `tools/pii_scan.py`

Scans the files git tracks for internal markers and fails the build if it finds
one, or if it finds a binary artefact it cannot read as text. It runs in CI on
every push and pull request. Its scope, its one self-skip and the reasoning are
in `docs/PUBLICATION-NOTES.md`.

## The strategy page in `plans/`

The public build of the project's strategy page is a static artefact; on the
private deployment it is generated from a master copy by a rule-based splitter,
which is not part of this repository (it carries the identifiers it strips — see
`docs/PUBLICATION-NOTES.md`). Consequently this repository cannot regenerate its
own copy of that page, and does not claim to.

## Not verified here

* The previous point: the splitter and its master were not audited by the pass
  that assembled this repository; only the published build was checked.
* No load, concurrency or SQLite-corruption testing was done. The server is a
  thread-per-connection prototype.
* No test suite exists. Nothing in this repository is covered by automated tests
  other than the release gate.
