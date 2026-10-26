# Driving diameter during Circle placement

Source development adds a direct literal diameter while the Circle is unfinished:
choose Circle, click its center, then **Tab**. Enter a positive numeric diameter
in mm or a supported unit literal, such as `20`, `2 cm`, or `0.5 in`.
**Enter** creates the circle and a real editable radius driver in one sketch
Undo step, only after fresh native validation. The displayed annotation uses
**⌀** and twice the radius; the canonical constraint remains radius = diameter / 2.

The initial field accepts only literals from 0.000002 to 1,000,000 mm diameter
(the minimum reflects the canonical 0.000001 mm radius). No formulas, named
parameters, hidden Fixed constraints or inferred persistent constraints are added.
Use Dimension after creation for formulas. Opening a diameter-displayed driver
now uses the [explicit Diameter dialog](DIAMETER_EDITING.md), so its number and
formulas describe the full diameter. Already-retained raw radius edits keep their
original meaning and the heading **Driving radius · diameter / 2**; ordinary radius
annotations are unchanged. Ordinary pointer
Circle creation and the existing Dimension acceptance/replay gates are unchanged.

Escape in the field cancels only diameter input and keeps the original unfinished
Circle. Continue resumes pointer radius placement. Right/outside click suspends
exact raw text; **Reopen Diameter** starts a fresh field. **Discard Circle** removes
both proposal and its raw diameter. Repeated Enter or stale callbacks cannot add
a circle twice. New centers must retain their captured position; reused centers
must not move. All prior solved points and circle sizes must remain unchanged
(absolute comparison tolerance 1e-7 mm), otherwise acceptance is refused.

## Ownership, journal and recovery

`pending_diameter` is a separate optional UI extension, schema version 1. It stores
the exact original Circle proposal, captured center position, raw text and raw
revision. The strict codec binds it to the Circle tool/proposal and rejects mixed
pending fields, unexpected fields and malformed data. Capture, input leases,
queued acceptance, native evidence and execution authority are never serialized.
A restored draft remains suspended; explicit Reopen and fresh validation are
required. Optional local recovery validates this data through the same strict
codec; it does not enable recovery preferences or change recovery storage policy.

`add_diameter_circle` creates the new center (if any), circle and radius driver
in a single journal2/3 entry with strict shape, identity, value and allocation
validation. Radius annotations may now explicitly request diameter display;
their kind and references still bind to the original canonical radius driver.
Older strict installers cannot Resume drafts with the new pending extension,
command opcode or diameter-display metadata. No frozen installer is modified.
Old inactive snapshots and ordinary radius annotations are unchanged.

The owner uses separate Circle-diameter input and native completion phases,
immutable source/candidate snapshots, exact raw revision, current owner/session,
window/scene/workspace/area, saved slot, backend, unit scale and base checks.
A fresh baseline solve (when existing points exist) and candidate solve must
retain the captured placement and every prior solved point/circle radius.
Evidence and owner context are rechecked before the single checkpoint CAS.
Cancel during child cleanup can only remove the exact field/proposal while
preserving the complete command checkpoint; it cannot accept geometry.

This is structural draft acceptance, not canonical Part publication. The canonical
Part remains unchanged until Finish/full downstream replay succeeds. No profile,
Extrude or consumed-driver-edit gate is relaxed. An intermediate disjoint circle
may be valid draft geometry even when the final Part cannot be built.

## Verification scope

The combined targeted pure command, codec, owner-guard, annotation, existing
Line-length, general-authoring and recovery suite passes 603 tests. Scoped Ruff
and whitespace checks pass. Six standalone native solver/kernel tests pass:
literal/unit diameter, retained
new/reused center, preservation of prior free/driven circle sizes, exact cylinder
volume, existing consumed-driver formula/replay gating and final refusal of a
disjoint circle in a consumed sketch. These are not Blender owner checks.
Native Blender 5.2.2 source-loaded checks pass `CIRCLE_DIAMETER_OWNER_SMOKE_OK`
and `CIRCLE_DIAMETER_CONSUMED_SMOKE_OK`: first center placement, unit input,
editable radius driver, one-step Undo/Redo with diameter annotation, reused
center, prior free/driven circle sizes, formula refusal, raw Suspend/Reopen,
cancel during cleanup, stale token refusal and disjoint consumed-sketch geometry
whose final Part is refused. Canonical Part and unrelated scene objects remain
unchanged in these fixtures.

A two-process `.blend` check passes `CIRCLE_DIAMETER_PERSIST_SAVE_OK` and
`CIRCLE_DIAMETER_PERSIST_RESUME_OK`. Saving during a pending native diameter check
retains exact raw text and reused center identity. A fresh process restores no
controller, token, proposal capture, queued job, attempt or native evidence.
Explicit Reopen and fresh native validation accept the restored operation once.
This is ordinary draft persistence, not qualification of the optional recovery
chooser. The latter was not enabled or exercised on this branch.

Bounded cloud-Linux GUI checks exercised real Circle center → Tab → `2 cm` →
Enter, visible ⌀20 mm with canonical radius10, atomic Ctrl-Z/Redo, creation formula
refusal, Esc retaining the original proposal, Continue followed by ordinary free
Circle placement, right-click exact raw suspension and explicit Reopen → Enter.
A second fresh GUI launch checked the final concise literal/formula guidance,
which fits the sidebar without hiding the route to Dimension. Both disposable
GUI fixtures exited cleanly. Screenshots and logs are retained with the local
engineering evidence, not shipped in the source tree.

These are source-loaded bounded observations, not a full inherited-suite run,
packaged-install qualification, Windows evidence, manufacturing certification or
a fix for the unresolved native allocator crash. Diameter-displayed drivers now
open the explicit Diameter dialog; existing radius annotations and retained raw
edits keep canonical radius semantics. See [Diameter editing](DIAMETER_EDITING.md).
