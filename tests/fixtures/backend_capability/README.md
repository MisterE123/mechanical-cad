# Exact backend compatibility baselines

These are byte-for-byte snapshots of historical source, stored as `.py.txt`
fixtures so source archives can run the compatibility tests without Git, repository
history, or a separate release checkout. The test suite must never regenerate them
from the current implementation.

- `sidecar-b965df1.py.txt` preserves the pre-contract sidecar for exact stdout-byte
  comparisons of legacy success and failure responses.
- `sketch_solver-51ed72d.py.txt` preserves the qualified arc-core solver for exact
  source comparisons of its three audited safeguard functions.

`provenance.json` records the full source commits, paths, Git blob IDs, SHA-256
digests, and lengths. The fixtures were captured using the exact output bytes of
`git show <source_commit>:<source_path>`, with no rewriting or newline conversion.
Tests verify the pinned SHA-256 before using each fixture and retain the original
byte-equality assertions. Historical implementation text is deliberately data,
not an imported module or a replacement production implementation.

To verify provenance in a checkout that retains the historical commits, compare
each fixture's bytes with `git show` for its recorded commit and path. That check is
an authoring/audit step only; running packaged tests requires no Git installation.
