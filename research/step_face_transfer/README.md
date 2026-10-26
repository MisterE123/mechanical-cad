# Bounded STEP face-transfer provenance investigation

Date: 2026-10-24. Source inspected: `3ce71456965074ff0a3077e3a13d0f47d2829f64`.
This is a negative feasibility observation, not a production change or a claim
that OCCT cannot support imported-face identity. No upstream defect is established.

## Result

The verified Python API path did **not** establish the required mapping from
persistent STEP entity labels to output native faces. Imported faces therefore
remain `unknown`; no stable-selector policy changes are justified by this probe.

The native runtime reports OCP `8.0.1.1`, with `cadquery-ocp-proxy` and
`cadquery-ocp-novtk` distributions both `8.0.1.1.0`. A single native 20 x 30 x 5
box was exported once and those exact bytes imported twice. Each replay produced
six output faces and 48 transfer mappings, including six face-entity bindings.
For each mapped face the indexed binder reported `TopoDS_Face`, execution status
`Transfer_StatusDone`, no multiple/next result, and zero warnings or failures.

Nevertheless, the following documented access path failed in both replays:

- `model.Value(i)` returned a `StepShape_AdvancedFace`, but
  `model.Number(entity)` and `model.IdentLabel(entity)` returned zero.
- `process.MapIndex(entity)` returned zero; `process.Find(entity)` returned `None`.
- `transferReader.ShapeResult(entity)` returned a null shape.
- Those same round-trip observations held for `process.Mapped(i)`, although
  `process.MapItem(i)` exposed a non-null binder reporting a face result.
- `reader.GetShapeProcessFlags()` raised a Python conversion `TypeError` for
  `tuple[std::bitset<18ul>, bool]`; 54 shape-fix parameters were present.

Initial interactive inspection also found no importable `OCP.TransferBRep`
module and no shape extraction method on the surfaced `Transfer_Binder` object.
The durable probe concentrates on the forward and indexed-transfer observations,
not an exhaustive search of every possible API. Zero warning counts do not prove
that no repair occurred. An entity's model/map position is logged only to locate
a diagnostic observation, never as a proposed persistent selector.

## Reproduce safely

Run from the repository with the pinned native sidecar Python:

```sh
/path/to/cad_runtime/dev-venv/bin/python research/step_face_transfer/probe.py
```

Optionally pass `--output-parent /existing/output/directory`. The script always
creates a fresh uniquely named directory with `tempfile.mkdtemp`; it writes only
`plate.step` and `result.json` there and prints the result path. It reads no user
model. The fixture includes native export metadata, so new runs need not produce
the same asset digest. Within each run the bytes are checked unchanged before
each import. `observed_result.json` preserves one complete measured result.

A successful process exit means the probe ran, not that identity is established.
The report deliberately sets `identity_established` to false: this script does
not implement a sufficient proof even if another runtime returns better results.

## Missing proof and safe future boundary

An independently reviewed future path would need all of the following:

1. A trustworthy original STEP entity label tied to the exact immutable asset
   digest, not an ordinal or reverse lookup's first match.
2. Complete forward source-to-result provenance and exact native `IsSame`
   membership checks against output faces, with exhaustive competing-source
   accounting. Exactly one source and one output occurrence must claim a face.
3. Reliable exclusion of repaired, split, merged, duplicate, generated, unmapped
   or otherwise uncertain faces. Missing repair evidence must fail closed.
4. Repeatability under the declared pinned importer/settings policy; an asset
   change must invalidate identity even if labels or geometry appear unchanged.

A supported, qualified binding or narrow native provenance bridge could be a
future investigation, but neither is implemented or proven here. No nearest
geometry, face-order matching, pointer/ctypes access or reverse-first-match
shortcut was used. This result is not a universal TNP claim.

## Existing guards that must remain intact

- `src/mechanical_cad/step_asset.py` already enforces exact SHA-256, canonical
  base64 and the existing 512 KiB bound. There is no reason to expand that limit.
- `kernel_ocp.py:import_step_data` requires one transferable root and one solid;
  it retains no imported-face provenance. `topology` consequently emits unknown
  snapshot-only face handles.
- `blender_addon/mechanical_cad_blender/topology_evidence.py` allows only
  unresolved imported roles, closes provenance keys/relations and validates
  role/surface consistency. A future extension requires narrow, versioned guards,
  not only a kernel stable-status flag.
- `part_result_bridge.py` checks canonical source binding, downstream lineage and
  face support. Any future digest-bound role must agree with the authored asset.
- Existing operation-history ambiguity/split/merge/deletion checks remain
  necessary after a truly proven imported source. No downstream guard may be
  weakened to compensate for absent import provenance.

## Execution limits

Only one small exported box and two imports were exercised, plus installed public
API/docstring inspection. This does not test other STEP encodings, assemblies,
healed inputs, other platforms or kernel versions. No production behavior,
user/release model, Blender session, Techbox task, publication, native bridge or
full regression suite was changed or run.
