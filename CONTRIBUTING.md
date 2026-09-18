# Contributing

One idea holds this project together: every claim keeps a return address. A
change that adds claims without keeping their origin, or that drops the origin
to make the numbers look better, is not a change we can take.

## Ground rules

1. **Evidence, not vibes.** A patch that changes what the index claims about the
   world should say how you checked it (a command, an output, a row).
2. **No internal material, ever.** The release gate (`tools/pii_scan.py`) fails
   on internal markers and on any binary artefact it cannot read as text. Run it
   before you push; CI runs it on every push and pull request.
3. **The private deployment's builds are not part of this repository.** See
   `docs/PUBLICATION-NOTES.md` for what is deliberately withheld and why.
4. **Licences decide what can be indexed.** See `DATA-LICENCE.md`.

## Adding a source domain

`app/cc_domains.txt` is both the crawl list and the licence gate. To add a host:

* It must be public-dump-safe: Wikipedia (CC BY-SA), government material under
  OGL or US public-domain terms, or EU material under CC BY 4.0. News domains
  stay out until the licence question is settled.
* Add the licence family to the header comment so the mapping stays visible.
* Add **every hostname form you expect to be stored**. The gate compares the
  stored `domain` field for an exact match, so a claim stored under `example.ie`
  is withheld even if `www.example.ie` is on the list. That has already cost
  real coverage (see the gaps section of the README), so check your inventory
  with:

  ```
  python3 -c "import sqlite3;print(*sqlite3.connect('site/provenance.db').execute('select domain,count(*) from claims group by 1 order by 2 desc'),sep='\n')"
  ```

## Running things

```
python3 app/index_builder.py --help     # ingest
python3 app/serve.py --help            # serve
python3 app/export_static.py --help    # single-file export
python3 tools/pii_scan.py --self-test  # prove the guard can fail
python3 tools/pii_scan.py              # the gate itself
```

There is no test suite yet. If you add one, make it runnable as
`python3 -m pytest` and keep it dependency-light — the project ships with
nothing but the Python standard library.

## Commits

One line, imperative, in the present tense ("add OGL host to the gate", not
"added"). Put the command and its output in the body when the change is about
data, and say plainly what you could not verify.

## Reporting a problem

Open an issue with the claim id, the stored origin, and what you expected. If
the return address is wrong, that is a bug worth more than a wrong claim: the
whole point of the index is that you can go and look.
