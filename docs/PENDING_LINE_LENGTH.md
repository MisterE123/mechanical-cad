# Driving length during Line placement

Source development adds a bounded exact-length route without accepting rough
geometry first. Choose Line, click the first point, move to set direction, then
press **Tab**. The **Driving length** field accepts a positive number in mm or a
supported explicit unit literal (for example `20`, `2 cm`, `0.5 in`). Enter
creates the line and an editable distance dimension together, after native
validation. One sketch Undo removes the complete operation.

Hold Shift while pressing Tab to capture the currently shown Horizontal or
Vertical intent. Its name appears in the field, and the real H/V constraint is
retained. Shift used while editing text cannot change this captured intent.
A suspended Driving-length field retains that explicitly captured H/V as data,
not as a held-key state. This differs from an ordinary unfinished pointer Line:
a recovered pointer proposal requires Shift to be held anew for its next click.
Without H/V, direction is placement intent only, not a lasting angle constraint.
No hidden Fixed constraint anchors the start. New endpoints are seeded at the
requested distance; acceptance verifies the captured placement was retained.

Escape in the field cancels only its length and retains the original unfinished
Line. Choose Continue to return to pointer placement. Outside/right click
suspends exact raw input; Reopen Length restores editing with a fresh lease.
Cancel Proposal removes both the unfinished Line and its raw length input.
Repeated Enter and stale native completions cannot add the line twice.

Only finite positive literal lengths from 1e-6 to 1e6 mm are supported here.
Formulas are rejected with guidance to create the line first, then use the
existing Dimension editor. That editor's formula and downstream-replay behavior
is unchanged. Reusing an existing endpoint never silently relocates it to fit a
length; incompatible reuse is refused. The bounded acceptance also refuses
changes to any pre-existing solved point (absolute comparison tolerance 1e-7 mm).

## Transaction and recovery contract

`pending_length` is an optional strict UI extension with its own schema version
1. It stores original proposal, captured anchor/endpoint identity and positions,
unit direction, optional H/V, raw text and raw revision. Old inactive UI1/UI2
snapshots are unchanged. Older strict readers reject an active extension instead
of dropping its intent. A restored draft has no input lease, held modifier,
queued acceptance or solver evidence. Reopen is explicit. Existing points are
freshly solved again; saved positions are only intent, never native authority.

A distinct `add_length_line` journal2/3 command creates all new endpoint IDs,
one line, a real editable distance driver and optional H/V in one entry. Older
installers cannot resume journals containing this opcode, just as they cannot
resume `add_axis_line`; no frozen installer was updated.

The owner binds session/window/scene/workspace/area, exact base and saved slot,
backend selection, unit scale, source proposal/raw snapshot and fresh input token.
It stages an immutable detached candidate. A fresh guarded baseline solve (when
there are existing points) and candidate solve must retain all existing points
and new seeded placement before the single checkpoint CAS. Final postcheck
revalidates both evidence chains and owner context. Cancellation during child
cleanup permits only exact field/proposal removal with the entire command
checkpoint unchanged, using the same slot CAS and rollback.

This is structural **draft** acceptance, not Part publication. Like ordinary
Line, it permits an intermediate open segment in a consumed sketch. Finish still
requires full native downstream replay and cannot publish an invalid Part.
Canonical parameters, unrelated constraints and existing identities are unchanged.

## Bounded evidence (2026-10-24)

The new pure command/raw/owner-guard tests pass (89 tests). The related focused
suite passes 338 tests and 19,597 text-input subtests; this is not the full inherited
suite. Scoped Ruff and whitespace checks pass.

Native Blender 5.2.2 source-loaded owner checks pass with
`LINE_LENGTH_OWNER_SMOKE_OK` and `LINE_LENGTH_CONSUMED_SMOKE_OK`: first-line start
placement, unit input, reused endpoint plus H/V, atomic Undo/Redo, formula rejection,
raw Suspend/Resume, cancellation during cleanup, stale input token, and consumed
intermediate geometry whose invalid final Part is refused. Canonical Part text
and unrelated scene objects remain unchanged in the fixtures.

A separate two-process `.blend` check passes `LINE_LENGTH_PERSIST_SAVE_OK` and
`LINE_LENGTH_PERSIST_RESUME_OK`. Saving while a native length check was pending
preserved exact raw text and reused point identity; a fresh process restored no
controller/token, gesture capture, queued job/attempt, or native evidence. Explicit
Reopen followed by fresh native validation accepted the restored operation once.

A bounded cloud-Linux GUI session exercised real first-point → Tab → `2 cm` →
Enter, visible 20 mm driving annotation, atomic Ctrl-Z/redo, Shift+Tab capture and
retention of Horizontal, formula rejection, Esc retaining the original Line,
right-click raw suspension and explicit Reopen → Enter. The disposable fixture
exited cleanly. A second fresh GUI launch checked the final concise guidance and
retained-axis field label. These are source-loaded observations, not packaged or
Windows qualification, exhaustive input/recovery testing, or resolution of the
separate intermittent native allocator crash. No speculative allocator fix is
included.

The pending-length sidebar is contextual: while its text field is active it shows
only the unfinished-Line state and applicable Back to Line / Discard Line actions.
The field itself supplies raw text, axis and keyboard guidance. Suspended input
shows retained raw text/axis and Reopen/Cancel actions. Tooltips distinguish
canceling only length entry from discarding the entire unfinished Line. Solver,
profile, stale/error and Part status remain visible; irrelevant disabled relation
controls are omitted until the pending length is resolved.
