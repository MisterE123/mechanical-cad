# Topology and intention regression catalog

This is a bounded, inspectable acceptance plan, not a claim that general topological naming is solved. `catalog.json` separates executable unit contracts from planned B-rep and Blender interaction fixtures. A passing mocked-candidate test does **not** demonstrate that a kernel adapter correctly produces those candidates.

## Current implementation boundary

Implemented: kernel-free resolver contracts, actual OCCT construction/cut provenance, parameter-edit replay, stable feature IDs, order-independent source-list replay, old-source replay, and explicit failed-dependency output. The implemented links in `catalog.json` describe each test's actual scope.

Planned: general merge support, feature suppression, an interactive rollback tip, history reordering that rewires dependencies, unit-bearing expressions, persistent topology-selection records, natural-language operation parsing, and the repair preview/confirmation/audit UI. The source model currently uses mm only; Blender scene conversion is a separate boundary. The absence/restoration unit test proves resolver behavior with supplied snapshots, not suppression integration.

## What is supported

The resolver represents a persistent selection as a stable feature ID plus a documented semantic role, an entity kind, and preferably a body UUID. A primitive or extrusion adapter can provide roles such as `cap.start`, `cap.end`, and `side.x_min` when those roles follow the actual construction or operation history. The adapter must assert `provenance.semantic_status = "stable"`.

A reference resolves only when there is exactly one semantic match and its provenance explicitly says `stable`. A missing assertion fails closed. One-to-one source history may preserve identity for a supported operation only after checking both directions: one descendant for the source, and one ancestor for the descendant. A split, merge, generated-only face, or unsupported operation is not silently upgraded to stable identity.

Persistent identity never comes from:

- Kernel face numbers or object handles
- Blender polygon indices or tessellation order
- Feature display names or history-list positions
- Nearest centroid, largest area, normal direction, or geometric score
- A deterministic sort breaking a symmetry tie

Geometry is useful evidence for a repair proposal. Every `TopologySuggestion` has `inferred = true`; its score is a ranking heuristic, **not a probability**. A result with proposals is still `missing` or `ambiguous`, with no accepted `candidate`. Proposals can be wrong and need explicit correction or confirmation. Tied best scores are marked, even though their display order is deterministic.

## Small data contract

`src/mechanical_cad/topology.py` has no Blender or kernel dependency. It accepts dataclasses or dictionaries:

```python
from mechanical_cad.topology import resolve_reference

reference = {
    "id": "reference-mounting-plane",
    "feature_id": "feature-pad",
    "body_id": "body-part",
    "role": "cap.end",
    "kind": "face",
    "signature": {"surface": "plane", "area": 1200, "centroid": [20, 15, 5]},
}
candidate = {
    "id": "current-rebuild:face-8",
    "feature_id": "feature-pad",
    "body_id": "body-part",
    "role": "cap.end",
    "kind": "face",
    "signature": {"surface": "plane", "area": 1200, "centroid": [20, 15, 8]},
    "provenance": {
        "semantic_status": "stable",
        "operation_id": "feature-pad",
        "evolution": "generated",
        "rebuild_id": "current-rebuild",
        "sources": [{"feature_id": "feature-profile", "role": "profile.region"}],
    },
}
result = resolve_reference(reference, [candidate])
assert result.status == "resolved"
assert result.candidate.id == "current-rebuild:face-8"
```

The distinction between `semantic_status` and `evolution` matters: an extrusion cap is created by an operation but has a supported stable construction role. Conversely, an arbitrary boolean-generated face has generated lineage without a supported persistent semantic role and must use `semantic_status = "generated"` or `"unknown"`.

`Resolution.status` is `resolved`, `ambiguous`, or `missing`. `reason` is a stable machine-readable reason code. `candidates` contains exact semantic matches; `suggestions` contains geometry-based proposals. `to_dict()` provides a serializable representation. A reference's optional `id` is created and persisted by the document layer; the resolver never invents or changes it.

The caller supplies only candidates from the active successful evaluation. The resolver cannot detect a stale snapshot mixed in by its caller. Suppressed or rolled-back features must not contribute candidates. On rebuild failure, a last-good visual preview must be visibly stale and excluded from new operation selection.

Canonical lengths are millimetres, areas square millimetres, and normals dimensionless. Missing signature units mean canonical mm under this contract. Explicit non-mm signatures are not geometrically compared; convert them at the parameter input boundary. Identity is independent of signature/display-unit changes.

## Durable IDs and operation provenance

Keep these distinct:

1. **Feature ID (UUID recommended):** allocated once, serialized, unchanged by rename, parameter edit, suppression, or permitted reorder. Copying a feature creates a new UUID.
2. **Body/output ID (future document support):** a persistent logical output slot, not an index in today's kernel result array. Multiple outputs must have explicitly supported slots or require review.
3. **Reference ID (future document persistence):** identifies the user's saved selection/intent. A repair changes its target with an audit record, rather than losing the previous target.
4. **Snapshot candidate ID:** unique only in one rebuild. Useful for highlights and diagnostics; never a persistent selection key.
5. **Case ID:** permanent catalog identity independent of its current hierarchy or title.

The adapter should retain operation ID/type, source semantic references, evolution (`unchanged`, `modified`, `generated`, `deleted`), semantic status, and rebuild/kernel metadata. Preserve one-to-many and many-to-one ancestry. A deleted source is an operation-history tombstone, not a current geometric candidate. Keep the document's feature graph and source-intent records separate from disposable tessellation and geometric evidence.

OCCT exposes operation history through `Modified`, `Generated`, and `IsDeleted`; its naming documentation explicitly distinguishes splits, merges, and deletion. These are evidence to consume, not a guarantee that an application's naming policy is correct. See the [official modeling-algorithms source](https://github.com/Open-Cascade-SAS/OCCT/blob/master/dox/user_guides/modeling_algos/modeling_algos.md) and [official naming-evolution reference](https://occt3d.com/dev/doc/refman/html/_t_naming___evolution_8hxx.html). This MVP resolver is not an OCAF/TNaming implementation.

## Intention resolution and human correction

Keep a proposed operation separate from an executable edit:

1. Parse a bounded command into an explicit operation, parameters, input features and supported semantic selectors.
2. Display assumptions in ordinary language: for example, “I interpreted ‘top’ as the end cap of Pad, along its extrusion direction.” The display should name the feature and highlight the target.
3. Validate dimensions, dependencies, target uniqueness and supported operations. An unresolved selection stops dependent evaluation.
4. Let the user correct the operation, target, direction or dimension before committing. A preview or canceled proposal must not mutate the feature graph.
5. On acceptance, store old/new semantic targets, the evidence shown, user decision, document revision and recompute outcome. Undo restores the prior intent.

Do not persist free-form prose as executable code or treat an AI's confidence as permission to select a face. A fully specified supported semantic command can execute without inventing a guess. An underspecified or geometrically inferred target stays visibly proposed. For an unstable generated face, offer a supported datum/feature relationship or explain that persistent selection is not yet supported.

## Bounded MVP acceptance fixtures

Each case in `catalog.json` includes its fixture, edit, observable assertions, repair policy and exact pytest links. The core real-B-rep gate should be:

- **Dimension edits:** 40 × 30 × 5 mm plate, height 5 → 8; supported cap/side roles persist and volume changes 6000 → 9600 mm³.
- **One-to-one cut:** radius-3 through-hole in that plate; top cap survives with one-to-one modified lineage. Changing radius to 4 changes volume from `6000 - 45π` to `6000 - 80π` mm³.
- **Split:** shallow crossing slot, x=19..21, y=-1..31, z=2..6. The lower web keeps one solid, top cap splits, volume is 5820 mm³, and the old single-face reference is ambiguous.
- **Delete:** trim x=-1..5 through the plate. Original x-min side is deleted, the cutter-generated replacement is not automatically equivalent, volume is 5250 mm³.
- **Symmetry:** two equal holes with equal evidence for a missing target; both are proposals, neither is auto-selected.
- **History:** rollback/suppress/restore, source-list permutation, missing/cyclic dependencies, and failed-rebuild atomicity. Suppression and operation-history rewiring remain separate planned gates.
- **Units:** equivalent mm/inch dimensions preserve physical shape and semantic references; changing display units never rescales the model.

Real merge coverage is separately planned: fuse adjacent solids and explicitly unify same-domain faces, then verify many-to-one ancestry. A unit-level `merged` marker test does not establish kernel merge detection. Blender preview/cancel/accept/undo is likewise a separate UI acceptance gate.

For real-kernel tests assert validity, solid count, mass/volume with explicit tolerance, provenance cardinality, and semantic target. Avoid golden face enumeration and binary BREP hashes. Retain a minimal input history, before/after parameter values, kernel version, operation diagnostic, expected/actual resolution, and rendered highlights when useful. Tests should fail on silent retargeting even if the final shape happens to look plausible.

## Search and traceability without loading everything

`catalog.json` has `schema_version`, independent `catalog_version`, a small taxonomy, and case records. A record has permanent `id`, `category_path`, tags, fixture, mutation, acceptance, repair policy, exact test node IDs, coverage status, and code symbols. `planned` tests are intentionally named but are **not** represented as executed. `test_implemented_catalog_test_links_exist` checks that every implemented entry points to a real test function.

Start with a category or tag, then load only the matching case and its test/source symbols. For example:

```sh
jq '.cases[] | select(.id == "MCAD-TOPO-003")' docs/regressions/catalog.json
jq '.cases[] | select(.category_path[1] == "evolution") | {id,title,coverage}' docs/regressions/catalog.json
jq '.cases[] | select(.tags | index("cut")) | {id,title,tests}' docs/regressions/catalog.json
python -m pytest tests/unit/test_topology.py -q
```

When a new failure appears, first reduce it to a deterministic fixture. Add one permanent case ID, the expected safe behavior and an initially failing test; then make the smallest scoped implementation change. Record whether the remedy is a supported semantic rule, an inference proposal, an explicit unsupported case, or an input-validation fix. Never “fix” ambiguity by picking the first candidate. Reclassifying or moving a case must not change its ID. Do not erase a retired case: retain a replacement/alias record so old bug reports and tests remain traceable.

## Constrained-sketch additions

Catalog version 2 also tracks exact duplicate relations/native seed sensitivity,
explicit region connectivity, stable line-ID side provenance, schema-1 hash
compatibility with explicit schema-2 migration, and native small-feature limits.
These are separate solver/unit/B-rep layers. They do not claim interactive
constraint creation, assembly mates, general curve loops or complete topological
naming. Search the `sketch/constraints`, `sketch/regions`, `sketch/resolution`,
`topology/semantic_identity/sketch_boundary` and `history/schema_migration` paths.
