# Publishing this repository

There is **no credential on this machine** and no remote repository has been
created. Nothing here has been pushed anywhere. These are the commands to do it
when you are ready.

## 1. Check before you push

```bash
cd fact-provenance

# the release gate: must print PASS (exit 0)
python3 tools/pii_scan.py --self-test
python3 tools/pii_scan.py

# read the file list a human way, not a grep way
git ls-files

# the internal build must be absent from the index (must print 0)
git ls-files | grep -c internal
```

Also decide, before the first push:

* the copyright holder line in `LICENSE` (currently `the fact-provenance
  authors`);
* the committer identity in the commit below — it becomes public history;
* the two sentences flagged in `docs/PUBLICATION-NOTES.md`.

If you change any of those, edit and commit again, or amend:

```bash
git -c user.name="Your Name" -c user.email="you@example.org" commit --amend --reset-author
```

## 2. Create the repository and push

Create the repository on your host first (empty, no README, no licence), then:

```bash
cd fact-provenance

# SSH (recommended; uses your key)
git remote add origin git@github.com:<owner>/<repo>.git

# or HTTPS with a token from your credential store
# git remote add origin https://github.com/<owner>/<repo>.git

git push -u origin main
```

Verify from the outside rather than trusting the push output:

```bash
git remote -v
git ls-remote origin
```

## 3. After the first push

* Turn on branch protection for `main` and require the `pii-guard` workflow
  (`.github/workflows/pii.yml`) to pass. That workflow is the release gate; a
  repository whose gate is not required is a repository whose gate is decoration.
* Keep the database and any `evidence/` directory out of the remote — they are
  ignored by `.gitignore`, so the only way in is `git add -f`. Do not.
* If you ever need to publish a new build of the strategy page, generate it on the
  private side and commit only the public artefact, as the current copy was.
