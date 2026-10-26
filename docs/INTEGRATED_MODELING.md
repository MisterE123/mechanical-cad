# Current modeling capabilities and limits

This is the current-source capability entrypoint, not a release certificate.
Development features, source/native checks and exact installed-package evidence
are separate. Consult the package's own receipt for its tested revision; this
guide does not certify an untested build. Historical milestone and
verification documents describe only their named checkpoint.

Start with [everyday modeling](EVERYDAY_MODELING.md), then use the detailed guides:

- [Draw and dimension sketches](GENERAL_SKETCH_WORKFLOW.md),
  [relations](SKETCH_RELATIONS.md) and [closed regions/holes](MULTI_LOOP_PROFILES.md).
- [Project from multiple explicit sources](MULTI_SOURCE_PROJECTION.md) and
  [repair an unapplied edit](STAGED_EDIT_REPAIR.md).
- [Read-only reference dimensions](REFERENCE_DIMENSIONS.md), a bounded UI-only
  length/radius/diameter measurement workflow.
- [Typed lengths and angles](UNIT_INPUT.md), including the literal-only scope.
- [Mirror Result](MIRROR_RESULT.md), a reflected single solid across an explicit datum plane.
- [Solid features](CONNECTED_PART_MODELING.md),
  [extrusion end conditions](EXTRUSION_END_CONDITIONS.md) and
  [assembly workflow](ASSEMBLY_WORKFLOW.md).

## Available in the current source

- Dedicated Sketch, Part and Assembly workspaces with contextual tools, editable
  history, named formula parameters, tooltips and explanations.
- Lines, circles, circular arcs, driving length/radius/angle, diameter entry,
  coincidence, horizontal/vertical, parallel/perpendicular, equal lengths/radii,
  supported shared-endpoint arc tangency, circle-line tangency, point-on-line,
  midpoint, concentric circles, fixed points and construction geometry.
- Multiple closed regions with nested holes and general analytic line/arc loops.
  Disconnected regions are shown but cannot silently become a multi-solid Part.
- XY/XZ/YZ offset sketch planes, model context, plane-normal viewing, saved drafts,
  upstream editing, and basic unconstrained line-end trim/extend with preview.
- Extrude, inward extrude, symmetric/mid-plane, Remove-only Through All,
  explicit Up to planar face with offset, one-step additive/subtractive extrusion,
  union/cut/intersection, revolve, transform, fillet and
  chamfer (all edges or one stable face pair), connected linear/circular patterns,
  repeated linear/circular cuts for separated holes, inward open/closed shell,
  two-profile loft, and solved open line/arc-path sweep.
- Freely drawn constrained sketches and rectangle/circle shortcuts on stable
  planar faces. Their local coordinates, saved drafts and editing follow upstream
  support changes, including supported Boolean and revolved faces.
- Reusable Parts, explicit instance updates, fixed/revolute/slider/cylindrical/planar/ball joints with
  viewport connector placement and motion preview, literal surface picking,
  associative planar-face connectors, up to 64 instances, clearance/interference
  checks at saved or listed poses, and Assembly STEP. Component removal
  previews dependent branches/joints/requirements before one atomic edit.
- Self-contained STEP import of a single valid solid, including supported
  one-component wrappers with placement/units. The 512 KiB source limit and
  snapshot-only imported faces are explicit. The original file is not needed
  after save/reopen; multiple solid occurrences and loose geometry reject.
- Fresh-geometry Part checks and STEP/STL export; save/reopen and editable history.

## User-facing limits still being addressed

- Up to planar face uses the infinite supporting plane of one explicitly selected
  earlier stable face. It must be parallel and ahead in the selected direction;
  positive offset extends past the plane and negative stops short. This is not
  finite-face trimming, Up to Next or curved/nonparallel termination. Creation
  has exact preview; Edit Feature rebuilds atomically. See
  [end conditions and evidence](EXTRUSION_END_CONDITIONS.md).

- External projection links line/circle identities from explicitly chosen earlier
  constrained sketches and solids as construction geometry. One drawn sketch can
  mix several sources; each reference retains its own source binding. Circle
  projections require parallel planes;
  collapsed lines, missing source identities and unsupported curves fail visibly.
  Use Solid Edge projects straight edges and full circles by unique stable face
  pairs. Straight endpoint identity uses additional incident stable faces; circles
  use native centre, normal and radius and require a parallel sketch plane.
  Missing, split, changed or ambiguous identities reject instead of changing the
  reference. Source development adds explicitly bound circular arcs on parallel
  planes; see [arc projection scope and pending qualification](SOLID_ARC_PROJECTION.md).
  Ellipses, arbitrary splines and oblique circular projections remain unsupported.
  Use Solid Edge's source chooser can review different earlier solids without
  finishing the sketch; replacement remains within the reference's bound source.
  See [multi-source authoring and repair](MULTI_SOURCE_PROJECTION.md).
- Cylindrical joints expose independent axial translation and rotation, with
  separate limits and discrete sampling. Planar joints expose XY translation
  and Z rotation; ball joints use XYZ Euler component limits, not cone limits.
  These connectors currently use named frame editing, not direct dragging.
- Mates are rooted trees, not arbitrary closed-loop mechanisms. Surface connector
  samples remain literal coordinates; use explicit associative planar-face
  connectors when the connection must follow source changes.
- Trim/extend currently handles straight-line endpoints against finite lines, full circles or
  directed arcs; circle/arc targets are not supported, and
  constrained/shared endpoints are rejected rather than losing constraints.
- Sweep supports connected nonbranching planar open line/arc paths, including
  schema-3 line-only sketches. New Sweep dialogs explicitly offer area-centroid
  placement at path start with roll and reversed traversal. Keep authored placement
  retains the original behavior without migrating older files. See
  [placement assumptions and limits](SWEEP_PLACEMENT.md). Circles, closed curved
  paths and arbitrary 3D splines are not admitted as paths. Loft accepts two sections or an explicitly ordered list of 2–16
  compatible single-wire sections without holes; see [limits](MULTI_SECTION_LOFT.md). Patterns fuse whole solids into one connected Part.
- Shell supports explicitly selected stable planar openings or a closed cavity.
  Use the checked opening list or Shift-click multiple faces; see
  [multiple Shell openings](MULTIPLE_SHELL_OPENINGS.md). Curved openings and
  missing/split/ambiguous identities are refused. Edge-pair blending requires
  stable semantic faces; generated/split/ambiguous faces need explicit repair.
  Ordinary Cut now retains a stable authored tool face only for one exact native
  Modified or unchanged face image. This supports selecting a hole wall and cap
  for a fillet/chamfer, including radius/height edits and reversed wall orientation.
  Generated-only history, multiple images/sources, aliased operands and patterned
  cuts do not acquire tool identity. Planar support uses the current cut normal,
  not the original tool normal. This is not arbitrary persistent topology naming.
- Assembly checks can be indeterminate when B-rep tolerance exceeds the requested
  query resolution. Listed poses do not establish continuous collision freedom.
- No structural/load/manufacturing certification or drawing-sheet output.
- Windows 1.15 has bounded installed background workflow and independent reopen
  evidence on Windows test host with Blender 5.2.2 LTS, approved normal-host execution and
  verified registered launcher ancestry. GUI/Undo and ordinary Explorer/Start-menu
  launcher paths are not qualified. See [Windows delivery](RELEASE_115_WINDOWS.md).
  Linux 1.16 has separate bounded installed checks; see [its receipt](RELEASE_116.md).
  Later Blender versions are untested.

## Integration exercises

Create and dimension a rounded bracket with mounting holes; change its dimensions
and confirm the hole/edge features rebuild. Create an enclosure using shell/cuts
and repeated connected features. Create a revolved part and a loft/swept part.
Place reused Parts in a moving assembly, edit the source, update the instances,
check the requested poses, save/reopen, and export exact solids.

These are representative exercises, not a reduction of the broader product goal.

Cut tool-face lineage is enabled for typed result v2/v3 replay only. Omitted
or explicit result v1 retains its historical snapshot-only tool-wall output.

## Development extrusion end conditions

Extrude Remove supports saved, directional Through All intent that recomputes
against the target solid on every rebuild, without manually matching its depth.
Its linked feature editor switches between Blind and Through All. See
[extrusion end conditions](EXTRUSION_END_CONDITIONS.md) for semantics and evidence.

Symmetric / Mid-plane is available for standalone and Add/Remove extrusions.
Its editable positive total depth is split equally around the sketch plane.

### Extrusion creation preview (development)

Extrude Sketch and Add/Remove Extrusion dialogs now request a debounced exact
sidecar replay while dimensions, direction, profile, target or end condition
change. Cyan boundary outlines show the proposed active solid over the unchanged
original display. Internal same-face tessellation diagonals are suppressed.
The preview supports Blind, Symmetric and Remove Through All with the same
candidate construction as Apply. It is not a shaded replacement or face-picking
source; no preview object, feature, topology identity or saved cache is created.

New input immediately clears the old preview. Failed, oversized or incomplete
previews say so rather than retaining a supposedly current outline. Cancel,
load/history lifecycle retirement, changed base/units/backend or a lost owner
cancel native work and remove overlays without changing existing objects.
Dialog Apply starts a fresh guarded asynchronous replay, validates exact current
intent and publishes through the existing atomic Part transaction. Escape during
Apply cancels. Scripted EXEC_DEFAULT calls retain the synchronous operator API.
Creation dialogs are covered; editing arbitrary solid features is not covered.
Native headless ownership/geometry smoke is separate from real GUI qualification.

Projected construction references now have a bounded history-level
[Replace Reference](PROJECTION_REFERENCE_REPAIR.md) dialog: same source and analytic
kind, retained dimensions/relations, explicit line endpoint flip, atomic whole-Part
validation. It is a selection/review dialog, not a broken-draft viewport picker.
Eligible unapplied upstream edits can retain multiple support/projection repairs
with proposal Undo and saved-intent Resume; the accepted Part changes only after
the complete candidate succeeds. This is not general failed-document recovery.


## Source-development Sketch Corner Fillet

Two selected ordinary lines sharing one authored corner now offer **Corner
Fillet…** with an editable radius, purple proposal and Apply/Cancel. The original
corner stays as a dimensionable intersection witness on the infinite supporting
lines; existing line/outer-point IDs, H/V and point dimensions are retained. One
atomic command adds the real directed arc, tangent endpoints, radius/tangency
relations and persistent versioned bounds. Native solve and result validation
reject tangent points beyond the original segments or a flipped/major branch,
including later radius edits, consumed replay and export. Failed trials preserve
accepted Part data and editable raw input.

Initial limits: no projected/coincident/shared corners, construction targets,
collinear corners or non-H/V relations on selected lines. Protected endpoint
retargeting, Reverse Arc and required-relation removal are refused. Adjacent
fillets sharing a protected outer endpoint are not supported yet. Whole-sketch
copies retain intent; no new sketch mirror/copy operation is introduced. Legacy
sketch bytes are unchanged, but older installations reject newly filleted
sketches and their journal command rather than silently dropping intent.

See [workflow, persistent contract and focused evidence](SKETCH_CORNER_FILLET.md).
This is unreleased source development, not a change to the frozen Linux 1.24
installer or a Windows/full historical-suite qualification.
