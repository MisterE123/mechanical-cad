# 1.26.0 Linux feature checkpoint

This separate checkpoint follows frozen Linux 1.25.0. All earlier source tags
and artifacts remain unchanged.

## Changes

- Adjacent Sketch Corner Fillets support all four corners with unequal radii.
  Version-2 explicit reciprocal arc intent retains original corner/outer witnesses.
  Independent core and add-on validation enforce shared tangent ordering and
  separation, not merely each tangent's individual interior bound.
- Restore Sharp Corner removes only the selected explicit fillet's owned
  geometry and required relations. Peer intents update atomically; original
  dimensions and historical unavailable radius-label placement remain intact.
  A detached candidate must preserve every retained solved point within 1e-7 mm.
  Consumed sketches also require successful full replay before acceptance.
  No hidden anchors or expression rewrites are introduced.
- Cancel, stale dialogs and rejected trials preserve accepted authoring and
  canonical Part data. Normal Finish still performs complete Part validation.
  See [fillet scope](SKETCH_CORNER_FILLET.md), [adjacent intent ADR](adr/0010-explicit-adjacent-sketch-fillets.md)
  and [restoration ADR](adr/0011-explicit-sketch-fillet-removal.md).
- Legacy documents are unchanged. Strict older readers reject version-2 intent
  and new adjacent/removal journal opcodes; there is no silent downgrade.
- Sketch relation availability uses cheap, non-authoritative hints instead of
  capturing full transaction snapshots during palette polling. Invocation and
  Apply retain their fresh binding checks; no broad authority cache is added.
  See [bounded query and interaction evidence](PALETTE_APPLICABILITY_PERFORMANCE.md).

## Evidence boundaries

This scope document is not a passing receipt. The companion qualification receipt
must identify exact committed source, installer hash, installed module provenance,
runtime bytes/modes, and checks actually completed. Bounded installed validation
covers all-four unequal fillets, valid editing, overlap refusal preserving the
original, one/all-corner restoration, guarded native solid volume, Cancel/stale/
refusal, strict save/reopen, and historical annotation behavior. Actual installed
GUI creation and Restore controls are separate from source-loaded evidence,
scripted fixture setup and background operator checks.
Native OCP and libslvs stay in the sidecar, never inside Blender.

No full historical/boundary suite, exhaustive GUI/Undo, Windows 1.26,
manufacturing certification or zero-loss guarantee is claimed. The intermittent
native allocator crash, earlier unclassified suite failures and historical authority
inventory failures remain unresolved. Earlier test-run storage exhaustion was
recovered without deleting retained evidence; that does not qualify the broad suite.
Optional local
recovery remains OFF by default, unencrypted, bounded and best effort. Continue
ordinary file saves. Prior float32-display, no-DISPLAY and premature GUI-observer
diagnostics were harness issues, not source fixes.

## Retained runtime and materials

The builder retains all 1,030 external runtime files and modes and original
runtime lock bytes from verified Linux 1.18. Only project source and trusted
bootstrap are substituted. Historical source/materials remain historical; current
source, notices and provenance are appended. No development environment is
shipped. The native pin remains cadquery-ocp-novtk 8.0.1.1.0. Dependency source
correspondence, recipient rebuild and legal clearance are not established.
