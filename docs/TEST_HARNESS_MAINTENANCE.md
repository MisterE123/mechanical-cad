# Test-harness maintenance after frozen 1.28

This work changes test fixtures, not runtime behavior. The 1.28 installer remains
frozen at c3e187f41c96aeee18ca391109ce2de27fbea57e with SHA-256
`a8ebffe28769f19675ffadf96a2d31475921a7c1925d0463476ce111dc5ff6e0`.
Do not transfer later source-test results retroactively to that archive receipt.

## Registration extraction fixtures

Six failures in the packaging/runtime subset came from incomplete AST-extracted
namespaces: five lacked `local_recovery`; one preferences-draw fixture lacked a
package/name for its relative recovery import. Updating that fixture also exposed
its obsolete exact license-footer wording. Production registration/draw code is
unchanged.

The repaired fixtures explicitly spy on recovery start/stop and face/review/staged
cancellation, rather than silently ignoring them. Assertions cover idempotent
registration, recovery teardown before class cleanup, rollback after a failing
rebind, preservation of foreign-owned RNA and a newly injected recovery-start
failure. Preferences retain no manual backend paths in bundled mode, exercise the
recovery drawing call in both modes, and verify current attribution text.

Verification: 20 registration tests passed; 24 registration plus execution-lease
tests passed together; source Ruff passed. This does not erase the separately
recorded 441-failure subset or prior aggregate result. No aggregate rerun.

## Historical input attribution (read-only finding)

The first reconstruction gate's seven visual-joint added-file pins exactly match
ancestor db8cac466c8b7dad3a17d2107b66128180be395e. Their fixture has not changed,
but later committed revolute-joint/mating/gear-preview work changed those files.
Commit 9a89fd326a1694b1ee842e3478588693e42eaf0a explicitly retired the old whole-tree
freeze assertions, preserving the original harness as
`docs/regressions/historical_source_guards/arc_profile_native_end_cap_0_7.py.txt`.
That archive matches db8cac4 exactly (216,430 bytes); the retained helper module
is 148,729 bytes and cannot satisfy the historical whole-file identity.

The standalone boundary suite still supplies today's tree to these historical
inverses. Of 435 failures, 432 stop at historical source size/hash gates; this
establishes stale input routing, not that later code automatically satisfies every
old contract. The remaining three static Windows import/dormancy mismatches are
independent and remain open.

## Narrow historical byte-family repair

The original seven guard-byte cases now read an inert, immutable source fixture
from ancestor `1c8f03026c814cd69bfb25c35449810b5b858fb2`. Its 64,854 bytes and
SHA-256 are checked against the original trusted identity, not new pins for
current code. The original normalized seal and all six mutation-rejection
assertions remain unchanged; every mutation first establishes a passing baseline.
The fixture is never executed. No Git history is needed at test runtime.

Verification: the original seven cases pass. The separate pilot is retained only
as evidence, not duplicate collected tests. A focused rerun of the three current
Windows contract checks still fails all three; those results remain open. The
adjacent historical reconstruction family requires a larger multi-layer input
closure, not the identical byte-family repair, and was deliberately left unchanged.
No broad suite pass or runtime/security qualification is claimed by these repairs.
