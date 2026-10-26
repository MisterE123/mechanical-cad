# 0.6.0 bounded arc build/edit/save preview

Status: candidate preparation. Full regression and exact installed manual-GUI
qualification are still pending. **0.5.2 remains the latest delivered usable
release.** No previously delivered archive is replaced.

## Bounded scope

The existing General editor gains explicit arc-format opt-in, Center Arc's
center/start/end inputs, exact existing-point identity selection, finite directed
arc display/picking, Reverse Sweep, radius editing and local Undo/Redo. The
supported solid path is one arc with two shared-ID radial lines, explicitly fixed
center, H/V and radius constraints, then Finish and one extrusion. Radius and
extrusion height are limited to 1–1000 mm in the reviewed XY, zero-origin domain.
Incomplete arcs remain editable/suspendable drafts rather than finishable Parts.

The raw third input is retained as authored. The provisional circle and observed
point disclose any discrepancy. Check may move unconstrained solved points; no
hidden projection or constraint is inserted into the authored sketch. Resume
restores pure intent and raw input, never pointer capture or current evidence.

**Arc Geometry Check, STEP/STL export and Assembly capture/update remain blocked.**
Existing supported result2 Assembly sources remain reusable. This is a bounded
build/edit/save preview, not a manufacturing-ready arc workflow or a general
mixed line/arc region editor. Multiple arcs, holes, trim/extend, tangent/equal
editing, arbitrary planes and a broad constraint editor remain out of scope.

## Recoverable native limitation

A successful sketch solve and pure profile-readiness check can still be rejected
by the conservative native periodic-representation checks. Such a failure keeps
the draft/raw input and prior committed Part available for explicit editing,
Check, Undo, Suspend or Cancel. There is no automatic geometric repair or retry.
Solve success, profile readiness and native build status are shown separately.

## Compatibility and verification

Update the source root and add-on together. Per-operation guarded evidence,
nonce/source/owner binding, once-only publication and lifecycle revocation remain
in force. Old or mismatched backends cannot supply current arc evidence. Legacy
document/draft codecs remain exact. Arc-format opt-in is explicit; cancelling its
confirmation preserves the prior draft bytes. Undo reverses accepted geometry
commands while retaining the explicitly enabled draft-format capability.

Gate C has passed its independently reviewed bounded automated editor/owner and
two-process persistence qualification. The 0.6.0 change after that milestone is
release metadata only; all functional core/kernel/solver/service bytes remain
unchanged. Final full-suite, native exit and installed manual-GUI results will be
recorded separately before any usable-release claim. See
[the milestone record](ARC_AUTHORING_OWNER_MILESTONE.md) and
[the workflow](GENERAL_SKETCH_WORKFLOW.md).
