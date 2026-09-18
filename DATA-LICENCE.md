# Data licence

**The claims data in this project is published under Creative Commons
Attribution-ShareAlike 4.0 International (CC BY-SA 4.0).**
<https://creativecommons.org/licenses/by-sa/4.0/>

The code is MIT (see `LICENSE`). The two licences are separate on purpose: the
code is a tool, the data is a collection of other people's sentences.

## What we are licensing, and why CC BY-SA

Every row in `claims` is a sentence extracted from a page published by someone
else. We do not own those sentences and we cannot relicense them more permissively
than their strictest source allows, so the data is released under the same terms
as its largest source: Wikipedia, CC BY-SA. That is the whole reason for the
choice — not a preference for share-alike.

Two consequences, stated plainly:

* **Attribution is required.** Every claim we publish carries the page it came
  from (`url`, `domain`, `title`, `pubdate`) and the time we first saw it
  (`fetched_at`). That is the attribution, and it is machine-readable. A reuse
  must keep it.
* **Share-alike propagates.** A public build of this data — including one you
  derive — stays under CC BY-SA 4.0.

We are not relitigating anyone else's licence. Material we take from Wikipedia
stays CC BY-SA; Irish and UK government material stays under its own OGL terms;
US federal material stays public domain; EU material stays CC BY 4.0. We record
the source, we do not relicense it, and this file is a description of what we do,
not legal advice.

## The licence gate: public builds carry only public-dump-safe sources

The build refuses claims whose source domain is not on the allow-list. The rule,
as the project states it in `app/cc_domains.txt`:

> Wikipedia (CC BY-SA, attribution), Irish gov/eGov (OGL), UK OGL, US .gov
> (public domain), EU (CC BY 4.0). News domains (rte.ie, irishtimes, guardian,
> bbc) stay OUT of the public build until the licence story is settled.

`app/cc_domains.txt` is both the crawl list and the gate. `app/export_static.py`
applies it with `--allow-domains`, and reports what it withheld:

```
$ python3 app/export_static.py --db site/provenance.db --allow-domains app/cc_domains.txt --out public/index.html
licence gate: 1904 of 2239 claims pass the allow-list (335 withheld from this build)
```

On the 2026-09-18 snapshot that withholding was: `ourworldindata.org` (226),
`teagasc.ie` (52), `www2.hse.ie` (36), `www.irishtimes.com` (20), `www.bbc.com`
(1). Two of those deserve a look before the next build — `teagasc.ie` and
`www2.hse.ie` are Irish public bodies whose material the project intends to
allow, and they are withheld only because the stored hostname is not spelled
exactly like the allow-list entry (`www.teagasc.ie`, `www.hse.ie`). See the gaps
section of the README.

## Attribution format

> Claim text via fact-provenance, from <title> — <url> (<domain>), first seen by
> us <fetched_at>. Data licensed CC BY-SA 4.0.

## Per-source licence mapping

The mapping below is the project's own list, carried over from the gate file. It
has not been re-verified against each publisher's current terms for this build;
if you are reusing the data downstream, check the publisher's page for the
licence in force today.

| Source | Licence as the project records it |
| --- | --- |
| `*.wikipedia.org` | CC BY-SA 4.0 (attribution required) |
| `*.gov.ie`, `data.gov.ie`, `www.cso.ie`, `www.epa.ie`, `www.met.ie`, `www.hse.ie`, `www.teagasc.ie` | Irish public sector information / OGL |
| `www.ons.gov.uk`, `www.parliament.uk` | UK OGL |
| `www.nasa.gov`, `www.noaa.gov`, `www.usgs.gov`, `www.nih.gov`, `www.cdc.gov` | US federal, public domain |
| `ec.europa.eu`, `www.eurostat.ec.europa.eu` | EU, CC BY 4.0 |
| `www.un.org` | not recorded in the gate file |
| anything not listed | withheld from public builds |

## Notes for anyone publishing a build

* Keep `fetched_at` and the source URL on every claim. Without them the dataset
  is unattributable and the licence does not travel with it.
* Do not mix a private or commercial index into a CC BY-SA build: share-alike
  does not survive that.
* The absence of a claim is not a licence statement. The gate withholds by exact
  hostname match, so a withheld claim usually means the domain needed adding,
  not that the source is unusable.
