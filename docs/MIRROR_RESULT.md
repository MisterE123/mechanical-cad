# Mirror Result: explicit reflected single solid

Current-source development capability; not an installed-package or GUI certificate.

In the Part workspace choose **Mirror Result**, select the source solid, and enter
its mirror plane. **XY**, **XZ** and **YZ** presets show a single signed
**Offset** field, along Z, Y or X respectively. New dialogs start on XY. Select
**Custom plane** for **Plane origin (mm)** (a point on the plane) and a nonzero
world-space **Plane normal**; its length does not matter:

- XY plane: normal `0, 0, 1`; use origin Z to offset it.
- XZ plane: normal `0, 1, 0`; use origin Y to offset it.
- YZ plane: normal `1, 0, 0`; use origin X to offset it.
- Other normals define tilted planes, for example `1, 1, 0`.

Offset and origin fields accept the existing typed lengths and parameter expressions.
Opening an existing feature recognizes axis-aligned literals or direct literal
parameters without rewriting them. Other formula-defined/tilted normals stay
Custom; text is never evaluated to guess a preset. Repeated drawing changes no
values. Explicitly selecting a preset sets its normal, preserving all origin
expressions (tangential components do not affect the preset plane). Switching
to Custom exposes the current values without resetting them. Normal
components accept scalar numbers/expressions, not lengths. The cyan creation
preview is exact sidecar geometry and leaves accepted geometry unchanged. Apply
performs a fresh guarded replay; Cancel discards the preview. Edit Feature can
change the source, plane expressions or name. Save/reopen retains canonical intent.
The existing Edit Feature dialog applies atomically, without live edit preview.

## Exactly what is produced

The result is **only the reflected solid**, not both the source and its copy.
The source remains in feature history. There is no automatic union, no unmodeled
multi-solid Part, and no negative Blender object scale. Reflection is a native
OCCT B-rep transform with one-solid validation. Use a separate explicit Union
with the historical source only when a joined symmetric solid is wanted; Union
still refuses disconnected solids and applies its own conservative topology rules.
This is not a half-body symmetry/fuse option, feature pattern, mirrored assembly
instance, or associative reference to an existing sketch plane. The datum plane
is explicit numeric/formula intent owned by the Mirror feature.

## Topology and orientation

One-to-one native Modified history can retain an already-stable source face ID.
Its role names describe authored faces, not current world extrema: a mirrored
`side.x_min` can now be on the world's positive-X side. IDs remain source-bound.
Split, unknown, merged or otherwise unstable source identities are not promoted.
Client evidence validation follows the actual base and verifies modifier lineage.
Normals are recomputed from the output B-rep, including indirect reflected plane
frames, so a positive extrusion on a mirrored planar support points outward.

## Evidence and limits

`tests/integration/test_mirror_solid.py` checks XY/XZ/YZ and tilted/offset planes,
normal scaling/sign, exact bounds and volume, double reflection, outward normals,
strict v2/v3 transport and forged-source refusal, selected blends after upstream
edits, editing/replay, zero-normal
failure/blocking, outward face-attached extrusion after plane edits, actual split
refusal, STEP/STL checks and STEP reread, and reusable assembly capture.

`tests/blender_mirror_smoke.py` checks native Blender 5.2.2 creation invocation,
exact disposable previews and changed plane/preset, Cancel, invalid-normal refusal,
all three registered RNA preset callbacks, non-mutating production dimension draws,
and expression-preserving Edit Feature initialization,
fresh Apply, save, an independent reopen process, Replay and Edit Feature.
Both phases report `MCAD_MIRROR_SMOKE_OK`. Tests use the shared sidecar runtime;
OCP is not imported inside Blender. These headless tests do not establish
interactive GPU/dialog usability, manual Undo/Redo, ZIP installation or Windows
qualification. No release archive is created by this work.

Bounded verification on this worktree: all 14 Mirror integration cases passed;
94 connected-solid/transport/Cut-lineage/edit tests and 108 adjacent
boolean/support/pattern/unit-input/dialog tests passed in separate runs (these
runs overlap, so counts are not additive). Ruff and diff whitespace checks pass.
A broad unit sweep was interrupted after historical fixture failures: the first
`test_arc_downstream_barriers.py` import error (`bpy.props.IntProperty` absent from
its fake module) was reproduced on the unchanged integration baseline. This is
not a complete historical-suite pass claim.

Preset follow-up verification: 13 focused pure UI tests and 14 Mirror native
integration cases pass together. The expanded native Blender smoke exercises
registered XY/XZ/YZ callbacks and plane geometry, draw/change/Cancel, plus a
separate reopen phase. Expanded preset save-phase checks passed. The new
reopen/initialization assertions remain pending: both shared Python and Blender
stalled before startup output during the follow-up, and the owned checks were
retired. The earlier base Mirror two-process save/reopen check passed. No broad
historical suite was rerun for the UI follow-up.
