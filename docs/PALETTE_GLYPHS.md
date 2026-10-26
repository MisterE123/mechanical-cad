# Native palette glyph adapter

`blender_addon/mechanical_cad_blender/palette_shapes.py` is an isolated, native-free
adapter for eight frozen CAD glyphs. The adapter itself registers nothing.
`workspace_ui.py` uses its validated bytes in the live Part/Sketch palette, with
per-action PNG/native fallback. Menus retain PNG previews; availability and model
data do not depend on glyph loading.

## API

`load_shape(action: str) -> bytes | None` returns immutable, validated bytes for
`GIZMO_GT_button_2d.shape`. `ACTIONS` is the immutable tuple of supported keys:

- `NEW`, `EDIT`: `sketch_rectangle`
- `DIMENSIONS`: `sketch_dimension`
- `FINISH`: `edit_apply`
- `CANCEL`: `edit_cancel`
- `EXTRUDE`: `feature_extrude`
- `CUT`: `feature_cut`
- `CHECK`: `verify_model`
- `EXPORT`: `file_export`

Unknown keys, unreadable/missing resources, changed source or payload bytes, and
invalid geometry return `None`; callers should retain the existing PNG/native
icon for that action. One bad glyph does not disable other glyphs. A corrupt
shared manifest fails all requests closed. No filesystem access occurs for an
unknown action, and the caller cannot supply an asset path.

There is no runtime dependency on bpy, Inkscape, SVG parsers, tessellators, native
libraries, or network access. The existing source SVGs must remain packaged in
`assets/icons/svg`: their exact SHA-256 identities are checked on every load.
Loads are uncached so a successful earlier read cannot hide later corruption.
Call during gizmo creation, not on every draw. The private geometry validator is
not an API for loading arbitrary shapes; only `load_shape` verifies provenance.

## Binary format and safety

The payload is a sequence of unsigned-byte XY pairs. Coordinates 0–255 map to
native gizmo coordinates −1–1. Every simple polygon ends by repeating its **final
vertex once**. The initial vertex is not repeated. This mirrors the inspected
Blender 5.2.2 decoder's look-ahead and consumption of the terminal pair.

Some reviewed polygons have four or five vertices. Eight-byte triangle records
must not be assumed. The conversion expands strokes/caps/joins and dash patterns,
then unions the fill. Holes are assigned to connected components and tessellated
into simple polygons, preserving unfilled regions and disconnected dash islands.
The runtime neither reinterprets contours nor fills holes independently.

Before returning any bytes the adapter verifies:

1. The complete manifest SHA-256 against the constant pinned in Python.
2. Exact original source SVG and frozen payload SHA-256 values.
3. Bounded reads: 32 KiB manifest, 8 KiB source, 2 KiB payload.
4. Even byte framing, every look-ahead and final sentinel, at least three unique
   vertices, positive nonzero signed area, and full-buffer consumption.
5. At most 192 polygons, eight vertices per polygon, and 576 total vertices.
6. Exact reviewed byte count, polygon/vertex counts, area, and coordinate bounds.

The `bytes` representation itself enforces unsigned 8-bit coordinates; reviewed
per-symbol bounding boxes are compared as an additional check. Exact hashes bind
accepted geometry to the offline topology validation. Runtime checks are not a
general polygon validator or protection against modification of trusted Python.

## Assets, provenance, and evidence

`assets/palette_shapes` holds eight payloads totaling **3,836 bytes**, a manifest,
and a derivative notice. Existing assets are reused without modifying them:

- Google Material Symbols Outlined: check, close, fact_check, output, Apache-2.0.
- Original CAD geometry: rectangle, dimension, extrude, cut, GPL-3.0-or-later.
- The source notice and complete licenses remain under `assets/icons`.

The manifest retains upstream commit/blob/source hashes, source SVG hashes,
conversion-tool versions, build-script hashes, original proof-manifest and
validation hashes, source-pack identity, per-symbol topology checks, and raster
metrics. The derivative notice explicitly records geometry conversion; these are
not claimed to be unchanged upstream SVG paths. No license was changed, no source
was downloaded, and no conversion tools are required at runtime.

These bytes were copied unchanged from the isolated `cad_workspace_spike/native_shapes`
proof. Its rebuild evidence reports byte-identical payload, expanded SVG, and
decoded shape SVG outputs. Its checks cover exact signed area, contour boundary,
edge multiplicities, planar edges, nonzero winding, and native 5.2.2 wire output.
The exporter coalesced a few adjacent polygons to avoid that version's final-edge
wire-deduplication quirk. Offline 256px fill-mask IoU was 96.8–99.3%, with filled
alpha-area change below 0.8%. These are inherited conversion checks, not a new
Blender drawing test.

## Live integration and visual boundary

The caller assigns `shape` before the gizmo's first draw and never sets `icon` or
`icon_value` on that branch, since they take precedence. Each action owns its gizmo
for its lifetime; native batches are not reused across shape/fallback paths.
`BACKDROP` keeps the normal native hover target. Missing or invalid glyphs retain
per-action fallback, and menus continue using the existing PNG assets.

Native workspace smoke tests cover complete shape wiring, per-action fallback,
visibility/hit-bound parity and registration cleanup. The 2419fc8 source-loaded
5.2.2 GUI review found the Part extrusion and Sketch Dimensions/Finish/Cancel
glyphs distinct at its native scale; hover highlighted blue and displayed readable
help. Assembly uses native fallback glyphs and remains less visually distinctive.
These observations do not establish exhaustive HiDPI, light/dark contrast,
accessibility or cross-platform behavior. See the GUI audit and exact-package
receipt for the particular tested runtime and source.

Run `python -m pytest -q tests/unit/test_palette_shapes.py` in the repository's
pinned sidecar environment for asset identity, licensing, framing, corruption,
truncation, budget, unknown-action, and per-glyph fallback tests.
