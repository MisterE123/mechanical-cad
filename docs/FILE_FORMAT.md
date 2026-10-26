# Model file and process protocol

## Schema 1

A `.mcad.json` file is UTF-8 JSON with these fields:

- `schema_version`: integer `1`. Legacy primitive documents retain this version until explicit migration.
- `id`: stable document ID (nonempty text).
- `name`: display name.
- `units`: exactly `mm` in this version.
- `parameters`: object of name → number or arithmetic-expression string.
- `features`: ordered list of explicit feature records.
- `active_feature`: feature ID or `null`.

Unknown fields are rejected. IDs are independent of feature labels and Blender
object names. The file contains no mesh, native B-rep handle, Python pickle,
executable script, automatic Git action or machine-specific path. See the two
examples in `examples/` for complete, runnable documents.

Each feature has `id`, `kind`, `label`, `params` and `inputs`. Optional labels
fall back to the ID. Feature kinds:

| Kind | Required parameters | Optional parameters | Required inputs | Output |
|---|---|---|---|---|
| `sketch_rectangle` | `width`, `height` | `x`, `y`, `z` (all default 0) | None | Planar profile |
| `sketch_circle` | `radius` | `x`, `y`, `z` (all default 0) | None | Planar profile |
| `extrude` | `length` | None | `profile`: profile feature ID | One solid |
| `extrude_symmetric` | positive total `length` | None | `profile`: profile feature ID | One solid |
| `extrude_through` | literal `direction` ±1 | None | `profile`: profile; `base`: solid | One solid |
| `extrude_to_face` | literal `direction` ±1 | `offset` (default 0) | `profile`: profile; `target`: earlier solid | One solid |
| `cut` | None | None | `base`, `tool`: solid feature IDs | One solid |

Dimensions use positive millimetres; profiles are XY at Z and extrusion is +Z.
Inputs may reference a feature earlier or later in the list; cycles and dangling
IDs fail. The graph is fully replayed in stable dependency order. The list remains
the user's saved/display order. `extrude_to_face` is a deliberate exception: its
explicit `target` must be earlier in display history. It also requires top-level
`end_face`, a stable semantic face ID on that target. The end condition resolves
an infinite planar parallel stop, with signed travel-relative offset, on every
replay. It does not store a blind length or inherit the target face's identity.
See [extrusion end conditions](EXTRUSION_END_CONDITIONS.md).

Parameter formulas support numeric constants, parameter names, +, -, *, /, **,
parentheses, `pi`, `tau`, and `abs`, `sqrt`, `min`, `max`. No attributes, indexing,
Python execution, strings, conditionals or imports are allowed. Named parameters
can reference one another; cycles fail. Feature formulas reference only project
parameters, not arbitrary other feature properties. Unit-bearing expressions and
dimensional checking are not implemented.

## Schema 2: typed constrained sketches

Schema 2 adds `sketch_constrained`, with an empty scalar `params` object, no feature
inputs, and a required typed `sketch` object. All other document/feature fields
retain their existing meaning. Only this feature kind accepts a `sketch` field.
The embedded sketch payload independently uses `schema_version: 1`, stable point,
line, constraint and plane IDs, numeric seed coordinates, and expression-bearing
driving dimensions. See [SKETCH_SOLVER.md](SKETCH_SOLVER.md) and
`examples/constrained_plate.mcad.json` for the exact record contract.

Use `Document.migrate_to_v2()` to opt in explicitly. Loading, saving, or replaying
schema 1 does not migrate it or change its canonical hash. Migration changes only
the document version; existing features, IDs, expressions, order and active output
remain intact. Primitive rectangles/circles are not silently converted into solved
sketches. Schema-1 documents reject constrained features with `migration_required`.
Unknown versions beyond 2 still fail closed.

Sketch record arrays serialize in stable ID order. Numeric sketch values are
normalized within the new payload, without applying that normalization to legacy
features. Rebuilding evaluates expressions and solves a detached numeric snapshot;
it does not write solved coordinates into saved seeds or replace expressions.
`features[].sketch` in a replay result is derived solver evidence: status, actual
remaining DoF, diagnostic constraint IDs, residual, dimensions and solved geometry.
This result field is not an authoritative feature payload or model-history edit.

The first constrained-region backend supports one connected, simple closed loop
of straight lines. Connectivity requires shared point IDs or explicit coincidence
constraints. It never joins nearby endpoints by guessing. Multiple regions/holes,
branches, crossing/touching nonadjacent edges and degenerate edges fail visibly.
Each retained line ID becomes an explicit OCCT boundary and the extrusion's
`side.line.<id>` provenance. Workplane origin/quaternion define the extrusion
normal; the primitive profile behavior remains XY/+Z. GUI workplane/tool support
is a separate scope from this backend capability.

## Sidecar protocol 1

Run a configured CPython interpreter with `-m mechanical_cad.sidecar`, providing
one JSON value on stdin:

```json
{"protocol_version":1,"document":{"...":"complete schema-1 document"},"options":{"linear_deflection":0.1}}
```

One response JSON value is written on stdout. Kernel logs go to stderr. Exit code
0 indicates successful requested action (replay by default); exit code 1 indicates
failure. Always parse
the response, because a failed replay can still carry useful per-feature errors.
The response includes `protocol_version`, `ok`, `result` and `error`.

`result` includes `document_id`, `document_hash`, `active_feature`, `status`,
`units`, resolved project `parameters` and feature results. Every feature result
includes its ID/label/kind/inputs, `status` (`ok`, `failed`, `blocked`), `error`,
resolved parameters, tessellated `mesh`, `stats` and `topology` candidates.
Profiles have mesh previews but no solid stats. Failed/blocked features have no
usable mesh/stats; an earlier successful result must not be silently substituted.

Mesh vertices use millimetres and triangles use zero-based indices. Mesh indices
and `triangle_face_ids` refer only to that replay's display snapshot. They must
never be stored as persistent CAD references. Refer to `docs/regressions/README.md`
for provenance and semantic reference rules.

The optional top-level `action` defaults to `replay`. Explicit `check_geometry`,
`export_step`, and `export_stl` actions are also supported. Export actions require
an independently supplied top-level `destination`; a model document cannot request
file writes. Replay/check reject a destination. New action responses additionally
include `action`, `geometry_check`, and `export`, while legacy replay responses
remain unchanged. Every geometry action freshly replays the current canonical
snapshot, and exports atomically replace the chosen file only after validation.
See [GEOMETRY_ACTIONS.md](GEOMETRY_ACTIONS.md) for guarantees, failures and examples.

No operation executes arbitrary code, starts a shell, or makes network requests.
The add-on's configured interpreter is trusted executable software; the protocol
is not a sandbox against a malicious Python installation or modified source tree.

## Associative solid-edge projection extension

Existing constrained-sketch `projections` rows remain exactly `{source, target}`
and `inputs.external` continues to reference an earlier constrained sketch.
Unchanged documents retain their existing schema numbers, serialized fields and
semantics. No automatic migration occurs.

The new disjoint row variant is `{faces, endpoint_faces, target}`. `faces` is a
sorted pair of stable semantic face IDs resolving to exactly one straight native
edge; `endpoint_faces` contains two distinct canonically ordered signatures, each
a sorted nonempty list of additional stable faces incident to one native endpoint.
`target` identifies an ordinary managed construction line. For this variant
`inputs.external` requires a solid feature. All rows in a sketch must have the
same source kind; mixed variants reject. Native replay requires exact endpoint
signature equality, so changed identity fails instead of silently swapping points.

This optional feature extension requires the matching updated reader and backend.
Older readers reject the unfamiliar strict row shape; they must not drop it.
New rows use existing document schema 2 and typed result 2/3, not a reinterpretation
of legacy rows. Relevant replay rows and solve support contexts carry bounded
`projection_edges` native endpoint evidence bound to the exact source. These are
disposable replay values, never saved coordinate authority. Guarded edge catalogs
may additionally expose endpoint signatures for straight-edge authoring; blend
selection remains available for edges without those independent vertex identities.

### Circular solid-edge projections (development)

A new strict solid-source projection row is
`{"kind":"circle","faces":["stableFaceA","stableFaceB"],"target":"constructionCircle"}`.
The face IDs remain sorted unique stable native references. It may coexist with
unchanged straight-edge rows on the same solid source; it has no endpoint fields.
Earlier readers reject the new row rather than reinterpret it. Existing documents
and straight-edge rows require no migration and keep their existing representation.

Native `projection_edges` evidence for this variant has exactly `kind`, `faces`,
`center`, `normal`, and `radius`. Center and unit normal are world-space analytic
values; radius is in millimetres. The edge must be one uniquely resolved full
native circle, and its plane normal must be parallel to the target sketch normal.
Partial arcs and tilted circles (elliptic projections) are rejected. Check/replay
updates the managed fixed center and radius constraints from fresh source geometry;
saved construction coordinates are not authoritative source geometry.

Edge catalog entries may additionally carry `circle` with exactly `center`,
`normal`, and `radius`; the existing polyline remains only a transient hit target.
A catalog entry cannot carry both circular and straight-endpoint evidence.
This requires matching updated add-on and backend readers; old readers reject
new catalog evidence explicitly.

### Versioned logical support-plane intent

An attached `sketch_constrained` feature may additionally save `support_intent`:
`version: 1`, `policy: "preserve_plane"`, `signature` and optionally
`source_signature`. Each signature is exactly a planar surface record with
`surface: "plane"`, positive `area`, three-coordinate `centroid` in mm and unit
`normal`. The chosen signature is the saved attachment anchor/plane;
`source_signature` is the original unsplit source face workplane. Omission uses
the chosen signature as source baseline. Both records are deeply immutable in
the core and covered by canonical serialization/hash. Unknown policy/version or
fields are rejected; no snapshot face index can be stored as persistent support.

Complete proven ordinary Cut ancestry, with one stable image or coplanar split
images, may resolve the logical workplane
using this versioned rule while leaving every native descendant's face identity
unresolved/snapshot-local. The chosen anchor's local U/V offset is transported
onto the current stable original source workplane. This is the existing
projected-world-axis convention, not arbitrary material-spin matching. Native
replay and the Blender validator independently derive the same support plane.
The derived decision is not a saved successful-face cache: exact current ancestry
is required again after reopen. Missing `support_intent` retains strict behavior.

New UI face sketches capture this visible default. Explicit repair, Strict or
replacement-face edits are canonical document edits under the normal session
Undo system. Existing legacy split records can explicitly adopt the current
original source plane with a disclosed new anchor, not a fabricated old one.
See [MCAD-TNP-SUPPORT-001](regressions/topology/support/MCAD-TNP-SUPPORT-001.md)
for examples, evidence, rejection cases and limitations.


#### Optional saved orientation

`support_intent.orientation` may contain exactly `policy: "minimal_twist"` and a
unit `tangent` perpendicular to the saved source normal. Omission preserves the
existing World axes behavior; old records are never implicitly upgraded. New
authoring captures this tangent explicitly. Its shortest normal-to-normal
rotation drives the logical frame, including stable exact supports, without
altering native topology identity. Near-antiparallel normals require explicit
World axes selection or a disclosed saved-frame reset. This is not material-spin
inference. See [MCAD-TNP-SUPPORT-002](regressions/topology/support/MCAD-TNP-SUPPORT-002.md).
Readers predating this optional field reject it rather than silently discarding it.

#### Optional source-feature binding and transient Cut ledger

New capture saves `support_intent.source_feature`, an authored feature ID which
supplied the required `source_signature`. It must resolve to a current stable
planar `support_face` reached through consecutive ordinary Cut base edges. This
allows complete native Modified/unchanged/deletion evidence to compose through
multiple splits without reinterpreting the source-relative anchor. Older records
without this field retain their existing immediate-source rules. Unknown readers
reject the field rather than silently ignoring its meaning.

Typed v2/v3 Cut replay rows carry `cut_ancestry` (null on failure), with version 1
and complete `sources` records for both inputs: `port`, `source_id`, `deleted`,
`modified`, `generated`, `unchanged`. Image lists contain only current output
topology handles. Full clients bind every source/image to the same fresh replay
and check descriptor agreement; these handles and ledgers are never canonical
model authority. Legacy result v1 is unchanged. See
[case 003](regressions/topology/support/MCAD-TNP-SUPPORT-003.md).

## Sweep section placement

A Sweep may explicitly opt into version-1 `sweep_placement` construction intent.
Omitting it retains authored coordinates and the original serializer semantics.
See [the complete placement rule and limits](SWEEP_PLACEMENT.md). This field
never grants persistent face identity.
