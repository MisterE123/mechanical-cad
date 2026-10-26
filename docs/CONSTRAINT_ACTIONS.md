# Owner-bound constraint actions

This is a bounded, transient seam for the existing `GeneralSession`. It adds no
canonical schema, draft codec, lifecycle registry, native transport or solver.
Selection, rendering, dialog ownership and relation-target editing stay outside
`constraint_actions.py`.

## Adapter contract

1. `prepare(owner, action)` returns a frozen `ConstraintActionIntent`, or raises
   `DraftError` for an invalid/unavailable action. Supported names are
   `horizontal`, `vertical`, `fix_here`, `fix_origin`, `remove_relation`, and
   `recover_remove_relation`. Coincident is deliberately unsupported.
2. Inspect `action`, `state`, `refs`, `relation_ids`, `target`,
   `requires_confirmation`, and `disclosure`. State is `eligible` or `existing`.
   Preparation is read-only and starts no native work.
3. If confirmation is required, show the disclosure and retain the **original**
   Python intent across the dialog. Cancel by dropping it. Never prepare a fresh
   intent after the user approves an older disclosure.
4. Call `apply(owner, context, intent, confirmed=False)`. Only the explicit boolean
   `True` fulfills required confirmation. Application compares a fresh preparation
   with the original complete immutable intent before calling `owner.execute`.
5. `ConstraintActionResult` has `changed`, `revision`, `relation_ids`, and the
   convenience property `constraint_id` (first exact ID, or `None`). Existing
   relations return all exact IDs with `changed=False`; selection is a separate
   UI operation. No checkpoint, command, evidence replacement or native request
   is performed for an existing relation.

The existing owner remains the only mutation/checkpoint/async/publication path.
Accepted actions attempt its normal Check and remain local until its normal
Finish succeeds. A command and its saved draft checkpoint can succeed even when
verification cannot start. In that case the operator returns authored success,
shows a persistent unverified error, retains the Undoable command, and withholds
Finish. The user can correct backend settings and explicitly Check or Undo;
there is no automatic retry. Failures before command/checkpoint acceptance leave
all authored state unchanged and return cancellation. Applying a stale intent raises without mutating the owner. The
intent is not a saved capability or a command that can be serialized and replayed.

## Exact bindings and authority

Intents bind the exact session/owner, runtime scene/window/view-layer/workspace/
viewport, draft and command objects, raw source digest, complete serialized draft
digest, command/UI revisions, input token, normalized ordered stable-ID selection,
saved slot and solve-evidence identity/digest. The bounded immutable saved-slot
string is retained with its object identity: an input Begin/Cancel checkpoint
cannot revive an earlier intent even if it returns to identical bytes and began
without a current solution. Selection A-B-A advances the existing UI revision.
These are transient comparisons, not a second persistent revision system.

Preparation and application require the original live active owner, idle native
lease/replay, no proposal, no retained input and no annotation gesture. External
source/slot changes, pending checks, replaced/retired owners and changed selection
fail closed. Application also checks the invoking context's original viewport.

Fix here strictly validates the current complete request and response against
the owner's current command candidate, and reads the selected solved point's
exact coordinates. It never reads `owner.geometry()`, a retained outline, or a
geometry cache as authority. Ordinary relation release requires the same current
strict evidence; `owner.execute(DeleteBatch(...))` revalidates it again into its
detached candidate and records the current solved release seeds.

Fix at origin explicitly targets sketch-plane `(0, 0)` mm and discloses potential
movement. Any existing fixed relation is inspectable regardless of its target;
neither fix action retargets it or creates another relation. Likewise existing
H/V actions return exact existing IDs, preserving solve authority and allocation
state without native work.

Recovery is separately named and explicitly confirmed. It requires no current
successful solution, no retained solve response, and one exact constraint-only
preview with no geometry cascade. It delegates `RecoverRemoveRelation` using only
the exact authored-position policy described in
[CONSTRAINT_RECOVERY_CONTRACT.md](CONSTRAINT_RECOVERY_CONTRACT.md). Ordinary Remove
never falls back to recovery. Failure diagnostics do not select a relation or
provide placement/DoF authority, and their presence is not required for recovery.

## Verification

`tests/blender_constraint_actions_smoke.py` runs under actual native Blender 5.2.2
with the configured CPython sidecar and `--python-exit-code 1`. It checks the
four-line proposal loop, explicit H/V, origin and dimension actions, real zero DoF,
duplicate no-ops, strict FixHere/release placement, confirmation/stale/busy/input
guards, conflicting native solves, explicit recovery and local history, restored
inconsistent drafts without diagnostics, existing Finish, and an analytic-volume
extrusion. A separate far-origin circle exercises FixHere/release, explicit origin
movement, exact radius-expression retention and analytic disk extrusion. This is
headless transaction/solver evidence; it does not establish GUI usability.
