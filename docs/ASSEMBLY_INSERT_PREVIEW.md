# Preview before inserting an Assembly component

Post-1.29 source development; frozen installers remain unchanged.

Reuse a Part and Add Working Part retain the existing named-frame insertion
choices. Confirming the dialog now opens **Preview**, not an immediate insertion.
Gold wire geometry shows the complete candidate Assembly, including the new
child and joint. The panel identifies the source revision, child, parent and joint.
**Insert component** explicitly applies the reviewed candidate; Cancel/Esc leaves
no new source, definition, instance or joint. This is placement/geometry review,
not contact or dynamics verification and not uninserted-child face picking.

A detached typed draft uses the existing capture-definition and insert-instance
operations once, retaining stable generated IDs. A divergent already captured
Part still requires Update All Instances first. A private, one-shot handoff binds
the accepted Assembly, raw working Part, scene, window, view layer and exact
invoking viewport. Direct invocation without that handoff refuses. Cancellation,
launch failure and lifecycle changes revoke the handoff and transient owner.
The outer dialog returns CANCELLED; only successful child Apply owns Undo.
Explicit programmatic execute retains the existing guarded insertion behavior.

The insertion owner reuses the nonpublishing full-Assembly review machinery.
Apply freshly replays the same candidate and compares the complete validated
six-result-field plus base-pose fingerprint before staging display. Existing
transport, context, source, backend, unit and currentness guards remain mandatory.
No saved schema, protocol, tolerance comparison or publication-on-poll is added.

## Bounded verification

- Combined insertion/source-preview/motion focused tests: **190 passed**; Ruff clean.
- Blender 5.2.2 native: **64 create checks**, covering reused and newly captured
  sources, stable IDs, Cancel/no orphan, single atomic Apply, exact geometry,
  unchanged existing slider coordinates, divergent-source refusal and the
  existing source-update owner after insertion.
- Independent-process native saved-model reopen: **11 checks**, exact canonical
  graph, five instances, two sources/definitions, four joints, exact volume,
  no transient owner and explicit fresh replay. OCP stays outside Blender.
- An initial optional background operator-invoke probe was rejected by Blender
  before application invoke; its log is retained. Corrected no-handoff testing
  calls the actual method with a report-only port, not a claim of GUI invocation.
- Actual GUI Preview and Cancel preserve exact accepted Assembly, working Part
  and accepted report, with no completed operator-history entry. Fresh GUI Apply
  produced current four-instance geometry with one child-modal history entry; Undo
  restored the exact three-instance graph and Redo restored the exact applied
  graph and working Part. History correctly marks display dirty pending replay.
  Blender emitted one mesh ID-user decrement diagnostic during history, without
  crashing; retained evidence does not establish allocator-level correctness.
  Explicit Rebuild after Redo restored current geometry; the four-instance
  GUI model was saved with exact canonical data (SHA-256
  `e5bc471946e3eef77e32cf35a5f20e9bedc3b3adfd05c88fc4c825692d4d82a9`).
  Independent reopening of that exact GUI file passed **17 checks**: exact graph
  and working Part, four identical poses, new child at [30, 0, 0] mm, source width
  20 and volume 2000, unchanged sliders and saved bytes; no transient owner.
- Observed asynchronous GUI preview phases took 16.96 and 7.98 seconds, excluding
  synchronous admission/canonicalization. QA timeout was 180 seconds; product
  defaults remain unchanged. These host measurements are not release guarantees.

No full aggregate, Windows or exact-installed package qualification was rerun.
Existing broader test and native allocator limits remain open. This independent
fixed-joint insertion does not exercise the separately paused slider GUI Apply.
