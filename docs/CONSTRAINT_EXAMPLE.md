# Explicit constraint plate example

`examples/explicit_constraint_plate.mcad.json` is a small, reproducible canonical
example for the **unreleased explicit-constraint UI slice**. It was authored as
model data; it is not evidence that a person drew this part in Blender. It adds no
new document format or core API. Released 0.4 archives and evidence are unchanged.

## Definition and expected result

The Part and its embedded general line sketch both use schema 2 and millimetres.
There are only two features:

- `plate_outline` / **Explicit plate outline**: one XY line loop with four shared
  endpoints. Each corner is one point identity used by two lines, rather than two
  coincident points. No Coincident relation or hidden geometric join is needed.
- `plate_body` / **Plate thickness**: the active extrusion of that outline, driven
  by the expression `thickness` along positive Z.

The four point IDs are `corner_origin`, `corner_east`, `corner_far` and
`corner_north`. The boundary IDs are `edge_south`, `edge_east`, `edge_north` and
`edge_west`. These deliberately differ from the Rectangle shortcut's fixed
`p0`–`p3` / `l0`–`l3` definition, so **Edit Sketch** uses the general editor.

Seven explicit relations constrain the outline:

- `origin_lock`: fixes `corner_origin` at sketch-plane `(0, 0)`.
- `south_axis` and `north_axis`: Horizontal on their respective lines.
- `east_axis` and `west_axis`: Vertical on their respective lines.
- `width_driver`: distance from `corner_origin` to `corner_east`, expression `width`.
- `depth_driver`: distance from `corner_east` to `corner_far`, expression `depth`.

The named parameters are `width = 40`, `depth = 25` and `thickness = 8`.
Successful native replay gives **0 remaining DoF**, a 40 × 25 × 8 mm valid single
solid with six faces, and **8000 mm³** volume. The slightly skewed authored point
coordinates are initial solver seeds. Replay computes the exact rectangle without
rewriting those seeds or replacing the expressions with their resolved values.

Dimension edits preserve feature, point, line and constraint IDs. The four side
faces retain `side.line.edge_south`, `side.line.edge_east`,
`side.line.edge_north` and `side.line.edge_west` provenance, plus `cap.start` and
`cap.end`. Deleting and recreating a relation or boundary is a different operation
and need not preserve its identity.

## Open and edit in the development interface

Use the current development add-on with its configured native sidecar, not an
unchanged released 0.4 ZIP when trying the new explicit relation controls. The
ordinary sidecar and workspace setup is described in [INSTALL.md](INSTALL.md).

1. In Object Mode, choose **Load CAD Document** and open the example. The load
   validates and replays the canonical Part. Select **Explicit plate outline** in
   feature history, then choose **Edit Sketch**.
2. Choose **Check** and wait for current native evidence. Confirm the Sketch
   status shows 0 DoF. A retained outline, pending check or unverified draft is not
   current solver evidence.
3. Select the lower line, `edge_south`. **Sketch relations** shows its incident
   constraints. **Horizontal** inspects the existing `south_axis` relation instead
   of creating a duplicate. Select `edge_east` and use **Vertical** to inspect
   `east_axis` in the same way.
4. With `edge_south` selected, use **Start point** to select `corner_origin`
   explicitly. Its `origin_lock` row shows the fixed `(0, 0)` target. The existing
   Fix actions inspect that relation; they do not silently retarget it. The
   point-only selection tool is another way to select a corner.
5. To edit a driving expression, choose **Dimension**, select `edge_south`, and
   place its existing width label. Double-click the label, enter `width * 1.5`,
   and press Enter. Wait for the solve and downstream Part replay, then choose
   **Finish Sketch**. The same body becomes 60 × 25 × 8 mm, volume **12000 mm³**.
   The named parameter `width` is still 40; the changed expression drives 60 mm.
6. For parameter-only edits, first finish or cancel the draft. In Part's
   **Named Parameters**, change `width` from 40 to 60 while retaining the original
   `width_driver = width`, then **Rebuild**. This also gives 12000 mm³. Changing
   only `depth` to 35 gives 11200 mm³; changing only `thickness` to 10 gives
   10000 mm³. These values each start from the untouched example.
7. Use **Save CAD Document** with a new filename to keep an editable variant.
   Portable JSON retains the design; label placement belongs to the `.blend`.

To explore relation release on a temporary draft, select the exact `origin_lock`
row after a successful Check and choose **Remove relation**. The native result
has two translational DoF. **Undo sketch** restores the original relation; wait
for a successful Check to see 0 DoF again. Alternatively, select `corner_origin`
and explicitly apply **Fix at origin…**, reviewing its movement disclosure and
Apply/Cancel dialog. This authors a new relation ID. **Cancel Sketch** discards
these draft experiments and preserves the committed example.

See [CONSTRAINT_INSPECTOR.md](CONSTRAINT_INSPECTOR.md) for bounded inspection,
confirmation and conflict recovery. Coincident creation, arcs and a complete
general constraint editor remain outside this slice.

## Reproduce without Blender

From this checkout with the existing `.venv` containing the pinned OCP and `slvs`
packages:

```sh
.venv/bin/python -m pytest -q tests/integration/test_constraint_example.py
.venv/bin/python -m mechanical_cad.cli replay examples/explicit_constraint_plate.mcad.json --result-version 2
.venv/bin/python -m mechanical_cad.cli check-geometry examples/explicit_constraint_plate.mcad.json --result-version 2
```

To keep exports and an edited variant outside the source tree:

```sh
out=$(mktemp -d)
.venv/bin/python -m mechanical_cad.cli set-parameter examples/explicit_constraint_plate.mcad.json width 60 "$out/plate-60.mcad.json"
.venv/bin/python -m mechanical_cad.cli export-step "$out/plate-60.mcad.json" "$out/plate-60.step" --result-version 2
.venv/bin/python -m mechanical_cad.cli export-stl "$out/plate-60.mcad.json" "$out/plate-60.stl" --result-version 2
```

The integration tests check canonical round-trip, real zero-DoF solve, exact
dimensions/volume, immutable seeds, general-editor acceptance, checked formula
edits, reordered records, stable side provenance under parameter edits, and fresh
STEP/STL export of an edited Part. STEP is reimported and measured; STL's encoded
mesh and precision gates are checked. Exports contain geometry, not editable
feature history; STL must be interpreted in millimetres by the receiving tool.

These tests do not establish Blender GUI usability or installed-package
qualification. The geometry gates establish valid B-rep and closed, oriented,
manifold mesh results for these cases, not manufacturing, strength or safety
certification. See [GEOMETRY_ACTIONS.md](GEOMETRY_ACTIONS.md) for those boundaries.
