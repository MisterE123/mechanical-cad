# Distinct CAD toolbar identities

The delivered 1.4 screenshot showed different actions sharing identical native
symbols, rather than evidence of multiple registrations. This change preserves
all supported commands, native button hit testing, contextual availability and
fixed palette slots. It does not alter model data or topology behavior.

- Reverse arc uses a curved arrow; Extend uses a line, boundary and extension arrow.
- Select Points and Use Existing Point have different symbols.
- Check Sketch uses a magnifier with a check; Finish retains the commit checkmark.
- Round and straight corners distinguish Fillet and Chamfer.
- Boolean silhouettes distinguish Union, Cut and Intersection.
- Linear and circular arrangements distinguish patterns; cut patterns have holes.
- Circle, open arc, concentric, diameter and circle/arc tangent relations differ.
- Face sketch, face rectangle and face circle differ; projection and solid-edge
  reference have dedicated symbols.

The original geometry in `tool_glyphs.py` is GPL-3.0-or-later, like this project.
Simple bounded stroke polygons supply native button shapes; matching PNG previews
are generated offline with `scripts/build_tool_glyphs.py` (Pillow). No runtime
rasterizer, external executable artwork, or downloaded resources are needed.
Artwork is inset inside the existing 34-pixel button hit area, so selection targets
and responsive layout do not shrink. Native shape outlines are disabled to avoid
thin strokes being consumed by Blender's dark outline. Tooltips always begin with
the command name, including when the action has a context-specific explanation.
The redundant second Export entry in the Part menu is removed; Export remains in
the toolbar, named menu action and history panel.

## Verification for this delta

- 90 targeted unit tests pass (semantic glyphs and inherited safe shape framing).
- Ruff passes on changed Python files.
- Native Blender 5.2.2 LTS toolbar smoke: 470 assertions; second-process `.blend`
  reopen: 471 assertions. Exactly one header callback survives repeated enable;
  disable removes it, and unrelated objects survive. Fixed positions are tested
  at 1×, 1.5× and 2× across three viewport sizes. These are computed layout checks,
  not a claim of exhaustive HiDPI visual qualification.
- Real local ZIP install/enable exercises the installed module and all bundled
  preview files: 470 assertions. This is a source UI ZIP qualification, not a newly
  published self-contained installer.
- Cloud graphical Blender 5.2.2 review exercises Center Arc activation, rectangle
  drawing, native sketch Check, Finish and Cancel; observes distinct symbols and
  readable Check/Finish hover descriptions at the default native UI size. Part
  palette and matching menu symbols are reviewed visually. Test objects are in a
  disposable factory-startup session; no user document is used.

Run `tests/blender_toolbar_identity_smoke.py` with `--python-exit-code 1`. Set
`MCAD_TOOLBAR_BLEND` to a temporary output, then launch another process with that
file and `MCAD_TOOLBAR_REOPEN=1`. Set `MCAD_TOOLBAR_ZIP` and an isolated
`BLENDER_USER_SCRIPTS` directory to exercise actual add-on installation.

This scoped pass does not rerun the inherited full suite, establish all CAD
workflows, prove arbitrary Python hot-reload safety, or qualify other platforms.
The supported enable/disable/reopen lifecycle showed no duplicate registration;
no speculative registration rewrite was introduced.

## Focused original designs: Loft, Sweep, Hole, Shell

A four-action follow-up keeps the existing standard symbols and interaction
layout. In the actual action map, Loft, Sweep and Hole used Blender native
fallbacks (`MOD_SKIN`, `MOD_CURVE`, `MESH_CIRCLE`), not Google artwork. Shell used
a crowded closed-box outline. The supplied Part/Sketch GUI captures and existing
icon contact sheet were inspected before selecting these targets.

- **Loft:** different-sized closed section loops connected by rails. The changing
  section separates it from extrusion and constant-profile Sweep.
- **Sweep:** a constant-width curved elbow and end section, communicating a
  profile following a path rather than a changing section.
- **Hole:** a section through a stepped bore with shoulders and an open lower
  channel. The single command offers simple and counterbored holes; this glyph
  does not imply that counterbore is selected or that every hole is through-all.
- **Hollow / Shell:** an open cavity with separated inside/outside walls and a
  visible floor. This is a cutaway symbol, not an extra sketch command.

These are original project-owned GPL-3.0-or-later designs in `tool_glyphs.py`,
using the existing bounded native-shape vocabulary. `build_tool_glyphs.py` builds
both-theme PNGs and matching monochrome SVG exports for these four designs.
`assets/tool_glyphs/design_manifest.json` records authorship, license, source,
and generated hashes; the adjacent NOTICE explains the coordinate conversion.
Runtime never parses SVG or loads a new dependency. The frozen source-checked
palette pack and its manifest are unchanged. The existing live lookup immediately
uses the new code-owned shapes and menu previews; Shell's advanced route retains
its same-operation alias. Button size, 72% artwork inset, command names, tooltips,
search identities, learning labels, and availability are unchanged.

Offline verification: all four exported SVGs were rendered through Inkscape at
24, 32 and 72 px on dark/light backgrounds, then inspected as a contact sheet.
The stepped-bore and shell channels remain visibly open, and Loft and Sweep have
distinct silhouettes at 24/32 px. These are reviewer observations, not measured
user comprehension. Tests check bounded native encoding, nonduplicate geometry,
SVG/runtime polygon parity, licensing and generated hashes. Two complete builds
produce byte-identical assets. The supplied GUI screenshots describe the old
baseline only: no post-change Blender smoke, GUI, ZIP-install, reopen, or platform
qualification was run in this isolated asset pass. Those remain integration gates.
