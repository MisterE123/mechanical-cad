# Sketch, Part, and Assembly workspace blueprint

Status: architecture plus initial implementation and native API/UI evidence,
2026-10-16. The integrated modeling workflow still requires its release GUI gate. It refines Stage 2 of [ROADMAP.md](ROADMAP.md) and keeps the
acceptance contract in [UX.md](UX.md). The next deliverable must let someone draw
and edit a part, rather than merely rearrange the current form controls.

## Decision

Build **three actual workspace tabs: Sketch, Part, and Assembly**, as explicitly
requested by the user. Each has its own menus, layout, and tools; all share the
same canonical CAD design. Blender remains in its supported Object Mode. Use the
existing feature graph, exact sidecar, and document transactions. A true new
native Object Mode alongside Edit/Pose is not a Python add-on extension point in
the tested Blender 5.2.2 LTS runtime.

The tabs organize a single CAD workflow; tabs and menus alone are not acceptance.
The next working flow is viewport sketch → preview/dimensions/Cancel → commit →
Part extrusion → upstream edit and downstream rebuild.

Do not fork Blender for the requested interaction. Revisit a core contribution
only if a later requirement actually needs a new native object type/editor/mode,
or measured limitations remain after the supported workspace/tool/gizmo approach.
A fork adds custom builds, platform packaging, compatibility work, and ongoing
upstream merges; it does not itself solve constraints, feature identity, or CAD
kernel integration.

Do not disguise Sketch as Blender mesh Edit Mode. The generated mesh is still a
cache. The active workspace and header identify `Sketch`, `Part`, or `Assembly`, with
an obvious Finish/Cancel when editing. A workspace role is separate from transient
tool/draft state; a dropdown inside one workspace does not satisfy this design. Do not replace Blender's mode enum or globally overwrite its header,
keymap, or tool registry.

## Verified extension boundaries

Primary evidence is actual `bpy 5.2.2 LTS`, build `d13f752e3b9c`, plus installed
Blender Python source. Official online 5.2 API pages failed retrieval during this
investigation; that is a research limitation, not evidence that an API is absent.

- `Object.mode` and `Context.mode` report read-only RNA enums. `object.mode_set`
  accepts the existing native modes, filtered for the active object. Passing `CAD`
  raises an invalid-enum error. Registering a `WorkSpaceTool` with
  `bl_context_mode='CAD'` raises `KeyError: 'CAD'`; registering/unregistering the
  identical tool in `OBJECT` succeeds.
- `bpy.utils.register_tool` inserts into an existing editor/mode tool list. Its
  public conversion has no per-workspace tool `poll` callback. Operator `poll`
  can prevent execution outside CAD, but does not remove the tool icon from
  other Object Mode workspaces.
- `Panel.poll`, `GizmoGroup.poll`, and conditional header draw callbacks can
  scope our UI. `SpaceView3D.show_region_toolbar` and `show_region_ui` are
  per-space properties. Native `GIZMO_GT_button_2d` supports operator targets;
  exact 5.2.2 source and its native GUI expose `icon_value` for custom PNG icon
  previews. Hover descriptions, click dispatch and native UI scaling were tested.
  Native 4.3.2 lacks that custom-gizmo icon API; built-in icons are its fallback.
- `SpaceView3D.draw_handler_add` supports 3D geometry (`POST_VIEW`) and
  screen-space dimensions (`POST_PIXEL`). These callbacks are space-wide, so our
  draw function must check the owning window, area, workspace, and document.
- `workspace.duplicate` and role switching pass actual 5.2.2 window/event-loop
  tests, including repeated setup and fresh-process save/reopen. Several native
  transitions in one Python callback caused a reproducible screen/layout mismatch
  crash. The implementation issues one transition per timer step and checks the
  resulting window workspace before configuring it.
- `Region.active_panel_category` is dynamically read-only before the sidebar has
  drawn its categories. The new-workspace setup waits for a separate post-draw
  phase before selecting CAD. `SpaceView3D.show_region_asset_shelf` can also be
  dynamically read-only; setup does not assign it. Merely inspecting static RNA
  property metadata is insufficient.
- Do not assume a new arbitrary Blender editor type can be registered in Python.

Sources:

- [Blender 5.2.2 release artifacts](https://download.blender.org/release/Blender5.2/).
- [5.2.2 built-in object mode definitions](https://github.com/blender/blender/blob/v5.2.2/source/blender/makesrna/intern/rna_object.cc).
- [5.2.2 tool registration implementation](https://github.com/blender/blender/blob/v5.2.2/scripts/modules/bpy/utils/__init__.py).
- [Exact 5.2.2 native button gizmo](https://github.com/blender/blender/blob/v5.2.2/source/blender/editors/gizmo_library/gizmo_types/button2d_gizmo.cc).
- [Exact 5.2.2 region/category initialization](https://github.com/blender/blender/blob/v5.2.2/source/blender/makesrna/intern/rna_screen.cc).
- [Exact 5.2.2 workspace duplication and reorder operators](https://github.com/blender/blender/blob/v5.2.2/source/blender/editors/screen/workspace_edit.cc).
- [Official native tool-icon format/exporter](https://github.com/blender/blender/blob/main/release/datafiles/blender_icons_geom.py).
- Target runtime scripts inspected: `bpy/utils/__init__.py`,
  `bl_ui/space_toolsystem_common.py`, `bl_ui/space_toolsystem_toolbar.py`.
  Native 4.3.2 templates inspected separately: `ui_tool_simple.py`,
  `operator_modal_draw.py`, `operator_modal_view3d.py`, and `gizmo_operator.py`.
  Those older templates do not constitute 5.2 GUI verification.

## Choose the smallest native UI that meets the design

### A. Registered native WorkSpaceTool group

Advantages: stock toolbar selection/hover/active affordances, native keymap
integration and tool settings, minimal bespoke interaction code. Original icons
can be compiled to Blender `.dat` triangle icons; PNG preview IDs are not accepted
as `bl_icon`. This is a separate asset build path.

Tradeoff: tools are shared by Object Mode, not restricted to the CAD workspace;
operator polls can reject unsupported execution, but the icons remain present.
Stock tools also remain. Do not modify private `VIEW3D_PT_tools_active._tools` or
monkeypatch its context generator to pretend the API isolates them.

### B. Workspace-scoped native 2D gizmo palette

Advantages: true workspace/state visibility through `GizmoGroup.poll`; custom
icons via preview `icon_value` when supported; native gizmo hit testing and operator
tooltips. The stock toolbar can be hidden only in the CAD viewport. This avoids
an entire custom GPU widget toolkit.

Tradeoff: we own placement, active-state styling, theme/DPI handling, visibility
when gizmos are hidden, and interactions with an active modal tool. Retain a
native menu/tool-search route for every action. Optional learning labels and
keyboard discoverability must be explicitly tested; hover alone is insufficient.

**Selected route: B**, after the native 5.2.2 spike. It meets the requested
workspace-specific contextual palette without changing Blender's global tools.
`workspace_ui.py` uses native buttons, plus one inert backing rectangle for
contrast. Header actions, a named CAD menu and the history panel's Tools & Document
menu remain accessible when gizmos are hidden or the viewport is too short.
The ordinary registered-tool route remains a valid alternative, but only its
registration/icon loading—not its full live toolbar behavior—was established by
this probe. No private tool-list or built-in-header monkeypatch is used.

### Isolated spike and exact evidence

Development-only probe lives outside the add-on at
`cad_workspace_spike/probe_workspace_ui.py` in the working project area. It creates
three separate Sketch/Part/Assembly probe workspaces, compares both palettes, and uses the same two
shape actions. It draws temporary XY profiles with live dimensions, allows
navigation, and cleans the preview on Esc or completion. It does not write a CAD
model, create a mesh, test Undo, or establish full sketch-editor functionality.

`build_probe_icons.py` converts the two existing PNG glyphs into triangle icon
files solely to test native loading. This is prototype raster tessellation,
not the production vector exporter. Original icon source/provenance remains in the
asset pack. A production icon pipeline should triangulate the original vectors.

Verified independently on target `bpy 5.2.2 LTS` and native background Blender
`4.3.2`: class/tool registration, custom `.dat` icon loading, and unregister cleanup
all pass. Headless PNG preview IDs are zero; that alone is not rendering evidence.
The subsequently obtained official native 5.2.2 build was SHA-256 verified and
used for the GUI tests below.

The GUI reviewer must record each separately:

1. Both custom glyphs render and remain distinct at ordinary and enlarged scale.
2. Hover describes the action and required input; active selection is clear.
3. Clicking the second tool changes the action once, without beginning an
   unrelated drawing or changing a model.
4. Mouse navigation works both idle and during a preview; it neither commits nor
   cancels the preview. Test middle mouse, wheel, trackpad where available, and
   the relevant default/Industry Compatible keymaps.
5. Esc removes all draw handles/previews; repeated activation does not accumulate
   handlers. Window/workspace changes do not leave an invisible modal operator.
6. Switching away from CAD hides B but leaves A visible as expected; operator
   polls prevent A from acting on unrelated scenes. Document this tradeoff.
7. UI scaling, light/dark themes, narrow viewports, resized sidebar, and hidden
   gizmos leave a discoverable way to use and exit the tools.

Native 5.2.2 observed results:

- Custom PNG glyphs render, click selection updates, and the native hover tooltip
  uses the action-specific description.
- Actual Blender Resolution Scale 1.0 and 2.0 scales the glyphs and hit targets.
  Increasing only `Gizmo.scale_basis` enlarges the hit target/backdrop, not the
  glyph; exact source intentionally sizes 2D icons with `UI_SCALE_FAC`.
  The native icon path also hardcodes 0.6 alpha before hover. The integrated
  palette's normal-state glyphs were judged too small/faint at default scale;
  this remains a visual acceptance issue. The public native polygon `shape`
  path is being evaluated for full-alpha, scalable glyphs, with native hits and
  tooltips retained. An isolated eight-symbol vector conversion has offline
  geometry/fidelity checks, but is not integrated or native-GUI validated and is
  excluded from the 0.2 release.
- Live temporary circle preview and dimension labels render; wheel navigation
  passes through. Ten successive draw/Esc cycles each start/cancel once and leave
  no visible preview. Switching to the actual Part tab cancels and removes the
  preview; returning to Sketch leaves no ghost overlay.
- The original probe's placement overlapped viewport info and lacked contrast.
  That was explicitly rejected as production visual acceptance. The integrated
  palette is below viewport info with an opaque backing strip; a short viewport
  hides the whole palette and reserves no invisible click area.
- Integration fixture `scripts/blender_workspace_native_fixture.py` passes twelve
  checks in its create run and twelve in a fresh-process reopen run. These cover
  three tabs, an existing Sketch name collision, repeated setup, unchanged
  pre-existing layout flags, customized CAD layout retention, shared scene/JSON,
  saved role tags, and the injected draft-cancellation hook. The hook fixture is
  not a substitute for the real modal operator's GUI test.
- Initial setup now stages the public `workspace.reorder_to_front` operator for
  Assembly, Part, then Sketch after verified per-tick activation. The resulting
  first tabs are Sketch → Part → Assembly, followed by the original tabs in their
  previous relative order. Ordinary reentry leaves user ordering alone.
  A generic `temp_override(workspace=...)` did not redirect that operator to the
  intended target in the GUI; it still used the window's active workspace. The
  corrected extra phase passes headless execution and a fresh-process native
  5.2.2 visual check in both a 1180-pixel window and a maximized window. Active Part
  is visible without scrolling. This separate result is not included in the
  earlier twelve-check fixture; `workspace_front_tabs.png` records the final order.
  A generic request for the already-active role, with no callback or pending
  setup, is a no-op and preserves an active draft. Explicit callback/setup
  handoffs retain their documented cancellation behavior.

Evidence artifacts: `palette_normal.png`, `palette_probe_scale2.png`,
`palette_ui_scale2.png`, `workspace_integrated.png`, the probe event JSONL, and
`workspace-fixture-v3.create.json` / `.reopen.json`. They are development QA
artifacts, not product screenshots or shipped CAD models. Light theme, trackpad,
Industry Compatible keymap and multi-window drawing are still release checks.
Actual sketch commit/extrusion/upstream-edit/Undo behavior has a separate gate.

## Desired screen

- **Left:** a compact tool palette for the active workspace. Part initially offers
  New Sketch, Extrude, Cut, Check, and Export when those actions are actually
  available. Sketch initially offers Select, Rectangle, Circle, dimension editing,
  and Finish/Cancel. Do not show future Line/Trim/Mates as working controls.
- **Centre:** the part or sketch, selected entities, a visible origin/workplane,
  snap candidates, live dimensions, and transient operation preview. One short
  current-action hint is enough. Help remains optional and local.
- **Right:** feature history first, with names, operation glyphs, and compact
  ready/dirty/failed/blocked states. Selected history row and active output have
  different cues. The selected feature's small inspector appears below the list;
  named operands and editable dimensions stay readable. Full parameter tables and
  diagnostics are deliberate expansion, not the default wall of text.
- **Header:** the current workspace role, document name, units, and current operation's
  essential controls. Finish/Cancel is visible whenever a draft exists. A failed
  build has a readable reason and a route to correct it.

- **Sketch tab:** workplane-aligned viewport, contextual geometry/dimension tools,
  right feature history plus selected sketch inspector, and Finish Sketch/Cancel.
- **Part tab:** 3D part viewport, feature tools and handles, editable feature history,
  Check and Export. Selecting Edit Sketch opens that sketch in the Sketch tab;
  successful Finish Sketch returns to Part with the edited profile selected.
- **Assembly tab:** initially shows shared model context and a concise
  `Assembly tools are not implemented yet` explanation. Do not simulate component,
  mate, DoF, collision, or motion features with mesh parenting. The eventual tab
  gets component/instance tools, assembly relationships, and verification.

Keep Blender navigation and normal workspaces intact. An explicit Open CAD action
creates missing owned Sketch/Part/Assembly workspaces once and reuses them on
later entry. Tag each with add-on owner/version and a stable role, rather than
matching its editable name. Preserve existing user workspaces, including any
already named Sketch, Part, or Assembly; choose a nonconflicting display name.
Do not reset customized CAD layouts on every entry. Avoid splitting/joining the
user's existing screen.

All three tabs read the same document state/scene owner; there is no workspace-
specific copy of model JSON. A change in Sketch must be the exact change shown in
Part. Scene/window changes are explicit context changes, never permission to copy
or move unrelated geometry. The integration must handle multi-window context
without accidentally editing the other window's document. An optional application
template may eventually package the three default layouts, but is not needed to
add modeling behavior.

## Next milestone: draw a small part, not an empty shell

### W0: bounded interaction proof

Complete the palette comparison above and a real context-switch/cleanup test.
No schema changes, solver promises, or release UI. Integrate only the chosen
palette mechanism after evidence, using the behavior-preserving module split.

### W1: viewport-authoring vertical slice

Keep existing documents and rectangle/circle/extrude/cut replay compatible. The
approved first interactive path now uses the independently tested schema-2
constrained rectangle adapter: stable line/point IDs, horizontal/vertical
relations, width/depth dimensions and a fixed anchor. Deliver the three workspaces
**together with** this coherent end-to-end flow:

1. Open CAD in Part and create a document. New Sketch opens the actual Sketch
   workspace; choose the visibly labeled supported XY plane. Align the view
   for drawing. Do not imply arbitrary or face-attached planes exist yet.
2. Draw a rectangle with two clicks and live width/height. Type dimensions or
   expressions while drawing; a compact native input popup is acceptable if it
   keeps the preview and Cancel intact. Finish Sketch commits one profile
   transaction and returns to the actual Part workspace with that profile selected.
3. Extrude that selected profile with a normal-direction
   handle and visible numeric length; preview, confirm, and commit one feature.
4. Keep existing Extrude/Cut dialogs available with explicit named operands while
   their viewport handles are developed. The next shape slice adds direct circle
   drawing and radius editing. Do not present the legacy circle dialog as a
   finished viewport tool. Cut keeps finite-tool semantics, not a Through All label.
5. Edit Sketch from the Part history opens the original profile in Sketch, not
   a duplicate. Change its visible dimension, Finish Sketch, and return to the
   updated downstream Part result. Cancel preserves the previous part. Verify
   Undo/Redo, save, reopen, and repeat this cross-workspace edit loop.
6. Check and Export are discoverable in Part context. Hook only to verified
   canonical-replay/atomic-export actions; a stale visible mesh is never input.

Primitive dimensions remain geometry parameters, not general sketch constraints.
For the new constrained rectangle, display solver status/remaining DoF only from
an actual sidecar result bound to the current document snapshot. An outdated cache
must say verification is needed. Conflict IDs are diagnostic candidates, not
instructions to delete constraints. Grid/origin snap feedback remains transient
unless a real persistent relation is authored and shown.

### W2: integrate real constrained sketches

Broaden the tested sketch schema/solver adapter beyond the fixed rectangle:
explicit plane authoring, additional closed regions, driving/reference dimensions,
and interactive conflict/redundancy/remaining-DoF diagnostics. Add line/polyline and
additional constraints only with real solver coverage. Accepted inference becomes
an ordinary editable relation with provenance. Highlight a snap candidate before
commit and provide a visible way to reject it. Reuse the W1 workspace/session/UI;
do not build a second sketch UI around the solver.

Assemblies remain Stage 3. W1 includes the actual Assembly tab as an honest
scaffold, but no mates or motion claims. Tab creation is not assembly functionality.

## Implementation boundaries

Existing module owners after the behavior-preserving split:

- `document_state.py`: committed JSON, parameter updates, replay/transactions.
- `display.py`: disposable mesh, last-good cache, focus/local-view handling.
- `properties.py`, `operators.py`, `panels.py`, `help_ui.py`, `registration.py`:
  RNA and current UI lifecycle.

Initial implementation boundaries:

- `workspace.py`: idempotent three-workspace setup, role/owner identity, staged
  handoffs and new-layout initialization; no model edits. Public entry is
  `request_workspace(context, role, on_ready)`; callback receives a fresh viewport
  context after activation. `set_draft_handlers(query, cancel)` avoids a cyclic
  import, and `cancel_pending_setup()` cleans the owned timer.
- `workspace_ui.py`: scoped native gizmo palette, header/menu fallbacks, concise
  history/inspector and icon preview lifecycle. `is_palette_event(context, event)`
  shares its reserved rectangle with modal navigation/picking. Source/packaged
  icons load only from the explicit bundled manifest.
- `viewport_sketch.py`: per-window/area draft lifecycle, modal placement/editing,
  temporary geometry/dimension overlays, solver calls and one explicit commit.
- `sketch_draft.py`: pure draft state and canonical constrained-rectangle payloads.

Registration wires UI after its operators and tears it down before removing the
operators. Existing ordinary Blender workspaces keep the legacy CAD panel; owned
CAD workspaces show the compact history inspector instead.

A draft contains document ID and base content hash, selected feature/entity IDs,
plane, raw expressions and evaluated dimensions, draft geometry, validation
message, and owning window/area/scene. Temporary Python session state is not saved
as canonical CAD data and must never reuse `last_good_mesh`. Avoid long-lived RNA
pointers across Undo, file loads, or area destruction.

All model edits ultimately use one explicit document transaction, currently
`document_state._commit_candidate`, wrapped behind a narrow authoring interface.
Viewport picking resolves canonical feature/entity identity; mesh indices never
become persistent references. History selection only selects/inspects; changing
active output is a separate intentional action.

## Commit, cancellation, navigation, and Undo

- Mouse movement updates only the draft and preview. Never rebuild an exact solid
  from a draw callback. The current rectangle preview is analytic and makes no
  sidecar calls on pointer movement. Solving happens synchronously at explicit
  Apply/Finish or when opening a stale sketch for Edit. Future asynchronous
  sidecar preview must use debouncing, request IDs/base hashes, and main-thread
  result application. Do not touch `bpy` from a worker thread.
- Before commit, validate context and base document hash, then validate exact
  geometry. Accept the document and current display together. A stale asynchronous
  result cannot overwrite a newer edit. A failed candidate stays editable with
  its error while the committed result remains explicitly identifiable.
- Esc restores the pre-operation document, display, and relevant selection. Track
  and remove every timer, handler, cursor/status override, and preview. Restore
  only view settings we intentionally changed; never change unrelated scenes.
- Modal state must end or explicitly suspend on workspace/scene/window changes,
  file load, add-on disable/reload, and external Undo. Choose deterministic cancel
  for the first implementation; never silently commit. Version 0.2 discloses the
  cancellation rule while editing and shows an INFO notice after a context-switch
  discard. Safe draft suspension/restoration remains a follow-on. Saving stores
  committed design only and makes unsaved-draft status clear.
- Keep standard navigation available. Pass navigation events through rather than
  consume every event. Do not pass destructive mesh/transform shortcuts through
  blindly while a CAD draft owns the viewport. Do not globally replace the keymap.
- A completed profile edit or feature commit is one meaningful Blender Undo step.
  View navigation, hover, tool choice, and mouse moves are not model-history steps.
  Local draft correction is separate from committed-document Undo. Do not call
  global Undo from a still-running modal transaction or push an Undo on each move.
- Undo/Redo restores canonical JSON and corresponding display/status. Rebind any
  derived UI caches safely after Undo without appending new undo records. Feature
  history remains saved design data; Blender Undo remains session history.

## Release checks and decision triggers

Run existing kernel, lint, smoke, installed-ZIP, and two-process persistence gates
against the final implementation. Add state-machine tests for repeated clicks,
invalid/zero-size input, rejected numeric input, cancelled dialogs, missing backend,
late/out-of-order sidecar replies, context loss, deleted workspaces, two windows,
Undo/Redo, and disable/re-enable. Verify units using non-default scene scale and
large-coordinate/tiny-part cases.

GUI evidence must show the actual sketch-to-part flow and dimension editing,
not just a screenshot of icons. At ordinary window size a new user should complete
New Sketch → Sketch tab → plane → tool → draw/dimension → Finish Sketch → Part
tab → Extrude, without opening Help or reading introductory paragraphs. Then
Edit Sketch → dimension change → Finish must update the same part. Merely showing
three tabs, icons, or different menus does not pass. Existing Local View framing/Undo limitations
must be addressed or remain explicitly open; a new workspace does not fix them
by itself.

Escalate to Blender core work only after documenting a concrete requirement,
the failed supported-API prototype, and a costed maintenance benefit. A literal
new native mode would require core enum/context integration, entry/exit semantics,
operator polls, tools/keymaps, and Undo handling. Adding one label is not that work.

## Explicit viewport focus (post-1.17 development)

CAD's header icon, Tools & Document menu, and history-panel toolbar expose
**Focus CAD**. This uses Blender's native maximize-area action with panels kept
visible. The same action becomes **Restore Layout** and returns the prior area
arrangement. It does not join/delete editors, rewrite newly created or existing
workspace layouts, isolate objects, change canonical model data, or reset
intentional custom layouts. All changes are explicit and viewport-local; existing
ordinary Blender workspaces remain intact. During an active sketch, Focus/Restore
first checkpoints and suspends the draft, with a visible **Resume** notice. Native
maximize replaces viewport/region identity, so it must not rebind an old owner or
carry its solver authority across the transition. Resume restores geometry and
selection through the existing lifecycle; Check obtains fresh solve evidence.
A failed checkpoint prevents the layout transition. This explicit extra Resume
step is a known usability tradeoff, not an automatic seamless live-draft handoff.
Blender's own maximize-area shortcut
is still available.

While actively editing a sketch, the ordinary **Part: Dirty** notice becomes a
single status row. The detail icon explains that committed-Part status is separate
from the current sketch solve, and the rebuild icon remains available under its
existing poll rules. Failed/unverified/stale states and nonstandard dirty errors
remain expanded. Short histories initially reserve only the rows they need
(minimum two, maximum seven), keeping the sketch inspector nearer the active
geometry controls; longer histories retain the normal scrollable list.
This is presentation only: no status, solver evidence, failure,
or selection data is changed or relabeled Ready.

Native-free tests cover operator eligibility, use of the panel-preserving native
action, action labels, and the strict compact-status predicate. The disposable
`blender_workspace_focus_fixture.py` is the event-loop gate for repeated
Focus/Restore, exact layout restoration, exact unsaved geometry/selection across suspension/resume, fresh solver
verification, and Esc suspension/resume. Passing native-free tests is not evidence of
GUI usability. Real native and GUI results must be recorded separately before
including this development change in a release.

The bounded source-loaded native/GUI verification on 2026-10-24 passed the
repeated-transition, suspension/resume and visual checks described in
[the Focus CAD audit](audits/workspace_focus_20261024.md). This evidence is separate
from installer/reopen/platform qualification and does not alter the frozen 1.17
release scope.
