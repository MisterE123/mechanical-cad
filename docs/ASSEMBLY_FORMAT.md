# Assembly snapshot format and tree kinematics

This is the native-free model/evaluator contract. It does not establish native
geometry correctness, UI usability, continuous collision freedom or manufacturing
fitness. The Part feature graph and the assembly graph remain separate.

## Version and limits

An assembly has `kind: "assembly"`, `assembly_schema_version: 1`, a stable `id`,
`name`, `length_unit: "mm"` and `angle_unit: "rad"`. It embeds existing canonical
schema-1/2 `Document` snapshots without changing their serialization or hashes.
No migration of Part documents is implicit.

All envelope fields are required unless explicitly described below. Duplicate or
unknown keys, unknown joint kinds, nonfinite values, boolean-as-number, and
unit-bearing numeric strings are rejected. JSON has one total 2 MiB UTF-8 budget,
a nesting cap of 20 and numeric-token cap of 128 characters. Accepted snapshots
have at most 16 sources, 16 definitions, 16 instances, 128 mate frames in total,
and 15 joints. Up to 8 verification presets may each contain 120 named clearance
requirements, with a total cap of 960. The service separately limits motion to 32 samples and 4096 pair
queries. These are initial guardrails, not scalability claims.

Assembly/definition/frame/instance/joint IDs use 1–128 ASCII characters:
`[A-Za-z0-9_][A-Za-z0-9_.-]*`. Source-document IDs retain the existing Part
Document's text-ID contract, so legacy identities are not renamed. Names are
nonempty text up to 256 characters. Definitions, mate frames, instances and
joints accept an omitted `name`, normalized to their ID; serialization always
writes the resulting name. Explicit null names are rejected by the parser.
Names never replace stable IDs as references. Numeric values in assembly records
are serialized as doubles; authored quaternions are not normalized on save.

`AssemblyDocument.from_dict/from_json` and direct typed constructors validate the
complete graph before acceptance. Expected errors use `AssemblyError`, a
`CADException` subtype with a stable `code`. Accepted snapshots are deeply
immutable; `to_dict()` returns detached JSON data. `to_json()` uses sorted keys,
two-space indentation and a final newline. `content_hash` is SHA-256 of these
UTF-8 bytes; `fingerprint` is an alias. Array order is retained as authored order.

## Envelope fields

- `part_sources`: array of `{source_document_id, source_digest, document}`.
  `document` is a complete canonical existing Part snapshot. Its exact ID and
  canonical SHA-256 hash must equal the declared fields. Source identities are
  unique, with exactly one accepted revision per identity. No filesystem path,
  URL or implicit external loading is supported.
- `parts`: array of `{id, name, source_document_id, source_digest,
  output_feature_id, mate_frames}`. Each definition binds an existing source's
  exact revision and an explicit existing solid-output feature. An omitted
  output never falls back to `active_feature`. The output can deliberately be
  another solid in that feature graph. Native replay/validity remains a service
  responsibility. Several definitions may share one source revision.
- `mate_frames`: each definition owns an array of `{id, name, placement}`.
  IDs are unique within that definition. Instance identity scopes repeated
  occurrences of the same part-local frame/provenance.
- `instances`: array of `{id, name, part_id}`. Repeated instances refer to one
  reusable definition; they do not copy display meshes into canonical geometry.
- `grounded_instance`: exactly one existing instance ID, the tree root.
- `ground`: explicit rigid root world placement.
- `joints`: array of the joint records below.
- `verification_presets`: array of explicit named verification presets, described
  below; an empty array means no persisted checking intent.
- `active_verification_preset`: a preset ID or null. A non-null reference must
  resolve exactly. A single available preset is never automatically selected.

Frames are `{xyz_mm: [x,y,z], wxyz: [w,x,y,z]}`. Position components are bounded to
±1e6 mm. The quaternion must already have unit squared norm within 1e-9 and
components within ±1.00000001. A mate's local +Z is its motion axis; local XY fixes
zero-angle orientation. Negative-equivalent quaternions retain their authored
sign and bytes. Temporary transform arithmetic normalizes a copy, never saved
frames or embedded sketch workplanes. No scale, shear or deformation is accepted.
Derived poses also stay within the ±1e6 mm coordinate domain; exceeding that
range blocks the whole pose rather than publishing partial transforms.

## Joints and graph validation

All joints contain `id`, `name`, `kind`, `parent`, `child`, `parent_frame` and
`child_frame`. Parent/child fields reference instance IDs. Frame IDs resolve
strictly in those instances' part definitions.

- `fixed`: coordinate and limits fields must be absent from JSON. Its implicit
  coordinate is zero. Python constructors retain `coordinate=0` as a convenience.
- `revolute`: required numeric `coordinate`, radians about mate +Z, bounded to
  ±1e4 rad. Optional `limits` is null or `[lower, upper]`, with the same bounds.
- `slider`: required numeric `coordinate`, millimetres along mate +Z, bounded to
  ±1e6 mm. Optional limits use the same units/bounds.

Moving-joint serialization always includes `limits`, writing null when absent.
Limits must strictly increase; equal limits are not an implicit fixed joint.
Authored coordinates must lie within inclusive limits. Preview coordinates are
separate from authored values; invalid previews never clamp or change the model.

Each non-ground instance has exactly one incoming joint. Missing entities/frames,
self-edges, incoming joints to ground, duplicate parents, disconnected graphs and
cycles fail closed. Joint list order need not be dependency order. Exactly one
root instance with no joints is valid. Empty/orphan authoring drafts are not saved
assemblies and belong to the UI's separate transaction state.

## Named verification presets

The engineering minimum clearance and the numerical precision of a CAD query are
separate concepts. A `ClearanceRequirement` says how much separation is required
for a named instance pair. A `NumericalPolicy` controls finite-resolution queries
and display tessellation; it cannot stand in for a design clearance allowance.
Neither alone establishes a pass verdict or physical/manufacturing fitness.

The native-free `assembly_requirements.py` records are:

- `ClearanceRequirement(id, name, instances, minimum_mm)`: exactly two distinct
  existing instance IDs and a finite minimum in millimetres, inclusive 0–1e6 mm.
  The pair is unordered and saved in lexicographically sorted order. Reversed
  duplicates are rejected. IDs and names are explicit and required; IDs are
  unique within each preset, and the same scoped ID can appear in other presets.
- `NumericalPolicy(linear_tolerance_mm=1e-6, volume_tolerance_mm3=1e-9,
  linear_deflection_mm=0.1)`: linear tolerance is bounded to 1e-9–1 mm; volume
  tolerance to 1e-15–1 mm³; tessellation deflection to 0.001–10 mm. These initial
  numerical defaults match the exact-check service. Every value is finite,
  strictly typed and has units explicit in its field name. Increasing numerical
  tolerances does not change the named engineering minimum.
- `VerificationPreset(id, name, requirements, policy=NumericalPolicy(),
  kind="clearance")`: a stable, named checking intent. `clearance` requires at
  least one named pair. The explicit alternative `interference_only` requires
  an empty requirements array; it claims no authored clearance allowance.
  Unknown kinds are rejected. The model never infers interference-only intent
  from an empty clearance preset.

Preset JSON always contains exactly `id`, `name`, `kind`, `requirements` and
`policy`. Each requirement always contains exactly `id`, `name`, `instances` and
`minimum_mm`. Its pair is a JSON array. The policy always contains exactly the
three numeric fields above, including any constructor defaults. Missing or
unknown record fields, duplicate IDs/pairs, malformed names, booleans, strings,
nonfinite values and dangling instance references are rejected before native
work. Each preset has at most 120 pair requirements; the assembly's 8-preset/
960-total limit and shared 2 MiB budget also apply. Presets may intentionally use
the same pair with different minima for different named operating conditions.

The currently unreleased assembly schema 1 always serializes both envelope
fields, even as `verification_presets: []` and
`active_verification_preset: null`. Earlier pre-release envelopes lacking these
fields load with those explicit no-preset defaults. No active selection or pass
policy is guessed. Adding the fields changes those older pre-release assembly
hashes on normalization; it does not change any embedded Part schema-1/2 bytes or
hashes. An active reference cannot survive deletion of its preset unless the
same explicit edit clears or replaces the selection.

Changing a requirement, numerical policy, preset name or active selection changes
the assembly hash and invalidates all bound pose/report fingerprints. It does
not change source hashes, geometry, authored joint values or physical instance
transforms. The pose digest deliberately includes the complete assembly revision,
so a different digest here denotes revision invalidation, not changed placement.
Source updates preserve preset/requirement IDs, values and selected intent while
revalidating all referenced instances. Native verification and UI publication are
separate service/transaction responsibilities.

## Kinematics API and outcome identity

`evaluate(assembly, coordinates=None)` computes:

`child_world = parent_world * parent_frame * motion(q) * inverse(child_frame)`

It returns an immutable `PoseResult`. `status` is `evaluated` or `blocked`.
`transforms` maps instance IDs to rigid Frames; a blocked result has no current
transforms. `structural_dof` counts moving tree joints, with
`dof_method: "rooted_tree_joint_count"`. A supplied pose or a joint at a limit does
not remove this structural coordinate. This is forward tree kinematics, not a
general constraint solver or Jacobian-rank calculation. No fabricated solver
residual or overconstraint claims are included.

Every result, including blocked requests, includes:

- `assembly_digest`, all `source_hashes`, `pose_digest`, and `evaluator_version`
- `requested_coordinates`: exact supplied joint overrides (empty for no override)
- `effective_coordinates`: the complete map after defaults, keys, types, fixed
  coordinates and limits validate; includes fixed zeroes. The `coordinates`
  property is a compatibility alias
- Diagnostics and status

Invalid input produces an empty effective map, never a default in place of an
invalid supplied coordinate. If coordinate validation succeeds but a derived
transform fails, the valid complete coordinate map remains available alongside
blocked status and no transforms. Nonfinite or nonscalar values supplied through
the direct Python API are represented with explicit `invalid_type` diagnostics in
`requested_coordinates`, making even blocked results JSON-safe; no such value is
accepted as a coordinate. Arbitrary unsupported Python objects retain only their
type, and should not be used as meaningful request identities.

The pose digest hashes assembly/source revisions, requested and effective maps,
status, diagnostics and evaluator version. Thus identical bad coordinates against
different assembly revisions cannot share a current-report identity. Native
verification adds policy, requirements, tolerances, sample list and kernel/runtime
identity to its own report fingerprint; the pose digest alone is not a complete
geometry-verification fingerprint.

`effective_coordinate_map(assembly, overrides=None)` returns a detached complete
validated map or raises `CADException`. Motion sampling must resolve the complete
base map once, then copy it while replacing only the sampled joint. Otherwise a
second joint's preview override could silently reset to its saved coordinate.

## Explicit source updates

`replace_source(assembly, source_document_id, document)` (also available as
`assembly.replace_source(...)`) structurally validates one new canonical source
snapshot and returns a new assembly. The replacement ID must match the original.
It atomically updates every definition referring to that source, preserving all
definition/frame/instance/joint IDs, explicit output IDs, joint data and literal
frame coordinates. Missing outputs/references reject the whole candidate; the
old immutable snapshot remains intact. Independent copies require a new source
Document ID and explicit new source/definition records.

This helper is only pure preflight. Before publishing a source update, the service
must freshly replay and validate all affected explicit outputs; the UI must publish
all affected displays atomically and roll back on failure. Working Part edits never
automatically change accepted assembly sources. Literal frames do not follow
geometry edits: changing a thickness does not move an authored midplane datum.
Future dependent frames require a separate provenance/dependency contract.

No file-writing helper, assembly export, arbitrary mate solving, closed loops,
implicit geometric attachments or native imports are part of these modules.

## Optional directed gear coordinates

The optional `gear_relations` extension couples existing revolute angles with a
signed ratio and phase. Driven joints store `coordinate: null`; their angles
are deterministically derived, never independent saved values. Ordinary files
without relations retain their serialization and behavior. Relation graphs are
acyclic, single-driver and strictly validated; inclusive joint limits still apply.
Sampling uses the complete independent base map and re-derives followers for
every listed pose. See [gear relation schema and workflow](ASSEMBLY_GEAR_RELATIONS.md).

Optional `replay_tolerance_mm` stores explicit display-replay admission resolution
in mm (finite JSON number from 1e-9 to 1; booleans, strings and null are rejected).
An absent field retains 1e-6 mm and is omitted from canonical output for legacy
compatibility. It is independent of saved verification presets and never widens
Check/Sample/export precision. See ASSEMBLY_SERVICE.md for precedence and UI.

## Explicit contact intent (development)

See [intended-contact policy](ASSEMBLY_INTENDED_CONTACT.md) for the optional
named zero-clearance pair exception. Measured clearance pass and threshold flags
remain unchanged; separate authored policy acceptance can permit a fresh STEP
export without claiming exact contact, no penetration, or physical fit. Legacy
defaults stay strict.
