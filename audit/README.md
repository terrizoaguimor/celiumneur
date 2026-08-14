# External RTL audit pack

This directory makes the design audit behind CeliumNeUR's invariants
reproducible without copying or redistributing third-party RTL.

The lock records, for each reviewed project:

- the canonical repository, exact commit and Git tree;
- the upstream license identifier and normalized content hash;
- every evidence file and the normalized hash of each cited line range; and
- the invariant influenced by each observation.

The interpretation is in [FINDINGS.md](FINDINGS.md). The machine-readable
record is [source_snapshot.lock.json](source_snapshot.lock.json). A hash is
computed after normalizing CRLF or CR line endings to LF, so Windows and Linux
checkouts produce the same result.

## Reproduce against existing checkouts

From the CeliumNeUR repository root:

```powershell
python audit/verify_sources.py `
  --source-root C:\Users\Mario\Documents\neuromorphic\designs
```

The verifier requires the exact commit, exact tree, canonical origin, clean
worktree, license hash, file hashes and every cited range hash.

## Reproduce from the network

On a clean machine with Git, Python 3.9+ and network access:

```bash
python audit/verify_sources.py --clone-dir /tmp/celiumneur-audit-sources
```

The command creates missing repositories only inside the supplied directory,
uses sparse checkout for the evidence files, checks out the pinned commits in
detached mode and verifies them. It never deletes or overwrites an existing
directory. If a target directory already exists, it must itself pass the exact
checks.

For an offline integrity check of the lock and findings index:

```bash
python audit/verify_sources.py --validate-manifest
```

The normal CI path performs this offline check. A manually dispatched GitHub
Actions run also performs the clean network reproduction in an isolated runner
temporary directory, so upstream availability cannot make ordinary pushes or
pull requests fail.

## Boundary of the evidence

The pack is a source-level structural audit of the pinned revisions. It does
not claim that every upstream use case fails, that the latest upstream default
branch has the same behavior, or that CeliumNeUR is functionally equivalent to
any reviewed design. Protocol assumptions and architectural tradeoffs are
explicitly separated from loss paths and verification gaps.

No third-party source is stored in CeliumNeUR. Reviewers obtain it from the
listed upstream repositories under the upstream licenses recorded in the lock.
