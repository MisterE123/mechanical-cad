# Roadmap: 2D design to mechanical assemblies

Historical planning record: checkpoint claims below describe their named early
versions, not the current source. Use [current capabilities and limits](INTEGRATED_MODELING.md)
for implemented behavior and the exact package's receipt for qualification.

## Current checkpoint

Version 0.5 adds explicit H/V and point anchors, relation inspection, solved-position
release and separately confirmed authored-position recovery to the line/circle
sketch, Part and rooted-tree assembly foundation. Direct radius/distance editing,
saveable open chains, separate annotation placement and New/Edit/Resume remain.
The exact installed preview passed its bounded native GUI and fresh-process gates;
see [the release receipt](audits/constraint_installed_050.md) and
[current scope and verification](VERIFICATION.md).
The earlier stage descriptions below retain their historical acceptance goals.
Fully featured sketches and a polished integrated CAD interface remain unfinished.
Next work should build on the existing generic entity/constraint model rather
than treating the rectangle shortcut as the whole sketch architecture.
Circular-arc contracts are the next bounded design study: sweep direction, minor
and major arcs, exact endpoint identities, radius editing, mixed open/closed
profiles and legacy compatibility must be reviewed before implementation. Arc
support is not present in 0.5. General Coincident creation and richer constraints
remain separately tracked; earlier user dimension feedback is not treated as a
delivery-priority instruction.


## Product goal

Build a powerful, understandable workflow from constrained 2D sketches through
editable mechanical parts to components, assemblies, mates, and mechanism motion.
Blend Blender conventions with CAD conventions where they improve the experience;
ease of use takes precedence over reusing an unsuitable Blender mechanism.

Current user priority is object creation and mechanical assembly verification
before manufacturing, with watertight intended geometry. Construction sketches
remain in scope; 2D drawing sheets and document output are out of scope for now.
Solid/manifold validity, dimensions and tolerance, interference, clearance,
remaining degrees of freedom and motion limits are verification targets.
Structural/load/stress validation is not implemented or implied.

Every tool, property, inferred intention and error needs an easy-to-read contextual
explanation in the application. External documentation alone is insufficient.
See [UX.md](UX.md) for the interaction contract and testable release gates.

This roadmap describes intended development stages, not dates or shipped claims.
Fully featured sketches remain a required product goal: lines/polylines, arcs,
circles, construction geometry, trim/extend, editable dimensions and geometric
constraints with understandable freedom/conflict feedback. The current rectangle
editor is an initial tool, not the sketch architecture's final shape. The current
priority is a strong application base: reliable drafts, history, recovery,
save/reopen and part/assembly ownership before widening every tool family.
The released Stage 1 foundation does not fulfil the complete product request.
Version 0.2 adds the first narrow interactive rectangle-to-part loop described
below; it does not complete Stage 2 or the assembly workflow. Mark a capability
implemented only after the actual add-on and its end-to-end workflow are verified.

## Stage 1 — Honest parametric foundation

### Purpose

Prove that design intent survives edit, rebuild, failure, and save/reopen. A small,
reliable vertical slice is more valuable than many one-shot modeling commands.

### Initial scope

- Independent, versioned CAD document with stable feature identities and an
  explicit dependency graph, rather than treating generated mesh vertices as CAD.
- Millimetre parameters and bounded arithmetic expressions.
- Rectangle/circle profiles with explicit coordinates, extrusion, and a cut
  between named base and tool solids.
- Blender panel/operators for blank/demo documents, parameters, explicit operands,
  history/status, active output, rebuild, JSON save/load, and `.blend` persistence.
- Kernel/sidecar diagnostics, last-good geometry, actionable error/status reporting,
  and an actual in-app Help operator with tooltips and contextual help topics.

### Exit evidence

Complete the plate/profile/extrude/cut/edit/save/reopen workflow in UX.md. Verify
correct physical scale, stable history/operands, Cancel, Undo/redo, invalid input,
repeated operations, missing sidecar, and failed-build recovery. Record which
behavior is passed, failed, or not run on the exact Blender runtime.

Validate that the committed kernel output is a valid, closed solid and that its
exported/display mesh meets stated manifold and tessellation checks. Report the
actual precision and tessellation tolerances, units, and verification method.
Do not infer watertightness or mechanical accuracy from a screenshot.

### Explicit limitations

No viewport sketch creation/snapping, no general geometric constraint solver, no
fully featured dimensional sketch UI, no live viewport feature preview unless
separately implemented, no robust arbitrary face/edge reference editing, and no
assemblies/mates/motion. Fixed numeric profile parameters are not a replacement
for these capabilities. A finite solid subtraction is not automatically a
through-all hole. A correct kernel result is not by itself an intuitive UI.

Target Blender 5.2.2 LTS. Existing 4.3.2 execution can provide fallback smoke-test
evidence, but cannot establish the target's compatibility or UI behavior.

### Next-version interaction refinement

After the Stage 1 baseline, build three actual **Sketch**, **Part**, and
**Assembly** workspace tabs sharing one canonical CAD document. Put contextual
tools on the left, sketching and dimensions in the viewport, and feature history
with a compact selected-feature inspector on the right. A larger sidebar or three
decorative tabs is not the requested engineering workflow. See
[NATIVE_CAD_WORKSPACE.md](NATIVE_CAD_WORKSPACE.md) for the supported API design.

Move common actions toward an icon-first contextual toolbar.
Prefer Google Material Symbols with original mechanical icons for CAD-specific
semantics. Keep meaningful hover descriptions, keyboard/tool-search names, and
optional learning labels. Dimensions, units, operand names, and failed/stale
warnings remain readable text. Follow the semantic map, accessibility checks,
offline asset manifest and license requirements in UX.md. This refinement must
not replace the live sketch/part/assembly work below or imply those tools exist.

The first interactive release gate is a real loop: New Sketch → viewport drawing
and numeric dimensions → Finish → Part extrusion → Edit Sketch → upstream
dimension change → rebuilt same part, including preview/Cancel, Undo/Redo, and
save/reopen. Start with dependable rectangle/circle parameters, then integrate
the real constraint solver. A temporary overlay probe does not satisfy this gate.
The Assembly tab may initially explain its unavailable tools, but its presence
does not count as components, mating, or verification.

### Version 0.2 evidence and next gap

Actual native Blender 5.2.2 source-loaded GUI testing has now passed viewport
rectangle drawing, explicit dimensions and fixed/free position with real solver
DoF, Finish to Part, +Z extrusion, original-sketch editing and downstream rebuild,
Undo/Redo, fresh-process `.blend` reopening/rebuild, invalid-input recovery and
draft cancellation on workspace changes. See UX.md for exact values and limits.
The free-position toggle was explicitly corrected and retested to preserve current
placement when only the anchor is released. In-app geometry checking reported one
valid solid and closed/oriented welded tessellation for the tested part.

This is a dependable rectangle subset, not a general constrained-sketch editor.
Next work still includes viewport circle/line authoring, selection and dragging,
constraint creation/inspection, visible snapping proposals, unit-aware input,
live feature previews, stronger palette readability, and richer part operations.
The later 0.3 slice adds bounded rooted-tree assembly authoring, explicit source
updates and exact sampled checks. It does not complete Stage 3. Package-install
evidence and broader theme/keymap/scaling usability checks remain separately reported.

## Stage 2 — Intuitive constrained sketches and mechanical parts

### Purpose

Deliver the first genuinely interactive sketch-to-part workflow for both engineers
and Blender users, with obvious recovery when intent or geometry is invalid.

### Build order

1. **Sketch workspace:** explicit plane/origin/normal; line/polyline, rectangle,
   circle/arc, construction geometry, trim/extend; selection, drag editing, and
   closed-region feedback. General entity IDs and typed draft payloads must not
   inherit the rectangle editor's four-point assumption.
2. **Snapping and intent:** visible origin/grid/endpoint/midpoint/centre targets,
   candidate cycling/disable, and disclosed constraint suggestions. No invisible
   permanent constraints and no invented confidence numbers.
3. **Dimensions and solver:** driving/reference dimensions, named expressions,
   unit-aware input, initially a narrow dependable constraint set, then tangent,
   equal, symmetry and related constraints. Explain under/fully/overconstrained
   states; show remaining freedom and conflicting relations with corrective actions.
   The finished interface must support traditional geometry-linked dimensions:
   selection and placement, direct compact value/formula editing, Enter/Esc
   acceptance, draggable annotations and clear driving/reference roles. This is
   a product requirement, not a user-directed change in delivery priority. Familiar
   CAD conventions should be implemented independently; no proprietary code is used.
4. **Part features:** robust region selection and extrude new/add/cut first; then
   through-all/mid-plane/up-to-reference, revolve, hole, fillet/chamfer, mirror and
   pattern. Add further features only with editable history, preview/cancel,
   dependency semantics, failure messages and regression examples.
5. **History editing:** edit upstream sketches in context, suppress/restore,
   inspect dependents, safe rollback/reorder where valid, and repair missing
   references instead of substituting plausible-looking geometry.
6. **Interoperability:** dependable physical-unit import/export, explicit CAD-to-mesh
   copies, and documented boundaries for Blender modifiers/transforms. Preserve the
   parametric original when handing a mesh to Blender-native tools.

### Exit evidence

- A user draws and constrains a plate, creates its holes and finishing features,
  edits an early dimension, and obtains a correct rebuilt part.
- The user can see and override a mistaken inferred relation, recover from an
  overconstraint or invalid feature, and save/reopen/edit without losing intent.
- Both mouse-driven and numeric workflows are discoverable from the UI. Default
  and Industry Compatible Blender keymaps retain usable navigation and controls.
- A small usability study includes practicing mechanical CAD users and Blender
  users; unresolved confusion is recorded rather than hidden behind a feature count.
- Every operation and error has contextual help; no essential step requires a
  terminal, Python console, or an external tutorial.

## Stage 3 — Components, assemblies and mechanism motion

### Purpose

Complete the requested 2D-to-mechanical-3D workflow with reusable parts and
understandable assembly relationships, while making assembly repair trustworthy.

### Build order

1. **Components and instances:** promote a part to a component, place linked
   instances, make an independent copy deliberately, group subassemblies, and
   distinguish design coordinates from assembly placement. Give each instance a
   stable identity and an inspectable source/revision.
2. **Placement and mates:** grounding, rigid relationships, revolute and slider
   joints first; then distance/angle/planar/coaxial relations as the solver permits.
   Select mate origins/axes/faces with clear two-component roles and previews.
3. **Assembly solver and diagnostics:** remaining degrees of freedom, redundant
   relations, limits, conflicts and dependency inspection. Do not substitute Blender
   parenting or unconstrained animation for a solved CAD assembly relationship.
4. **Motion:** drag a permitted freedom, drive a joint through a range, preview
   kinematics, and identify unreachable/conflicting states. State clearly when
   contact, collision, force, inertia or real-world physics are not modeled.
5. **Change and repair:** edit a part in context, propagate to all linked instances,
   invalidate affected mates visibly, and repair changed references with highlighted
   old/new candidates. Never silently choose a different mating face.
6. **Mechanical verification and handoff:** interference checks, minimum clearance
   measurements with the checked component pairs and tolerances, component
   quantities, placements, supported assembly interchange, and watertight part
   exports. Report the sampled motion range for motion-dependent clearance checks;
   static or sampled clearance is not proof of collision-free continuous motion.
   Drawing sheets/document output are out of scope for now. Do not imply structural
   safety, load capacity, certification, or manufacturing readiness from a visually
   plausible, watertight model.

### Exit evidence

- A small mechanism uses a grounded component, a revolute component, and a slider;
  remaining freedom and joint limits are clear and motion follows the mate model.
- Inserting the same part twice, editing it, saving/reopening, and updating the
  assembly preserves instance identity and intended relationships.
- A conflicting mate and a changed mating reference can be diagnosed and repaired
  using in-app explanations, without silently moving unrelated components.
- Users can tell whether the current result is solved, underconstrained, stale,
  failed, or merely a preview. Cancel restores the previous solved placement.
- Model/history, units, exports and assembly instances stay synchronized across
  the full workflow. Automated regression evidence accompanies interactive QA.
- Known interfering, touching, separated, and near-tolerance component pairs
  return the right status; clearance results identify the tested pair and units.
  Motion checks state joint limits, sampled interval/step and any untested range.
- All part exports pass the declared solid/manifold checks within explicit
  tessellation tolerances. Any open or invalid geometry blocks a watertight-output
  claim. Structural/load analysis remains separately unimplemented.

## Cross-stage non-negotiables

- **Truthful status:** feature-level errors and stale results are visible; an old
  good mesh is never evidence that current parameters rebuilt successfully.
- **Safe correction:** changes are transactional, Cancel works, recovery preserves
  the last-good design, and repeated clicks cannot corrupt history.
- **Visible intent:** suggestions explain why they were made and are reversible;
  explicit user choices always win.
- **Units:** physical meaning is consistent between design data, Blender, and
  export. Unsupported syntax is rejected clearly rather than guessed.
- **In-app teaching:** short tooltips plus contextual popups explain meaning,
  required input, consequences, recovery and limitations at the point of use.
- **Blender fit:** reuse navigation, selection, gizmos, visualization and animation
  thoughtfully. Test changed keymaps and do not force shortcuts as the only path.
- **Evidence over labels:** track implementation, automated tests, UI tests and
  version compatibility separately. “Foundation” is not “full MVP.”
