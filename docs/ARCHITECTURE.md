# Architecture and invariants

This describes the current source architecture. Older milestone names below
are historical context, not a restriction to the early rectangle prototype.
Current supported tools and limits are listed in INTEGRATED_MODELING.md.

## Ownership boundaries

1. **Document model** (`model.py`) is the canonical saved design. It has a version,
   millimetre units, immutable snapshots, named parameters, stable feature IDs,
   typed graph inputs and an active output. List position is display history;
   dependency edges determine regeneration order. JSON contains no executable code.
2. **Arithmetic parameters** (`expressions.py`) form a second, bounded dependency
   graph. Arithmetic is interpreted from an allowlisted AST; it is never `eval`.
   Syntax and magnitude limits prevent code execution and pathological expressions.
3. **Replay engine** (`engine.py`) executes features in stable topological order.
   It creates fresh geometry each time. A failure blocks dependent features, while
   independent branches continue and report their results. A failed document
   cannot be exported. There is no silent stale-geometry fallback.
4. **Kernel adapter** (`kernel_ocp.py`) is the only OCCT-dependent module. It owns
   native B-reps, operation histories, exact validation, triangulation and export.
   Adapter handles never cross the process boundary or enter JSON.
5. **Topology resolver** (`topology.py`) only accepts explicit, stable semantic
   provenance. Geometric similarity produces suggestions, never automatic
   face-identity repair. Split, merge, deletion and unknown face identity fail closed.
   The separate versioned `support_intent.py` rule can preserve a constrained
   sketch’s logical plane across complete proven coplanar Cut descendants, with
   visible explanation and correction. It never picks/promotes a fragment identity.
   Source-bound intents additionally compose complete request-only native Cut
   ledgers through consecutive Cuts; snapshot handles are never saved authority.
   See `regressions/topology/support/MCAD-TNP-SUPPORT-001.md` and case 003.
6. **Sidecar** (`sidecar.py`) accepts one bounded protocol-v1 JSON request on stdin,
   replies with one JSON value on stdout and exits. Native logs go to stderr.
   It is an ABI boundary, not a sandbox. There is no network listener, pickle,
   external-command operation or authentication surface.
7. **Geometry actions** (`actions.py`) freshly replay the canonical document,
   validate the active solid, and perform explicit checks or atomic part exports.
   Model data cannot trigger file writes. The CLI and sidecar share this service.
8. **Blender add-on** provides authoring, display, document persistence and status.
   It invokes a configured sidecar interpreter without a shell. Mesh objects are
   disposable display caches. Native Blender mesh editing does not change B-reps.

## Distinct histories

- Feature history describes how the part is constructed and is saved in the model.
- Blender Undo tracks interactive session edits.
- Git tracks this software's source changes. It does not automatically record user
  model edits, commit in user repositories or replace feature history.
- A future opt-in model-history backend can snapshot canonical JSON and named
  checkpoints. It must remain a separate adapter; merges of dimensions/references
  need design-aware validation. No model-Git integration is claimed in version 0.2.

## Determinism

Identical documents are canonically serialized with stable key ordering and a
SHA-256 content hash. Graph ordering and arithmetic resolution are stable. Replay
is expected to reproduce geometry within the pinned kernel/tolerance environment;
exact binary CAD exports or triangulation across kernel versions/platforms are not
promised. Mesh vertex/face indices and snapshot face IDs are not design references.

## Units and constraints

Document schemas 1 and 2 store all geometry and expressions in millimetres. Blender display
coordinates are derived from millimetres using `0.001 / scene.scale_length`,
so changing Blender's unit scale does not change the part's physical size. Formula operands
are scalars in this convention; dimensional analysis and mixed-unit formulas are
not implemented. A rectangle is a constrained primitive by construction; this is
not a general constraint solver. A circle is likewise a primitive radius/location.
Schema 2 separately adds typed line sketches and the optional real libslvs solver;
primitive features never acquire hidden constraints.

Primitive profiles live on XY planes at explicit Z offsets. Constrained sketch
records carry explicit origin/quaternion workplanes; their extrusions follow the
plane normal. `sketch_model.py` owns strict pure records and expression resolution;
`sketch_solver.py` lazy-loads libslvs only inside the sidecar and returns actual DoF,
residual and diagnostic IDs. Analytic profile processing supports connected line/arc boundaries and
supported nested holes while retaining authored provenance. Face-attached
sketches and projected references use explicit canonical dependencies and
validated upstream evidence, never a guessed mesh identity. Rectangle and
relation tools expose their authored intent; they do not silently infer extra
constraints from pointer proximity. The current UI uses datum and supported
associative planar-face frames.

## Versioned sketch outputs

Typed sketch outputs were introduced without reinterpreting legacy documents.
Circle, line and arc entities and their constraints carry stable authored IDs.
Current general authoring chooses the supported result-version contract per
operation; legacy defaults remain compatibility paths. See ADR 0005,
SKETCH_SERVICE.md and the arc/output-contract documentation for these boundaries.

`outputs.py` separates solved sketch data, available profile faces and actual
solids. `sketch_evaluation.py` shares solver evidence between full replay and
`sketch_service.py`; the solve-only action has no OCCT import. `sketch_protocol.py`
bounds the new request path and binds its exact input. An open supported chain
is a successful sketch with no shape, while a dependent extrusion is explicitly
blocked. Unsupported region policy is distinct from constraint failure. Check
and export consume a real typed solid, never an inferred or stale mesh.

## Bounded assembly boundary

The post-0.2 backend adds a separate versioned assembly envelope with embedded
unchanged Part snapshots, reusable definitions, named literal mate frames,
instances and rooted fixed/revolute/slider/cylindrical/planar/ball trees.
Optional directed revolute gear relations derive controlled coordinates before
forward placement; they do not add spatial mate edges or a closed-loop solver.
See ASSEMBLY_GEAR_RELATIONS.md.
Planar-face mate frames can be explicitly associative; ordinary sampled surface
frames remain literal. See ASSEMBLY_FORMAT.md,
ASSEMBLY_GEOMETRY.md and ASSEMBLY_SERVICE.md. The development authoring workflow
and reversible display-publication boundary are described in ASSEMBLY_WORKFLOW.md
and ASSEMBLY_TRANSACTIONS.md; native headless coverage does not establish
interactive usability or installed-package qualification.

Instance placement and mechanical mates must be explicit model data,
not inferred from Blender collection parenting, rigid-body simulation or bones.
An assembly solver should return transforms, residuals, remaining degrees of
freedom and failed mate explanations. Interference/clearance and motion-limit
verification consume exact solids. These bounded checks are not structural/load
analysis or certification for manufacturing. A known violation stays visible
when another query is incomplete; sampled poses never imply continuous clearance.

UI sketch drafts are separately versioned transactions bound to exact canonical
base JSON. Workspace/window resources are transient; raw draft input is retained
in scene UI data for explicit compatible Resume. Legacy rectangle drafts and current general command checkpoints remain
distinct versioned records. The general editor supports drawn geometry,
dimensions, explicit relations and retained tool proposals; shared lifecycle
hooks do not assume four points or two dimensions. Kind/version dispatch never
implicitly reinterprets an older rectangle record.

## Security and operational limits

The sidecar executes trusted installed software and user-selected Python. Only
open local model files you intend to inspect. Maximum input size is 2 MiB, with
256 features and 128 project parameters. Positive dimensions are bounded to
1e-6–1e6 mm, coordinates to ±1e6 mm, mesh deflection to 0.001–10 mm. These bounds
are guardrails, not a guarantee against expensive boolean geometry. The add-on
uses a process timeout so a failed kernel does not hang Blender indefinitely.

No background telemetry, network access, cloud storage or automatic Git actions
are part of this project.

## Installation portability

The initial verified sidecar is CPython 3.12 on Linux x86_64. OCP wheels list
additional supported platforms, but this project's Windows/macOS installation
flows have not yet been exercised. A published wheel's existence is not a passed
project integration test. Blender 5.2.2 is the requested target LTS; a standalone
`bpy` wheel test is reported separately from a native Blender GUI test.

## Blender module map

The add-on entry point keeps metadata and lifecycle exports only. Implementation
modules have one-way dependencies and keep native CAD imports out of Blender:

- `common.py`: shared ownership tags and unit constants; no Blender imports.
- `bridge.py`: strict JSON/subprocess protocol; no Blender imports.
- `request_contracts.py` / `part_contracts.py`: transport-free bounded JSON and
  shared canonical snapshot identity; compatibility adapters reuse these leaves.
- `sketch_bridge.py` / `sketch_action_bridge.py` / `part_result_bridge.py`:
  opt-in typed sketch, solve-only and full Part evidence validation. Full replay
  binds the exact request, dependency graph and conservative face provenance.
- `geometry_evidence.py` / `topology_evidence.py`: shared strict nested geometry
  schemas and source-bound face metadata. `part_geometry_evidence.py` binds
  successful/partial checks and export receipts to a complete typed replay.
- Core `part_snapshot.py` and add-on `part_snapshot_bridge.py`: authoritative
  canonical source identity with strict, native-free receipt validation.
- `guarded_operations.py`: higher-level guarded operation/canonical-capture
  adapters. Legacy validators stay below guarded transport so imports remain acyclic.
- `sidecar_job.py`: bounded process ownership/cancellation, without Blender access.
- `part_publication.py`: captured one-shot main-thread publication of an exact
  completed typed replay through the shared rollback seam; see ASYNC_SKETCH.md.
- `assembly_pending.py` / `assembly_job_ui.py`: exact-input publication guards,
  main-thread modal interaction and detached process-only lifecycle cleanup.
  The same owner admits non-publishing independent-driver motion replay. Its
  receipt is revoked after returning a detached full-assembly ghost projection;
  it never writes canonical data, accepted display objects or report fields.
  `assembly_motion_draft.py` changes only one independent revolute coordinate.
  The existing viewport owner debounces input and discards superseded responses;
  Apply requires fresh replay to match the exact completed full preview pose.
  Its load-only display-rebuild purpose returns fresh guarded evidence to the
  single `history_rebuild.py` restoration owner. `publish_restored_display` stages
  only accepted Assembly caches, never canonical/source/report text; restored
  check history retains no runtime report binding.
- `assembly_bridge.py`: assembly transport and validated response lifecycle. The
  native-free `assembly_validation_common.py`, `assembly_validation_model.py` and
  `assembly_validation_evidence.py` separate finite JSON/schema primitives,
  canonical embedded-source payloads, and exact pose/query evidence checks.
- `assembly_edit.py`: detached JSON candidates for explicit Part reuse, literal
  frames, joints and saved verification intent; never publishes or certifies.
- `assembly_display.py`: separately owned instance/frame display, centered mesh
  conversion, staged publication/rollback and integrity checks.
- `assembly_properties.py` / `assembly_state.py`: separate saved assembly state,
  scene/window/revision-bound transactions and current-evidence lifecycle.
- `assembly_operators.py` / `assembly_operator_helpers.py`: explicit user-Part
  capture, reusable instances, literal frames, tree joints and source updates.
- `assembly_files.py`: validated atomic portable assembly file operations.
- `assembly_ui.py` / `assembly_verification_ui.py`: named assembly history,
  persisted verification-intent controls and explicit per-pose evidence.
- `sketch_display.py`: explicit result-version negotiation and source-bound solved
  open-chain display, with no triangles, solid volume or manufacturing evidence.
- `display.py`: owned viewport mesh, precision/origin handling and trusted stale cache.
- `document_state.py`: canonical scene JSON, parameter callbacks, replay and transactions.
- `staged_edit_store.py`: lower-level transient proposal storage and lifecycle;
  receives validated replay data and a captured binding-revocation capability,
  never imports the document coordinator or publishes geometry.
- `staged_edit.py` / `staged_edit_ui.py`: higher-level explicit repair service and
  proposed-only controls. Repairs publish through `document_state.py`; the
  detached proposal is never exported or published without full replay. Separate
  versioned repair intent can be checkpointed in .blend; explicit Resume freshly
  validates every retained state without publishing accepted geometry.
- `end_face_repair.py` / `end_face_repair_ui.py`: explicit proposal-only Up to Face
  target replacement from guarded current replay. Preserve profile/direction/offset;
  catalog choices never authorize publication. Initial proposal ancestry bounds
  downstream eligibility after retargeting, never supplies geometry evidence.
- `repair_resume.py`: main-thread cancellable Resume input owner over the shared
  guarded sketch transport and assembly job supervisor. An opaque reservation
  spans jobs, never grants native authority, and blocks competing Part actions.
  Only final fresh validation installs a live proposal; cancel retains raw intent.
  The shared validation plan also serves the explicitly synchronous script API.
- `repair_intent.py` / `repair_scope.py`: strict bounded data-only repair checkpoint
  codec and shared original/partial-edit scope validation. Saved text never grants
  native authority. Save pre/post/failure hooks retain one live owner until a
  successful checkpointed save; failed Resume preserves exact raw text.
- `properties.py`: RNA storage and interpreter/tessellation preferences.
- `help_topics.py` / `help_ui.py`: concise explanation catalog and same-dialog help.
- `operators.py`: explicit authoring/file/navigation commands.
- `geometry_operations.py`: canonical check/export dialogs and outcome reporting.
- `sketch_draft.py`: pure transient rectangle state and optimistic edit candidates.
- `general_sketch_commands.py` / `general_sketch_journal.py` /
  `general_sketch_draft.py`: pure stable-ID commands, bounded replayable local
  history, raw input and exact solver/Part acceptance gates.
- `general_authoring.py` / `general_authoring_store.py`: separate, bounded tool,
  selection, provisional geometry and annotation-placement intent. These do not
  change canonical manufacturing meaning or restore gesture capture.
- `sketch_session.py` / `draft_dispatch.py`: one shared viewport owner, strict independent codec dispatch, original-scene checkpoint/recovery and resource cleanup.
- `viewport_sketch.py` / `sketch_overlay.py`: rectangle authoring, modal commands
  and lightweight preview; compatibility hooks delegate to the shared owner.
- `general_session.py` / `general_viewport.py`: general line/circle owner and
  modal interaction, sharing the existing session, async and publication seams.
- `pending_line_length.py` / `pending_circle_diameter.py`: separate strict, data-only
  unfinished primitive size inputs. `line_length_session.py` / `circle_diameter_session.py`
  validate detached structural candidates through the current owner and checkpoint CAS;
  neither path publishes a Part or edits an existing driver.
- `reference_dimensions.py`: bounded explicit read-only annotation role and stable
  authored entity bindings, with no measured-value cache or solver record. Existing
  annotation/draft schemas accept this additive binding variant; legacy bindings
  retain their exact form. Missing bindings stay unavailable, not rebound.
- `general_view_geometry.py` / `general_sketch_overlay.py`: detached display
  geometry, conservative picking and bounded drawing; no solver authority.
- `constraint_selection.py` / `constraint_diagnostics.py`: pure explicit selection
  requirements and immutable exact-bound failed-solve candidates.
- `constraint_actions.py`: transient prepared constraint intents, strict solved
  seed access, disclosure/stale guards and delegation to the owner command path.
- `constraint_ui.py`: bounded relation inspector, explicit point-ID controls,
  native confirmation dialogs and local journal actions; no separate lifecycle.
- `workspace.py`: owned tab setup with one native layout transition per timer phase.
- `workspace_ui.py`: scoped native icon palette, named menus and feature-history panels.
- `panels.py`: feature-list and panel rendering.
- `history_rebuild.py`: one debounced, exact-bound async accepted-Part replay after
  history restoration or file load, with no canonical write or Undo push. Load
  tickets separately preserve opaque dormant repair/draft intent; they never
  Resume it. Assembly workspaces skip this Part-only load path. See HISTORY_REBUILD.md.
- `registration.py`: class lifecycle, deferred restricted-context rebinding and cleanup.

Do not add core modeling logic to panels/operators. Workspace, viewport and solver
layers share the canonical document and transaction boundaries; none owns a second
model. Native diagnostics are strictly validated before becoming current display
state. During an active draft, committed solver counts are hidden to prevent an
old result from being mistaken for the current draft state.

## Direct selection and parameter presentation

Direct viewport selection resolves a display triangle only after the complete
current display is bound to its accepted source evidence. The triangle maps
to an explicit stable face ID; triangle numbers are not saved design identity.
Modified, stale, instanced, unknown or unsupported geometry fails visibly. Blend
selection uses a separate guarded native edge catalog for a one-click supported
edge, translated into existing stable face-pair intent. Two-face picking remains
a fallback and native replay retains the unique-edge check. No edge identity is
invented from tessellation diagonals. See DIRECT_EDGE_PICKING.md.

Existing Fillet/Chamfer/Shell reselection uses `solid_review.py`: a separately
owned input-body display and captured read-only replay receipt. Optional picker
snapshots cannot replace the accepted current-result association. The canonical
active output remains unchanged; a completed pick returns retained editor fields
for the normal whole-document atomic Apply. See VISUAL_FEATURE_RESELECTION.md.
`solid_projection_picker.py` reuses the same `InputBodyReview` lifecycle for an
explicit earlier-solid chooser inside a live sketch. Frozen RNA choices are UI
only; source membership, sketch revision and accepted runtime remain separately
captured guards. The pick adds one ordinary source-qualified draft command,
restores display state and does not change canonical output or runtime.

Hover highlighting is a transient draw resource and never edits geometry.
Picking and numeric-entry lifecycles must preserve accepted model data, user
selection and Undo on cancellation or context changes. Parameter usage hints
inspect expressions without evaluating model text or changing its dependencies.

### Explicit projection source ports

Multi-source drawn sketches bind every projection to its exact input port and
source feature. Replay and independent result validation keep solid edge evidence
source-qualified, including when two bodies share semantic face labels. See
[ADR 0009](adr/0009-explicit-projection-source-ports.md) and the
[multi-source authoring workflow](MULTI_SOURCE_PROJECTION.md).

## Optional local recovery boundary

`recovery_store.py` owns bounded, checksummed exact-text envelopes and private
atomic two-generation disk storage. `recovery_capture.py` fences unsettled
postchecks. `local_recovery.py` owns the default-off preference UI, main-thread
observer and explicit fresh-Scene restore. No native authority, model path or
saved scope ID crosses this boundary. Recovery failure is status-only and cannot
fail a committed CAD operation. See [Local Recovery](LOCAL_RECOVERY.md) for
identity, retention, unsupported work and the best-effort capture interval.
