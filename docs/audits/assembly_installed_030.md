# Installed 0.3 assembly preview: final GUI receipt

Reviewed 2026-10-16 using native Blender **5.2.2 LTS**, build `d13f752e3b9c`,
on Linux x86_64. This receipt qualifies the exact released package and separates
its scope from the earlier [source GUI review](assembly_authoring_gui.md).

## Immutable release identity

- Source: `1431ecd250a504ddc5b1066b57d8ea31baaabc14`, 38 local commits.
- Add-on ZIP SHA-256:
  `09f40cbba5ff3ef5e002456388b9cada45ccbb255cf0400acc25c595d50519cc`.
- Complete preview ZIP: 4,904,323 bytes, SHA-256
  `a315fbec83eceb395e73251b0ee780a9d592ceb80094743fc6bff7d40f115c59`.
- Actual installed-GUI `.blend` SHA-256:
  `3711faa5ebc29f5ffcb813b05c81a74cc67f545002a1bab6a5ed0b807ad94f63`.

The complete archive contains source, full Git history, installable add-on,
canonical clevis documents, individual STEP/STL exports, native GUI scene,
screenshots and verification evidence. All 102 payload hashes were independently
read back. Released files remain unchanged; this later documentation commit does
not retroactively change the package's source identity.

## Method

Native Preferences **Install from Disk** and Enable used a fresh isolated profile.
Preferences showed version 0.3.0. Every one of the 567 installed archive members
matched the frozen ZIP. The backend used a clean extraction of the same source
revision and the pinned CPython 3.12.14 sidecar environment.

The reviewer reopened the authentic source-authored guide-pair scene and saved a
distinct installed-package copy. No source add-on imports, scripted authoring or
artificial process delay were used. Read-only observation captured accepted JSON,
display transforms, viewport membership and hide flags after native actions.

## Verified native interactions

1. **Focus Part / Whole Scene:** the visible buttons isolated only the working
   Part and restored the full view locally. Every other viewport's framing and
   membership, and all objects' hide flags, remained unchanged.
2. **Reuse and fixed joint:** a third named instance reused the existing Part.
   Its named fixed joint had no coordinate or limits, and its accepted transform
   matched the explicitly selected parent and literal origin frames.
3. **Revolute joint:** a fourth reused instance accepted a named hinge at 45° with
   explicit 0–90° limits. Canonical values were π/4 and [0, π/2] radians, with
   the expected right-hand local-Z rotation.
4. **Current-pose check:** the intentionally coincident fixed follower and rotated
   hinge produced complete evidence with `passed=false` and known interference.
   The original pair retained its 14 mm gap against the 2 mm requirement.
   Coincident overlap was approximately 512 mm³; rotated overlap approximately
   129.650134 mm³. These are negative controls, not clearance-passing designs.
5. **Listed samples:** slider positions 0 through 31 mm produced 192 pair checks
   across 32 poses. Evidence reported interference, clearance violation and
   threshold contact, with explicit discrete-pose scope. Authored coordinates and
   accepted geometry stayed unchanged.
6. **Actual mouse Cancel Check:** one click on the live enabled button at about
   2.2 seconds cancelled the repeated request. Exact accepted Part/Assembly JSON,
   all recorded objects, report bytes, verification status/message and display
   status were preserved. No Escape or programmatic cancellation established this
   pass. Earlier timing-limited attempts that finished first were not counted.
7. **Native save:** the final `.blend` retained four instances and all three joint
   kinds. One follower is coincident, so four instances do not produce four
   separated silhouettes. Reopening requires Replay and explicit Check to restore
   runtime trust in persisted geometry/evidence.

## Evidence in the complete archive

- `evidence/installed-gui-receipt.md`: detailed original receipt.
- `evidence/installed-gui/gui-identity.json`: exact package/scene identity.
- `evidence/installed-gui/gui-focus-comparison.json` and
  `gui-mouse-cancel-comparison.json`: read-only preservation assertions.
- `screenshots/02-focus-part.png`, `04-fixed-authoring.png`,
  `05-revolute-authoring.png`, `11-final-mouse-cancel.png` and
  `13-final-installed-assembly.png`: actual native views.
- `examples/installed-authoring-check.blend`: deliberate-overlap authoring scene.
- `examples/clevis_hinge/`: separate editable positive-clearance benchmark.

## Qualification limits

The installed gate reused the genuine source-authored Part. It did not repeat the
entire sketch/extrude, upstream all-instance Update, Undo/Redo and fresh-process
reopen sequence; those remain separately recorded source-loaded GUI evidence.

F3 searches did not expose the CAD Focus command in the tested Part context.
Use the verified visible **Focus Part / Whole Scene** controls. Narrow labels can
truncate, default Properties/Outliner occupy substantial space, and unselected
datum axes have weak contrast. Broad themes, HiDPI, input devices and keymaps were
not qualified. Windows/macOS and later Blender versions remain untested.

This is bounded rooted-tree assembly authoring with literal frames and exact
listed-pose checks. It does not establish general closed-loop solving, continuous
collision freedom, physical-fit, structural/load or manufacturing certification.
