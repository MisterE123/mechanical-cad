# Assembly transport and disposable instance display

This boundary is infrastructure for the assembly workflow. It does not register
assembly UI or add a second canonical model. Part and Assembly state owners must
explicitly coordinate authoring, persistence, Undo, and report invalidation.

## Transport

`assembly_bridge.assembly_action(assembly, action="assembly_replay", *,
coordinates=None, requirements=None, policy=None, samples=None, project_root="",
python_executable="", timeout=60.0, preset_id=None)` executes one isolated sidecar request and
returns a validated `AssemblyResponse`, a dictionary subclass. Supported actions
are `assembly_replay`, `assembly_check`, and `assembly_sample`. Every optional
request field is present, preserving the distinction between null and an empty
object/list. `validate_response(request, response)` is available for validating a
previously received wire envelope against the exact outstanding request.

`bridge._exchange_raw` owns the common bounded JSON/process transport. The legacy
Part `_exchange`, `replay`, and geometry-action contracts remain unchanged. The
assembly module imports no Blender, core model, OCCT, or solver modules.

Before any result can become display state, validation checks:

- Explicit integer protocol versions and assembly/action identity.
- `input_fingerprint`, SHA-256 over sorted compact finite JSON of the full raw
  request. A result for another pose, policy, source, or sample list is rejected.
- Canonical assembly and embedded Part hashes, each over sorted, indented JSON
  plus one terminal newline. Canonical serializer defaults cannot change supplied
  fields. All definition, source, frame, joint, and instance bindings are checked.
- Request echo, request fingerprint, supported policy/evaluator identity, runtime
  metadata, report fingerprint, and all pose fingerprints. The report fingerprint
  also includes errors and source-replay diagnostics. The service's typed-argument
  fingerprint is retained and checked for SHA-256 syntax; the exact raw-request
  hash and echo bind this JSON-only client independently of direct-Python inputs.
- Finite mesh vertices, triangle indices, unit WXYZ quaternions, literal datum
  frames, successful per-definition B-rep/mesh gates, and complete source replays.
- Full effective coordinates, authored limits, exact requested-coordinate echo,
  complete sampled base maps, and every explicit sample/pair outcome. Invalid
  coordinates never fall back to saved values. A blocked world-bounds composition
  may retain already validated effective coordinates, but has no transforms.
- Independent completeness, known-interference, known-clearance-violation, and
  threshold-contact flags. An incomplete result cannot pass; an unknown pair or
  blocked sample cannot hide known violations elsewhere. Distance witnesses are
  finite and agree with the reported distance. Small positive overlap is never
  accepted as a clear complete result.
- Existing 2 MiB request / 64 MiB response transport limits; at most 16 sources,
  definitions, and instances, 128 frames, 15 joints, 32 samples, and 4096 pair
  queries. Each mesh is limited to 100,000 vertices and 200,000 triangles.

These checks detect malformed/stale transport and inconsistent claims. Hashes
are not signatures or a sandbox, and the validator does not independently rerun
OCCT or solve kinematics. The configured sidecar remains trusted software.

Persisted verification intent is explicit. Canonical assemblies include
`verification_presets` (default `[]`) and `active_verification_preset` (default
`null`). The boundary validates at most eight named presets with at most 120
uniquely identified, normalized instance-pair requirements each. Engineering
minimum clearance and numerical query tolerances remain separate. A `clearance`
preset has named requirements; an explicit `interference_only` preset has none.

`preset_id=None` uses only the explicitly saved active preset. It never selects
the only available preset automatically. A supplied preset ID must be valid and
existing; empty IDs cannot silently fall back. Selected presets reject ad-hoc
requirements/policy overrides. The exact selected preset, named requirements,
resolved tolerances, and `report.verification_basis` are bound and checked.
Without a selected preset, `requirements=None` means `unconfigured`: interference
evidence may still be complete, but neither a pose nor its aggregate can pass.
Explicit `requirements=[]` means `ad_hoc_interference_only`; a nonempty list means
`ad_hoc_clearance`. Replay has `not_requested` basis and never passes.

A rejected schema/request can raise `BridgeError` with the sidecar's readable
error. Validated blocked/partial outcomes return their complete error/report
instead. `ok` indicates operation completeness, not absence of interference.
Replay is never a clearance pass. Sampling guarantees only the listed discrete
poses, never continuous collision freedom, load capacity, or manufacturing fit.

An `AssemblyResponse` is detached from its input dictionaries. Its
`request_snapshot()` method returns a detached copy of the exact raw request for
persistence and revalidation. Mutation after validation invalidates its display
capability. Persist plain JSON if needed, then
revalidate against the original request before displaying it; never manufacture
an `AssemblyResponse` to bypass the bridge.

## Disjoint display ownership

`assembly_display` uses only `mechanical_cad_assembly_*` ownership, definition,
instance, frame, revision, and role tags. It never sets the Part ownership key.
Consequently, existing Part cleanup/regeneration cannot consume assembly siblings
or overwrite the assembly snapshot. All unrelated objects remain untouched.

Each part definition has one recentered disposable mesh shared by its repeated
instances within a publication. Instances are separate mesh objects; authored
frames are separate tagged arrow empties with composed part-local placements.
Empty names and object names are labels, never persistent CAD identity.

For canonical millimetre vertex `p`, definition mesh origin `o`, rigid placement
`(R,t)`, and `s = 0.001 / scene.unit_settings.scale_length`:

- Mesh-local vertex = `s * (p - o)`.
- Object rotation = the rigid WXYZ quaternion.
- Object translation = `s * (R * o + t)`.

Origin subtraction and rotated-origin compensation happen in double precision
before conversion to Blender float32 data. Scene unit settings and canonical mm
values are never rewritten. Tiny distant parts retain local mesh dimensions;
large world-coordinate placement is still limited by Blender's float32 precision.
Affected objects carry a visible-to-UI precision-warning property.

## Reversible publication API

`stage(scene, owner_id, validated_response, *, pose_index=None, show_frames=True)`
constructs and validates all new meshes, instance objects, and frame objects while
they are unlinked from the scene. It returns a `DisplayTransaction`.

`pose_index=None` displays `report.base_pose`, including for a sampling report.
An integer selects one explicit sample. A blocked pose cannot be displayed. A
complete current geometric replay may still be displayed when its pair checks
are incomplete or find violations; the report must retain that distinction.

Use one short synchronous transaction around canonical publication:

```python
transaction = assembly_display.stage(scene, owner_id, validated_response)
try:
    transaction.publish()
    # Commit candidate canonical JSON/revision/report in the state owner here.
except Exception:
    transaction.discard()  # Rolls back if publication had completed.
    raise
else:
    transaction.finalize()
```

- `publish()` checks scene unit scale, original owned-object membership/links,
  response integrity, and staged geometry before swapping. It returns new objects.
- A staging failure cleans newly allocated objects/meshes without touching the
  old display. A publication failure restores original links.
- `rollback()` after successful publication restores the original objects and
  collection links. Old objects are retained until finalization, so a subsequent
  canonical-state commit failure is recoverable. `discard()` also handles staged
  transactions and is safe after rollback.
- `finalize()` marks the accepted display finalized, then removes only now-orphaned
  old owned objects/meshes. Other scenes' linked objects and meshes are preserved.
  Cleanup exceptions are caught in `transaction.cleanup_warnings`; the state owner
  can show that warning while retaining a successful Apply. A partially completed
  cleanup cannot turn accepted canonical/display state into a failed operation.
  Finalized transactions cannot roll back; no implicit destructor commits or
  destroys scene state.
- `replace_display(...)` is a display-only convenience that stages, publishes,
  and finalizes. It must not replace the above transaction around canonical edits.

The caller must discard a staged transaction it no longer wants. Do not leave a
published transaction pending across user interactions or asynchronous callbacks;
commit/rollback immediately and then finalize. This boundary does not mutate
canonical JSON, and cannot itself restore a state owner's partially committed
canonical fields.

Shared collection links are preflighted. If an owned object's collection is
reachable from another scene, replacement is rejected before mutation. An object
linked through separate scene collections is unlinked only from the selected
scene. No global clear, remove-all, hide-all, or selection-changing operation is
used. Visibility policy for workspaces/view layers belongs in the state/UI owner.

## Detecting edited caches

`trusted_display(scene, owner_id, validated_response, *, pose_index=None,
show_frames=True)` verifies the exact object set, IDs, revision, scene scale,
geometry, quaternion, translation, and neutral object-transform state. It rejects
manual mesh edits, parenting, constraints, modifiers, animation, shape keys,
delta transforms/scales, missing/extra/duplicate objects, and stale/mutated input.

A true return means the cache still matches that validated response. It is not a
claim that the report passed, that a B-rep was checked again, or that Blender edits
are canonical. A state owner must visibly invalidate verification when this check
fails; rebuilding restores display from the canonical snapshot. Blender object
transforms must never be read back as authored joint coordinates.

## Verification

- `tests/unit/test_assembly_bridge.py`: native-free import, successful/blocked
  actions, canonical defaults, exact echo and stale hashes, source/ID/mesh/frame
  corruption, requested/effective pose integrity, full sampling, witnesses,
  aggregate evidence, configured-preset identity and no implicit pass, response
  mutation, timeout, and process failure.
- Legacy bridge and add-on architecture tests verify Part compatibility and the
  native-free acyclic import boundary.
- `tests/blender_assembly_display_smoke.py`: native Blender 5.2.2 LTS, real sidecar
  geometry, nonzero origins plus rotations at three unit scales, shared instance
  mesh, literal frame axes, manual display mutations, stage/swap/commit rollback and nonfatal post-commit cleanup failures,
  linked objects and shared collections across two scenes, sibling protection
  during Part regeneration, and tiny far-origin geometry. Run with
  `--background --factory-startup --python-exit-code 1`; require the explicit
  `ASSEMBLY_DISPLAY_SMOKE_OK` marker.

This headless evidence does not establish a usable assembly authoring UI,
installed-ZIP integration, Undo/Redo or save/reload integration, asynchronous
execution, or cross-platform support. Those remain separate integration gates.

## Module boundaries

`assembly_bridge.py` retains the public transport/validated-response API. Private
validators are split into `assembly_validation_common.py` (finite JSON and identity
primitives), `assembly_validation_model.py` (canonical model/mesh/preset payloads)
and `assembly_validation_evidence.py` (coordinates, poses, pair queries and
aggregation). They import one way and remain usable without Blender or native CAD.
The module-only split preserved every function/class AST and passed the unchanged
adversarial and native display suites.
