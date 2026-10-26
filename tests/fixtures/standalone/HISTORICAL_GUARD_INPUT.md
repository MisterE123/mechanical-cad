# Historical guard-byte input

`historical_guard_1c8f030.py.txt` is inert source text from commit
`1c8f03026c814cd69bfb25c35449810b5b858fb2`, path
`tests/unit/test_arc_profile_native_end_cap.py`. The companion provenance records
its existing pinned size and SHA-256; tests also check it against the unchanged
`STANDALONE_HARNESS_ORIGINALS` identity before using it as data. No Git executable
or `.git` directory is required at test runtime. The fixture is never executed.

Only the original positive guard-byte case and six guard-source mutation cases
use this historical input. Each mutation first passes the original positive seal,
then must fail the unchanged guard. This does not reconstruct later source layers,
repin current source as old-equivalent, or qualify current runtime behavior.

The visual-joint layer still pins ancestor
`db8cac466c8b7dad3a17d2107b66128180be395e`; all seven added-file pins match that
ancestor, while committed later features changed those files. Commit `9a89fd3`
explicitly archived obsolete whole-tree freeze assertions but retained inverse
helpers. Broader historical-input routing requires a separate scoped review.
The current Windows import-edge, dependency-leaf and dormant-query contract
mismatches remain visible and are not waived by this narrow routing repair.
