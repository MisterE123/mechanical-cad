# 1.24.0 Linux usability checkpoint

This separate checkpoint follows frozen Linux 1.23.1. The failed, undelivered
1.23.0 candidate and all earlier source tags and artifacts remain unchanged.

## Changes

- Circle center → Tab accepts a positive literal/unit diameter and creates a
  circle plus canonical radius driver atomically after fresh native validation.
  Creation formulas are not supported. See [Circle input](PENDING_CIRCLE_DIAMETER.md).
- Diameter-displayed annotation edits use the explicit Diameter dialog. Literal
  diameter edits retain numeric canonical radius; formulas and untouched/no-op
  expressions preserve their documented meaning. Ordinary radius annotations and
  retained raw radius edits are not silently reinterpreted. See
  [Diameter editing](DIAMETER_EDITING.md).
- Optional local recovery keeps routine controls compact and puts explanatory
  text under explicit details. Recovery still defaults OFF, writes unencrypted
  bounded local copies only after opt-in, and restores into a new unsaved Scene.
  See [recovery limits](LOCAL_RECOVERY.md).

## Evidence boundaries

This scope document is not a passing test receipt. The companion qualification
receipt must identify the exact committed source and installer hashes, installed
module provenance, installed/runtime bytes and modes, and checks actually run.
The intended bounded check covers ordinary Part edit/Check/save/reopen, Circle
creation/diameter edit/save/reopen, default-off no-write, and combined unsaved
Part plus accepted sketch and pending raw diameter recovery in separate processes.
Actual installed GUI diameter popup and compact recovery controls are required
and recorded separately; synthetic/background popups are not GUI evidence.
Native kernels stay in the isolated sidecar, never inside Blender.

No full inherited or boundary/history suite, exhaustive GUI/Undo, Windows 1.24,
manufacturing certification or zero-loss guarantee is claimed. The intermittent
native allocator crash, earlier unclassified suite failures, and historical
storage exhaustion remain unresolved. Older installers cannot Resume the new
pending diameter intent or journal opcode. Continue saving ordinary files.

## Retained runtime and materials

The builder retains all 1,030 external runtime files and modes plus original
runtime lock bytes from verified Linux 1.18. Only project source and trusted
bootstrap are substituted. Historical source/materials stay historical; current
source, notices and provenance are appended. No development virtual environment
is shipped. The native pin remains cadquery-ocp-novtk 8.0.1.1.0. Dependency
source correspondence, recipient rebuild and legal clearance are not established.
