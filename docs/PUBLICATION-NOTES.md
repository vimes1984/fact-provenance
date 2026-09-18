# Publication notes

What is in the public build, what is deliberately not, and what the release gate
does and does not prove. Written for whoever publishes this repository, so that
the omissions are a decision rather than a surprise.

## The public build

| Published | Why |
| --- | --- |
| `app/` — `serve.py`, `index.html`, `index_builder.py`, `export_static.py`, `cc_domains.txt` | the runnable application |
| `plans/` — the published strategy page only | it is the public build of that page |
| `tools/pii_scan.py`, `.github/workflows/pii.yml` | the release gate and its CI |
| `docs/`, `README.md`, `LICENSE`, `DATA-LICENCE.md`, `CONTRIBUTING.md` | this documentation |
| `PUSH.md` | the commands to publish, for the maintainer |

`app/serve.py` in this repository is the application **before** the private
deployment's changes, kept byte-for-byte. The private deployment's copy adds
absolute staging paths, a second document route and a docx route. Those changes
are deployment, not application: they name a private host layout and serve a
document that is not part of the public build. Keeping the pre-deployment copy
means the published file is an artefact that already existed, not a rewrite.

The published build was checked against the private deployment's running service:
`/api/stats`, `/api/claim/1`, `/api/search?q=eire&limit=5` and the UI page came
back **byte-identical** from both, so publishing this copy does not change the
public behaviour of the application.

## Deliberately withheld

| Withheld | Why |
| --- | --- |
| the private strategy master | it carries internal infrastructure identifiers (private LAN hosts, host addresses, internal job and agent names) |
| the internal review build of the strategy page | same, plus it is the one artefact that must never leave the private side |
| the rule-based splitter that produces those two builds | it necessarily contains, as its strip-list, every identifier it removes |
| the private deployment's `serve.py` changes | absolute staging paths plus a route that serves a private document |
| any database (`*.db`), any `evidence/` directory | local state; the index is data, and the evidence carries the identifiers this build excludes |

The consequence is stated in the README's gaps list: this repository cannot
regenerate its own copy of the strategy page, because the master and the splitter
are on the private side.

## What the gate proves, and what it does not

`tools/pii_scan.py` proves one thing: **no file git tracks contains any marker on
its list, and no tracked file is a binary the scan could not read.** CI runs it on
every push and pull request, after a self-test that proves the guard can fail.

It does not prove:

* **That the marker list is complete.** It is a list, not a rule. Text that
  *describes* the private side without using a listed token passes. The published
  application contains two such sentences — a route that serves the private
  strategy page (which 404s here, because the file is not in this repository) and
  a port number carried over from an earlier private deployment. Neither is a
  credential, an address or a name, and both were left in place rather than
  editing an artefact to satisfy a gate. Review them before publishing; if the
  decision is to remove them, remove them in the application and re-run the gate.
* **That the guard cannot hide its own leak.** The guard skips exactly one file
  when it scans the tree: itself. A marker list has to contain the markers, so
  self-exclusion is structural rather than optional. The skip is printed on every
  run. If that trade is unacceptable, keep the marker list in a private CI config
  instead of in the repository.
* **That the markers are secret.** Publishing this repository publishes the marker
  list, including the address of a private host. That is inherent to a published
  blocklist. If a token on the list is sensitive in itself, the list belongs in
  CI secrets and not in a file.
* **Anything about binaries.** A `.docx`, `.zip` or any compressed artefact hides
  its text from a byte scan, which is why the guard fails the build on a binary
  rather than certifying it. Keep binaries out of the public tree.

## Before you publish

1. `python3 tools/pii_scan.py --self-test` — the guard must fail the bait file.
2. `python3 tools/pii_scan.py` — the tree must pass.
3. `git ls-files` — read the list. A gate checks tokens; a human checks intent.
4. Decide the two sentences above, and the copyright holder line in `LICENSE`.
5. Set a committer identity you are happy to have in public history, then push
   with `PUSH.md`.

## History and provenance of this repository

The pre-hardening build is **not** in this history. Before the first commit that
was cleaned for publication, the public plan page still carried the internal
build's scope label, an internal filesystem path, the CDN provider name and an
internal role heading. That earlier build is archived outside the repository, on
the private rig that built it, together with the gate run that caught it
(5 markers, exit 1). Nothing was deleted; it was simply never published.

The guard in `tools/pii_scan.py` was extended the same day: it had passed the
leaky build, so the marker list, not the file, was the defect. `--self-test`
fails a bait file on every run to prove the gate can still fail.
