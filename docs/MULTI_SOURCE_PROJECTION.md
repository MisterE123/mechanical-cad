# Multiple explicit sources in one drawn sketch

A drawn sketch can keep projected construction geometry from several earlier
sketches and solids. Each reference stays bound to the source explicitly chosen
when it was added. Equal face labels on different solid bodies are not the same
reference. Upstream changes regenerate every source; missing or ambiguous
references fail visibly rather than choosing nearby geometry.

## Project Geometry

In a live drawn sketch, use **Project Geometry**, choose an earlier drawn sketch
and its entity, then repeat with another earlier sketch. Existing target IDs,
constraints, formulas and projections are retained. Sources must precede the
target sketch in feature history.

## Use Solid Edge: choose an earlier solid

In the live drawn sketch, use **Use Solid Edge**, choose a **Source solid**, then
**Pick Edge**. The chooser shows each eligible earlier solid's feature label and
ID, defaulting to the current active output when it is eligible. The selected
source is also named while picking. Click one supported straight edge or full
circle to add source-linked construction geometry and return to the same sketch.
Repeat with a different solid without Finish, changing active output or reopening.

The temporary picking body belongs only to that captured source. It reuses the
exact owned input-body review lifecycle used by feature reselection, including
native semantic edge evidence and full display integrity checks. Canonical JSON,
active output and accepted runtime are never replaced. Only the owned final CAD
display is temporarily hidden; unrelated objects are unchanged. Viewport
navigation remains available, and the sketch's existing geometry and annotation
state are retained. Esc/right-click returns without changing the draft or Undo.

The picker restores prior visibility, selection and active-object state when it
finishes or is cancelled. A changed sketch revision, saved draft, source document,
accepted runtime, backend, units or viewport context rejects the pending pick and
releases its temporary body. Save and owner teardown also retire the review.
The review body is not accepted geometry, persistent identity or an export source.

Only successful earlier typed solids are eligible. Picking still requires a
current fully replayed Part and a unique supported semantic edge; hidden arbitrary
scene meshes, ambiguous edges and oblique circular projections are not supported.
The source-development [circular-arc extension](SOLID_ARC_PROJECTION.md) uses this
same picker with explicit stable endpoint identities; its focused native checks pass, while Blender/GUI qualification
is still pending. Existing single-active-display picking remains supported by the
shared picker, without introducing an automatic source substitution. A sketch may
combine these solid references with **Project Geometry** sketch references.

## Repair and reversibility

The reference-repair dialog offers replacements from the selected reference's
bound source only. A repair cannot silently move to another source, even if its
edge has the same semantic labels. If several references break, supported repairs
can be kept one at a time in the unapplied proposal. **Undo Proposal Repair**
reverses proposal progress; ordinary Blender Undo remains full-model history.
The accepted model changes only after the complete candidate succeeds. See
[staged repair policy](STAGED_EDIT_REPAIR.md) for discard, save and invalidation.

## Verification and limits

Focused native geometry tests cover mixed source kinds, identical face labels on
two solids, independent evidence validation, persistence, upstream edits,
missing/forward/cyclic sources, and exact-source replacement. Headless Blender
checks exercise registered authoring controls and multi-source sequential repair.
These checks do not establish real-GUI usability or platform compatibility.

The extension uses optional per-row source ports, not a document migration;
legacy single-source rows keep their original meaning. See
[ADR 0009](adr/0009-explicit-projection-source-ports.md) for the wire contract.

Focused regression entry points:

- `tests/integration/test_multi_source_projection.py`: native geometry, save/load,
  sidecar solve/replay, source-qualified evidence, invalid bindings and legacy rows.
- `tests/integration/test_projection_authoring.py` and
  `tests/unit/test_solid_projection_owner.py`: source allocation and fresh owner
  evidence, including stale-source rejection.
- `tests/unit/test_projection_repair_ui.py` and `tests/unit/test_staged_edit.py`:
  same-label source filtering and refusal to move a repair to another port.
- `tests/blender_multi_source_authoring_smoke.py`: registered two-sketch/three-solid
  line/circle controls, same-session source switching, owned-display restoration, stale-unit
  cleanup, unchanged accepted runtime, draft Resume/Undo/Redo and two-process
  `.blend` persistence without a saved temporary body.
- `tests/blender_multi_source_repair_smoke.py`: fresh native sequential repair,
  stale dialogs, proposal Undo and automatic whole-model Undo/Redo rebuild.

Native scripts require `MCAD_ROOT` pointing at the source checkout and
`MCAD_PYTHON` pointing at a Python with the native backend dependencies. Run
Blender with `--background --factory-startup --python-exit-code 1 --python` and the
script path. The authoring test launches one fresh Blender process to verify
saved multi-source intent and Resume. Success markers are
`MCAD_MULTI_SOURCE_AUTHORING_SMOKE_OK`, `MCAD_EARLIER_SOLID_REOPEN_OK` and
`MCAD_MULTI_SOURCE_REPAIR_OK` (19 repair checks).
