# Multiple planar Shell openings

Development source capability, not a newly delivered package or general topology
naming claim. Shell can remove one or more explicitly selected stable planar
faces while hollowing a single solid inward.

## Create and edit

- Shell's viewport tool keeps the one-click single-opening workflow. Shift-click
  to collect several openings on the same solid, then Enter to review thickness
  and the explicit selection. Click a selected face again while collecting to
  remove it. Chosen faces stay orange while orbiting; the hovered face is cyan.
  These depth-tested overlays are guarded disposable display feedback, not naming
  authority, and disappear on deselection, stale display, Cancel or completion.
  Escape cancels without changing the accepted Part.
- In the Shell dialog, use Open mode and the checked list of stable planar faces.
  Review every checked opening before Apply. Closed cavity removes none.
- Edit Feature restores the whole opening list. Change the checked faces or use
  viewport reselection, then Apply. Expressions such as `wall` remain supported.
- A face that is missing, split, ambiguous or no longer planar is an error, not a
  request to guess its replacement. Explicitly select the intended current face.

The list is bounded to 64 distinct semantic IDs. All must resolve uniquely in the
selected base. One invalid face rejects the entire operation. OCCT must return a
valid closed single-solid B-rep with positive reduced volume; thickness or opening
combinations that cannot do so are rejected. The add-on still stages a complete
Part replay and publishes atomically only after validation. Cancellation or a
failed operation must leave the accepted Part untouched.

## Naming and compatibility

The existing `opening_faces` JSON field now accepts multiple IDs. Omission still
means the original closed-cavity operation; a singleton retains the exact old
schema and `shell.opening_lip` construction role. Existing files are not migrated.
Multiple openings use `shell.opening_lip.<SHA-256 of source ID>` for each provably
unique rim, independent of list order. Inner walls keep source-derived identities.
Native Modified/Generated ancestry and source/image collision checks remain the
only authority. Missing or nonunique rim history remains unresolved.

Changing between one and multiple openings changes the rim naming mode. Existing
references to the old single lip can therefore need explicit repair. This is
visible failure, never a nearest-face rebound. Untouched outside and source-bound
inner faces retain their proven histories where native geometry permits it.

## Example and evidence

`examples/multiple_opening_shell.mcad.json` is a 20 × 15 × 10 mm sleeve with both
end faces removed and a named 1 mm wall. Exact material volume is 660 mm³.

Focused native tests cover opposite, adjacent and three selected openings, point
classification of empty openings and retained walls, one-solid validity, exact
volumes, dimension/thickness edits, JSON round trips, order-independent rim IDs,
strict result v2/v3 transport, forged ancestry rejection, duplicate/oversized lists,
missing/split/aliased identities and unchanged single-opening/closed-cavity tests.
See `tests/integration/test_multiple_shell_openings.py` and the existing Shell
integration tests. Blender operator smoke coverage and exact commands/results
are recorded with the implementation checkpoint.

Curved openings, arbitrary imported/unstable face naming, offset self-intersection
repair and general hollowing topology are not claimed. Headless operator coverage
is not interactive mouse, Undo/Redo, installed-package or Windows qualification.

### Focused checkpoint checks

Using the existing Linux `cad_runtime/dev-venv/bin/python`:

- 138 passed: `test_multiple_shell_openings.py`, `test_open_shell.py`,
  `test_open_shell_lineage.py`, `test_shell_generated_surfaces.py`,
  `test_connected_solid_features.py`, `test_connected_feature_contracts.py`
  under `tests/integration/`.
- 289 passed: `test_model.py`, `test_result_v3_client.py`,
  `test_part_snapshot_v2.py`, `test_solid_dialog_values.py` under `tests/unit/`.
- An additional broader probe of `test_geometry_result_v3.py` returned 435 passed
  and 14 failed. All 14 failures reproduce on unchanged base `676fb8e`; they concern
  pre-existing unsupported-source/endpoint contract expectations, not Shell.
- Ruff passes on changed Python files; `git diff --check` passes.

This was intentionally a focused implementation checkpoint, not a full-suite,
ZIP-install or interactive desktop qualification run.

Native Blender 5.2.2 Linux, sidecar-only kernel, `--python-exit-code 1`:

- `tests/blender_multiple_shell_smoke.py` create and separate-process reopen:
  `MCAD_MULTIPLE_SHELL_CREATE_OK`, `MCAD_MULTIPLE_SHELL_REOPEN_OK`.
- `tests/blender_open_shell_smoke.py` legacy create and separate-process reopen:
  `MCAD_OPEN_SHELL_CREATE_OK`, `MCAD_OPEN_SHELL_REOPEN_OK`.
- Existing solid reselection smoke passed. New smoke covers actual operator
  creation/editing, checked-list helpers, missing selected identity visibility,
  empty/duplicate/missing/invalid-thickness atomic refusal, modal multi-selection
  toggle/Enter/Escape and cancelled reselection. Modal events use controlled
  picker doubles, so real mouse hit-testing usability is not established.
- 48 focused pure selection/dialog/guidance/extrusion tests passed.
- The broader arc UI availability probe has 38 failures/25 passes. The exact 38
  failures also reproduce on a clean archive of the unchanged base; this feature
  only adds required RNA property stubs to its fixture, not unrelated repairs.

The normal `scripts/run_checks.sh` native phase now includes the multiple-Shell
save/reopen smoke. No packaged release, public push, desktop or Windows testing
was performed for this checkpoint.

### Persistent selection feedback follow-up

Selected opening faces remain orange during hover changes and viewport navigation;
cyan remains the transient hover tint. Capture and each draw validate the same
bound source object against its exact replay display. Modified/stale display
clears feedback, and close/deselection releases retained triangles. The semantic
opening list, not overlay geometry, remains the only authored selection.

Native `MCAD_MULTIPLE_SHELL_FEEDBACK_OK` covers real FacePicker/HoverSnapshot
binding and selected cap triangles, navigation/hover persistence, one/all
removal, orange/cyan GPU call arguments, edited-display refusal, dirty-state
clearing and timer/handler cleanup. GPU drawing is mocked in that smoke; actual
mouse and rendered tint checks are still separate GUI work. Multiple Shell
create/reopen markers pass after this change. A focused picker/owner run passes
70 tests; two broader AST expectations on unchanged edge-picker modules fail
(the files and test are identical to base `676fb8e`).

### Navigation gizmo passthrough correction

The GUI check found that the picker swallowed navigation-gizmo drags. Shell
creation/reselection now pass through no-face pointer movement/releases and
reserve the visible native navigation footprint before any face ray cast. A
UI-started drag remains passthrough after leaving that footprint. A new press
resets a prior drag even if Blender consumed its release, and normal acceptance
still freshly validates the exact bound face display.

The footprint follows the viewport's current region origin, right sidebar and
top overlays, UI scale, navigation visibility and user-selected gizmo size. It
reserves no space when navigation gizmos are hidden. This is conservative UI
exclusion, not a gizmo/geometry hit test or automatic face selection. No fixed
screen coordinates from the reproducer are used.

Layout reference: [Blender v5.0.0 view3d_gizmo_navigate.cc](https://github.com/blender/blender/blob/v5.0.0/source/blender/editors/space_view3d/view3d_gizmo_navigate.cc),
`GIZMO_OFFSET=10`, `GIZMO_MINI_SIZE=28`, `GIZMO_MINI_OFFSET=2` and
`WIDGETGROUP_navigate_draw_prepare`. The same constants were checked in upstream
main on 2026-10-24, whose axis spacing is 2.2 versus v5.0.0's 2.1; the conservative
reservation includes both. Minimal-axis spacing likewise reserves both layouts.
The inspected runtime is Blender 5.2.2 build d13f752e3b9c; the exact native gizmo
hit map is not exposed by its Python RNA. Actual mouse retesting is separate.

11 pure tests cover hidden/axis-only modes, multiple UI scales, region origins,
sidebar width/top overlay changes, drag exit/release and consumed-release reset.
Native multiple-Shell create/reopen and face-pick markers pass. Controlled event
coverage asserts navigation never invokes face hover/acceptance or changes the
selected IDs, while orange overlays persist. The same actual GUI drag must still
be rechecked before claiming the reported usability bug is resolved visually.
