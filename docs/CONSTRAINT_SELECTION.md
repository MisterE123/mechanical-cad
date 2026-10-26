# Authored constraint selection contract

`blender_addon/mechanical_cad_blender/constraint_selection.py` is a native-free
dependency leaf. It describes currently available authored IDs and control
requirements. It does not execute commands, import the owner or renderer, inspect
solver reports, establish current geometry, or change persisted payloads.

## Public entry points

- `normalize_selection(authored_sketch, selection)` accepts a bounded list or
  tuple of the existing UI dictionaries `{kind, id}`. It returns immutable
  `EntitySelection(kind, id)` records in the exact selected order. Duplicate,
  missing, unknown and wrong-kind IDs fail closed; no selection is silently
  dropped. The maximum is 32, matching existing UI intent. Existing shared sketch
  validation also bounds records, coordinates, constraints and source bytes.
- `relation_descriptors(authored_sketch)` returns all supported relations sorted
  by stable ID. Each immutable `RelationDescriptor` contains `id`, `kind`, exact
  ordered `refs`, `source_value` and `fixed_target`. Source numeric types and raw
  formula strings are preserved. No solved/evaluated value replaces a source.
- `selection_contract(authored_sketch, selection)` returns immutable `selection`,
  `relations` and `actions`. Read an action using `.action(name)`. Action names are
  `horizontal`, `vertical`, `fix_here`, `fix_origin`, `inspect`, `remove_relation`
  and `coincident`. Unknown action names fail closed.
- `pick_kinds()` returns the existing generic geometry filter;
  `pick_kinds("point")` returns only `("point",)` for an explicit point mode.
- `coincident_preflight(authored_sketch, point_ids)` reports symbolic line-collapse
  risks for exactly two distinct available points. It is not solver evidence.

All returned containers are tuples and all record types are frozen. Input lists
and dictionaries remain untouched and are not retained by the results. Schema 1
and schema 2 sketches use their existing validators without migration.

## Action states are requirements, not authority

Each `ConstraintAction` has `action`, `state`, `refs`, `relation_ids`,
`requirements`, `target` and a readable `reason` when needed. There is deliberately
no `enabled` property. Its states mean:

- `unavailable`: the exact selection shape/kind is unsuitable, or symbolic
  coincidence would leave a line collapsed.
- `eligible`: authored selection prerequisites are met. The owner must still
  check currency, satisfy the listed requirements and use its existing command,
  solve and publication boundaries.
- `existing`: show the listed existing relation IDs instead of creating another
  relation. This is inspection/no-op intent, not proof of a successful solve.
- `deferred`: valid candidate intent whose production control must stay disabled
  until additional safety gates are implemented.

Horizontal/Vertical need exactly one line. Existing exact duplicates are exposed
by ID. A descriptor's `signature` matches the existing reducer equivalence rule:
only distance/coincident references are symmetric; equal numeric values compare
equally, while formula strings and distinct fixed targets stay distinct. Exact
source reference order remains intact in `refs`. If multiple exact duplicates
were already authored, all IDs are exposed; the helper does not appoint a new
canonical ID or replace the reducer's existing no-op behavior.

Fix here and Fix at origin need exactly one point. Fix here returns no target and
requires `current_successful_solution`; authored seeds, a retained outline and
failed diagnostics cannot supply its target. Fix at origin returns `(0, 0)` in
sketch-plane millimetres and requires `origin_movement_disclosure`. Neither checks
whether current solved evidence exists. If any fixed relation already references
the point, both actions expose every such ID, require
`explicit_fixed_relation_selection`, and propose no additional target. Different
targets are retained for explicit inspection/edit/release, including very small
differences that a formatted label might hide.

Inspect requires exactly one entity or relation. Remove requires exactly one
constraint ID, with `current_successful_solution` and
`relation_only_delete_preview`. It never suggests deleting geometry or all
relations touching an entity. An authored-position recovery action, if integrated
separately, must retain its own typed command, explicit seed-policy disclosure and
owner guards; it is not implied by this ordinary removal capability.

The contract has no current revision token and must be rebuilt after relevant
source or selection changes. The owner checks its exact current source/revision
again at action time. Keeping a returned descriptor does not keep it current.

## Inspector incidence

Selecting a relation returns only that exact relation. Selecting geometry shows
relations with explicit one-hop authored incidence:

- A point includes direct references to it, H/V on its incident lines, and radius
  relations on circles having it as center.
- A line includes references to the line or either endpoint.
- A circle includes references to the circle or its center.

This is a compact view of authored references, not a complete solver-dependency
graph. It does not follow coincidence transitively or imply that a radius relation
fixes a circle's center. Multiple selected entities return no single-entity
inspector list; two distinct points are evaluated separately for Coincident.

## Explicit point picking and compatibility

Use a visible, transient **Points** selection filter (or an explicit stable-ID
chooser), then pass `kinds=pick_kinds("point")` to the unchanged
`general_view_geometry.pick_geometry`. Only a complete `unique` picker result is
an unambiguous proposal; validate that exact kind/ID against the current authored
sketch before storing the selection. The helper does not invoke the picker or
give a hidden priority to points.

A point at its incident line endpoint ties with the line in generic Select,
including after zooming. Point-only mode resolves that cross-kind tie. Distinct
overlapping points still remain ambiguous, and incomplete projection results must
not become selections. Generic Select retains its actual nearest geometry policy.
The tests exercise the real picker, including a nearer line with a nearby point.

The recommended first integration keeps the visible filter in runtime owner/UI
state, resets it explicitly with the gesture/session lifecycle, and leaves saved
selection dictionaries and the current UI wrapper v2 bytes unchanged. This means
the filter itself will not resume after reopening, which is an intentional
compatibility tradeoff. Persisting a filter later needs explicit codec/version
dispatch and compatibility tests; silently appending a field is not supported.

## Coincident remains gated

The symbolic preflight unions only exact point IDs connected by authored
coincident relations, then tests the proposed pair. It reports every line whose
endpoint classes would coincide, including an already-collapsed line. It never
merges/replaces point records, infers connections from equal/near coordinates or
treats an existing transitive path as an exact duplicate relation. Existing direct
duplicates, including reversed refs, remain inspection/no-op results even when
the authored sketch itself is invalid.

An absence of symbolic collapse does not prove valid geometry. Other constraints
can cause geometric degeneracy, conflicts or unsupported profile changes. The
production action remains `deferred` and requires `explicit_two_point_preview`,
`solve_profile_preflight` and `recovery_path`. Native solve and supported profile
validation, dependent-feature replay, recoverable failure handling and clear
preview of both IDs remain necessary before exposing a production button.
