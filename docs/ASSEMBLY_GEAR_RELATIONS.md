# Directed gear coordinate relations

This development slice couples existing revolute joint angles. It is forward
kinematics over the existing rooted assembly tree, **not** physical gear tooth
contact, a dynamics engine, a closed-loop mate solver, or a manufacturing check.
No new native library is required. Exact Part replay, placement, current-pose
checks and listed-pose sampling use the existing isolated sidecar.

## Use in Blender

Create two or more revolute joints using the ordinary Assembly workflow. In
**Gear coordinate relations**, choose **Add Gear Relation**:

- Choose the named **Driver joint** and **Driven joint** (controlled) explicitly.
  Stable joint IDs remain visible in the panel and selector descriptions.
- Set **Signed ratio** (driven / driver motion). The equation is
  `driven angle = ratio × driver angle + phase`. Negative ratios reverse the
  sign of the coordinate motion; positive ratios retain it. These signs refer
  to each joint's mate-local +Z axis. They do not infer shaft orientation or teeth.
- **Keep current alignment** explicitly derives the phase from the captured
  saved pose. This is initially enabled for a new relation. The disabled offset
  field is not used while it is selected. Uncheck it to author **Phase (deg)**,
  the offset in degrees, explicitly. The dialog shows calculated phase and the driven angle
  before/after Apply. Editing an existing relation initially keeps its exact
  authored phase; changing another field never silently changes that phase.
- Apply freshly replays the whole assembly through the normal atomic transaction.
  Cancel, stale dialogs and invalid edits leave the accepted assembly intact.

The panel names both joints, signed ratio, coordinate direction and phase. A
controlled angle is read-only. Its joint Edit dialog still exposes its inclusive
limits, and identifies the ultimate independent driver to edit or sample. The
sampling chooser excludes driven angles. Driver edits update all followers,
including other branches of the assembly tree and chained relations. If any
follower exceeds a limit or the coordinate domain, the entire edit is rejected.
Limits do not clamp motion or silently adjust phase or ratio.

The relation's pencil opens Edit. **Remove** releases its driven joint at its
current derived coordinate, so neither it nor any remaining downstream chain
jumps. Component removal refuses branches touching a relation and names which
relations must be explicitly removed first. It does not silently delete an
unrelated relation or leave a controlled coordinate dangling.

### Viewport driver motion

**Preview Driver Motion** opens a motion-only viewport panel for an independent
revolute joint. A controlled joint instead offers **Preview Driver: name** and
identifies its angle as read-only. Type exact degrees and press Enter, or use
±1°. The selected driver is named with its child component. Limits are retained;
there is no automatic clamping, phase adjustment or follower override.

Each settled input requests a guarded asynchronous **whole-assembly replay**:
all coupled branches and chains use the authoritative evaluator and freshly
resolved Mate Frames, not a local subtree transform. Requests coalesce; pending,
invalid and failed inputs clear the prior ghost immediately. The accepted
assembly display remains untouched and the panel states whether the proposed
pose is pending, failed or ready. Preview is not contact or dynamics checking,
and never overwrites an accepted check report. Native failure does not retry by
itself: change the angle or reopen the preview after fixing the cause.

Apply is available only for the exact completed input. A fresh guarded replay
must reproduce that entire preview pose before the existing atomic transaction
publishes it; the resulting pose is **Unchecked**. Cancel/Esc discards all motion
intent, even during native work. Context, history, units, backend or accepted
assembly changes revoke the old preview. Opening a saved file does not restore
transient motion intent. Existing canonical Undo/Redo remains the model history.

Connector placement, reparenting and Mate by Faces remain unavailable for geared
assemblies in this slice. Use named **Mate Frame** edits for connectors; these
still perform whole-assembly exact replay. No free-drag connector solver,
physical gear dynamics or closed-loop mate solver is claimed.

Portable `.mcad-assembly.json`, embedded `.blend` storage, source-Part refresh,
and ordinary Blender Undo/Redo retain explicit relation records. Reopening or
history restoration does not revive old geometry/check authority: Replay and
Check remain explicit. Sampling changes neither saved angles nor accepted
instance display; every listed pose re-derives followers separately.

## Canonical contract

Assembly schema 1 gains optional `gear_relations`. It is omitted when there are
none, so ordinary existing assembly serialization/hashes remain unchanged. Older
readers reject this new field rather than silently discarding coupling. Every
record contains:

```json
{
  "id": "gear_1",
  "name": "Opposed 2:1",
  "driver_joint": "input_hinge",
  "driven_joint": "output_hinge",
  "ratio": -2.0,
  "offset_rad": 1.0471975511965976
}
```

Names default to the record ID when omitted. IDs use the existing stable ASCII
assembly-ID contract; names use the existing text bounds. Ratio magnitude is
inclusive 1e-6–1e6, nonzero and finite. Phase is finite and bounded to ±1e4 radians.
Booleans, expressions, unit strings, unknown fields and malformed arrays fail
closed. The relation array has the existing 63-record joint limit, and remains
within the shared assembly byte/nesting budgets.

Only the driven revolute joint has `coordinate: null`. It retains its ordinary
`limits` field. All other joints retain their existing coordinate schema. The
assembly rejects a numeric independent value on a controlled joint, or a null
coordinate without a relation. Thus a saved document never stores a second,
potentially inconsistent independent value for a follower.

References must resolve to existing revolute joints. Self-relations, multiple
incoming drivers and cycles are rejected. Directed chains and one driver with
multiple followers are supported, independent of spatial-tree branch order.
Relations evaluate in deterministic dependency order, preserving authored order
for ties. The effective map contains every joint coordinate, including derived
ones. Overrides may contain only independent coordinates (and existing fixed
zero placeholders); supplying a driven override is rejected even if it happens
to equal the derived value.

Sampling requires the full independent base map, retaining fixed zero
placeholders and every unrelated movable axis. It may sample only an independent
axis. Each sample re-derives the complete chain and checks all bounds. Invalid
samples retain their requested values and blocked diagnostics, with no effective
map or current transforms; valid listed poses are still reported. No clearance
claim is made between samples.

`structural_dof` is the ordinary tree joint-coordinate count minus the number
of driven joints. With relations, its method is
`rooted_tree_independent_coordinate_count`; without relations the existing
`rooted_tree_joint_count` value and method remain unchanged. This is a structural
count, not numerical Jacobian rank, loop-solving freedom, or physical mobility.
Limits do not reduce this structural count. The assembly revision binds both
relation semantics and the derived pose/check fingerprints.

The native-free Blender contract separately validates relation records,
references, dependency ordering, null ownership, derived values, limits, DoF and
exact rigid placements, without importing OCP or the core native kernel. It does
not trust response hashes as substitutes for coordinate/placement validation.

Rack-and-pinion, screw relations, multi-axis coupling, tooth generation/contact,
closed-loop solving and continuous collision verification remain future scope.

## Focused evidence

- `tests/unit/test_assembly_gears.py`: backward compatibility, relation DAGs,
  sign/phase, chains, limits, explicit alignment, no-jump removal, sample ownership,
  source preservation and separate native-free derivation.
- `tests/integration/test_assembly_gear_service.py`: real native replay and poses,
  forged receipt rejection, chained samples including blocked limits and source
  updates through the exact service.
- `tests/blender_assembly_gear_smoke.py`: native Blender 5.2.2 operators, cross-branch
  exact poses, native Undo/Redo, transactional rejection, source refresh, portable
  files and separate-process `.blend` reopen/edit. Run create/reopen with
  `MCAD_GEAR_MODE=create/reopen` and `--python-exit-code 1`; require both
  `ASSEMBLY_GEAR_CREATE_OK` and `ASSEMBLY_GEAR_REOPEN_OK` markers.

These checks do not establish manual GUI usability, installed-ZIP qualification,
platform portability, physical fit, gear loads, or professional certification.
