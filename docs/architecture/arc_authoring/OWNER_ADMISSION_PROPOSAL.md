# Proposal: live bounded-sector evidence and atomic Blender ownership

Status: **parent-approved bounded design subject to independent consistency review; no implementation or qualification claim**.
Date: 2026-10-17 UTC.
Inspected source: `cad_arc_core` at `ce5b50bb011b3949a6599c7cbc28d31024805e0a` (clean before inspection).
This deliverable is outside the source checkout. This task read source and documentation only; it changed no production code, tests, release files or kernel policy and launched no native CAD/Blender process.

## 1. Decision and first usable outcome

Activate result 3 in the existing guarded General/Part owner path for **sketch solve and Part replay only**. Do not expose the dormant data service as a second owner or promote its returned dictionaries. Preserve every existing v1/v2 tooling contract and v2 production path. The live cutover must be atomic across request creation, retained evidence, pending completion, General commands, display, Part publication and current readers.

The first supported user outcome is:

1. In an eligible XY Part, explicitly author a center/start/end arc with a persistent direction and three persistent point IDs.
2. Add exactly two radial lines using those same point IDs, with no hidden coincidence relations or duplicate solver handles.
3. Apply the existing explicit fixed-center, H/V-radial and radius-driver controls. A genuine current solve must report 0 DoF for the qualified quarter-sector control.
4. Finish the supported sector through a fresh guarded replay, showing its profile. Add its sole extrusion and replay it through the same Part publication seam.
5. Reopen the same sketch, edit the existing radius driver, solve the exact trial, replay the existing dependent extrusion, accept the driver once, and Finish with another fresh replay. Preserve feature/entity/relation IDs and untouched authored seeds/expressions. A parameter-based radius variation must likewise retain the radius relation expression when that is the chosen authored intent.
6. Save ordinary `.mcad.json` and `.blend` data; reopen as unverified authored data and run fresh work to regain current evidence.

The bounded native geometry remains the qualified one-arc/two-radial sector, at radii and extrusion heights 1–1000 mm, with the existing exact incidence/membership checks, ray-dot limit, signed-permutation/zero-world-origin placement restriction and native representation guard. The viewport slice is XY; native support for additional signed-permutation frames does not create arbitrary-plane authoring permission.

### Product tradeoff: incomplete arcs

An isolated arc, incomplete radial boundary or other unsupported arc-bearing profile can be checked and inspected when the solve contract supports it, but **cannot use canonical Finish**. It remains a suspendable, resumable, editable draft. A successful solve with `profile_check.ready: false` is visibly a successful solve with an unsupported profile, not a solver failure and not an accepted open-arc Part.

For an arc-bearing schema-3 candidate, Finish eligibility requires current successful solve evidence and `profile_check.ready: true`; Finish still launches and validates a distinct full replay. This pure readiness result does not promise native construction. No solve-only canonical-save route is introduced. Legacy supported line-only open-chain Finish stays unchanged, including genuine no-profile/no-solid output. Arc-empty schema 3 retains the service's existing line/circle behavior and remains schema/result 3; it is never silently downgraded.

### Product tradeoff: downstream operations

The first workflow has a current profile/solid display and editable persistence, but **no schema-3 Check Geometry, STEP/STL export, Assembly capture/update/replay/check/sample, or guarded canonical snapshot**. These need additional separately reviewed contracts. Disable them with an explanation and enforce the same rejection on direct invocation before launch or external mutation. Do not label a successful Part replay as a geometry-check/export certification.

This is the recommended bounded next milestone. If the parent requires export in the first usable arc release, approval must instead expand the work to a separately designed result-3 geometry/export contract and its complete owner/export gates; the current proposal must not be presented as satisfying that release requirement. It is a bounded authoring preview, not general arc CAD, mixed-profile CAD or an export-ready arc release.

## 2. Source facts that constrain this change

The architectural baseline is `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, ADR 0008, the capability proposal and publication inventory, `docs/ARC_SECTOR_DATA_SERVICE.md` and `docs/NEXT_SKETCH_ARCS.md`. The latter is a broader staged roadmap; its open arcs, segment/chord profiles, multiple arcs, Assembly and exports are not all qualified or included here.

Current implementation seams, verified in source:

- `guarded_evidence._validate` explicitly rejects non-snapshot result versions other than 2. Its immutable G/O/response/projection, live selection and separate `EvidencePublication` are the correct extension point.
- `result_v3.py`, `sketch_contracts_v3.py`, `part_contracts_v3.py` and `sector_topology_v3.py` already strictly validate detached data-only result-3 solve/replay. They do not grant current authority.
- `service_v3.DataOnlyJob` deliberately returns copied data, has no owner/publication token, and is not imported by live owners. Keep that property.
- The server already advertises the exact arc/solve3/Part3 capabilities for result-3 solve/replay from the actual imported modules. It does not advertise snapshot3, geometry3 or Assembly3 support.
- `document_state._result_version`, `part_publication.prepare`, `sketch_pending._request_snapshot`, `GeneralSketchDraft.solve_request/replay_request`, and the General validation/display/diagnostic consumers are v2-only. Merely widening `GuardedEvidence` would leave an incomplete and unsafe cutover.
- `result_v3._graph` permits an arc-containing replay graph with exactly one arc-bearing sketch and at most its one extrusion. Once an arc is present, unrelated features, additional extrusions and cuts are rejected. Preflight first-arc final acceptance against this same strict rule before checkpointing migration into an incompatible Part. An authoring envelope/tool promotion does not itself select result 3.
- `document_state._publish_candidate_locked` is the shared canonical/RNA/display rollback seam; `_apply_result` is the sole Part write sink. Preserve them rather than adding an arc publisher.
- The General draft retains a one- or two-element solve/downstream evidence chain and transfers the entire chain to exact same-owner clones. Preserve that logic for version 3.
- `MCAD_OT_save` already atomically saves ordinary canonical JSON without calling `canonical_snapshot`. `.blend` stores authored state and historical caches. These saves do not need a new snapshot capability.
- `geometry_operations.run_geometry_action` currently uses the shared Part version selector and clears current display state before transport. A new action-specific schema-3 rejection must happen before those mutations.

No server capability expansion, solver changes, OCCT changes, native projection changes, tau/modulo normalization or tolerance widening is required or authorized by this proposal.

## 3. Per-version admission, without fallback

Introduce one small native-free operation policy/dispatch seam, proposed file `blender_addon/mechanical_cad_blender/operation_contracts.py`. It is a higher-level dispatcher over existing strict validators, not another serializer or a copied v2 validator. It must not import owners, Blender, core or native modules. Keep the old validator entry points and their legacy behavior intact.

The seam has two distinct jobs:

1. Select the **production** result contract from the complete bounded exact candidate and intended action/owner role.
2. Dispatch an already explicit operation/response to exactly one strict version validator. Never try one validator and fall back to another after failure.

Selection scans all embedded sketches in the whole Part, and every source for Assembly preflight. It uses exact integer schema tags, never truthiness, the active feature alone, nonempty `arcs`, tool selection, UI envelope version, a saved report, backend version string or available capability cache.

| Input and role | Production request | Admission and owner result |
|---|---|---|
| Part 1/2, all embedded sketches 1/2, any existing supported potentially-solving action | Explicit result 2 | Existing strict v2 validators and guarded production behavior |
| Same data, legacy unguarded tooling | Existing omitted/result-1/result-2 behavior | Exact historical behavior; cannot acquire production authority |
| Part 2 with any embedded sketch 3, General solve | Explicit result 3 | `result_v3.validate_solve_response`; current solve authority only |
| Part 2 with any embedded sketch 3, Part/General replay | Explicit result 3 | `result_v3.validate_response`; bounded graph/profile policy and ordinary current owner checks |
| Schema-3 sketch with empty arcs | Explicit result 3 | Retains genuine schema; line/circle semantics from existing v3 validators |
| Envelope/journal/UI promoted for an arc proposal, but candidate has only sketch 1/2 (including Undo before first AddArc) | Explicit result 2 | Authoring capability does not upgrade the model or backend result contract |
| Rectangle owner | Explicit result 2 only | Cannot accept v3, including a genuine legacy Rectangle solved/replayed through v3 |
| Schema-3 canonical snapshot | No live launch | Explicit unsupported action; do not request/advertise `mcad.snapshot-sketch3/1` as implemented |
| Schema-3 geometry checks or STEP/STL export | No live launch | Explicit unsupported action; no export tempfile, file write, current-state invalidation or fallback |
| Assembly containing any schema-3 source, or capture/update from a schema-3 working Part | No live launch/publication | Explicit unsupported action; old accepted Assembly/source/display/report remains unchanged |
| Unknown nested schema or result version, bool/float/string version, explicit version contradicting exact source/owner policy | None | Fail closed before launch/mutation; retained user bytes available for recovery |

The server/client minimum set for each supported result-3 launch remains sorted and exact:

- Solve: `mcad.backend-contract/1`, `mcad.sketch-arcs/1`, `mcad.solve-result/3`, `mcad.solver-dof-cycle-guard/1`.
- Replay: `mcad.backend-contract/1`, `mcad.part-result/3`, `mcad.sketch-arcs/1`, `mcad.solver-dof-cycle-guard/1`.

A backend with extra unrequested capabilities is compatible; a missing requirement, wrong identity, missing receipt or malformed inner result is not. No cached handshake, retry with result 2/1, stripping arcs, curve-to-line approximation, dropped contract or alternate backend is allowed.

Low-level explicit v3 validation may continue to accept legitimate legacy-shaped v3 solve/replay data as the data-service contract already does. This does not oblige production owners to select v3 for legacy documents. Use the conservative concrete API choice: `GuardedEvidence.revalidate` and `EvidencePublication.consume` default `expected_result_version` to **2**. Only schema3-capable owners explicitly opt into 3, supplying the version derived from the exact bound candidate/operation. The method compares that exact integer to immutable O before inner validation. An overlooked old consumer therefore continues to reject3 after `_validate` is widened. Rectangle and v2-only downstream consumers remain explicitly2 in the audited inventory; no generic “2 or3” default or success-based fallback is allowed.

Snapshot is a distinct action contract, with no synthetic result version. Its audited callers pass `expected_result_version=None` and `expected_action="canonical_snapshot"`; reject None for potentially-solving actions and reject numeric expected versions for snapshots. Update the small snapshot call set explicitly rather than making None a wildcard. `GuardedJob.result` can revalidate its newly accepted evidence only by passing the version/action from its exact captured prepared O (None only for canonical_snapshot); that transport-level acceptance still cannot override the receiving owner's stricter policy.

Add a static/AST inventory test over every publisher and current reader in the ADR publication inventory. It must distinguish (a) explicit schema-derived version in General/Part-capable sinks, (b) explicit2 at Rectangle/geometry/Assembly sinks and (c) explicit snapshot-only None. Check delegated wrappers as well as direct `.revalidate`/`.consume` calls, with a reviewed finite allowlist for legacy helpers. Assert no live owner imports `service_v3`, calls the low-level evidence factory on saved data, or passes a broad version set. Extend this static inventory whenever a new authoritative sink is introduced; dynamic wrong-version injection still remains mandatory.

## 4. Exact prepared G, nonce and selection binding

Use the notation already established by ADR 0008: O is the exact ordinary operation, G is O plus its top-level backend contract. Canonical document hash, inner O fingerprint and full G fingerprint are different checks and are all retained.

Each explicit Check, trial solve, downstream replay, Finish, Part regeneration and extrusion creates exactly one `PreparedRequest` and one fresh 32-hex nonce. Capture selection once on the main thread, including lifetime, generation, interpreter invocation/resolved target, source root, timeout and effective launch environment. Deflection is in O. Preserve omitted/default distinctions, JSON scalar types, signed zero, formulas and array order. Do not recapture launch settings later.

The production operation binding must retain:

- Immutable prepared G payload, prepared O payload, nonce, action, selected result contract and full G fingerprint.
- Captured `BackendSelection`, owner token by object identity, scene/window/view-layer/workspace/area/session as applicable.
- Exact canonical base and candidate, saved draft slot, command revision, pending input revision/token, units and annotation layout CAS.
- For Finish, the exact `PartPublicationIntent.prepared`; its prepared object must be passed into the pending job, not rebuilt from `.request` and assigned a second nonce.

At transport construction/start, pending poll, result consumption, command/trial acceptance and Part publication, verify that the transported G reconstructed without nonce generation equals the captured prepared request. The returned `GuardedEvidence.guarded_request()` must match **that expected G**, not merely be a valid receipt for some request, the same document hash, action or owner. This applies when two requests have identical O and different nonces.

`GuardedEvidence` must validate the receipt against the exact G and captured selection, project only the known outer receipt field, and select the strict inner validator from O's exact result version and action. Revalidate retained immutable bytes on every authoritative read, and compare public copies by encoded tokens. Version checks belong before accepting authoritative results; failure-only envelopes remain correctly stamped, readable failure data with no publication/seed/DoF capability.

Current production source of evidence remains `GuardedJob.result` / `guarded_transport.execute`. The low-level acceptance factory is stateless validation, not durable nonce replay prevention. Do not call it on saved packets, clones, draft rehydration, rollback or Undo to mint replacement claims. Do not add a global persistent nonce registry or describe local capability receipts as remote authentication/security attestation.

Retain the existing 2 MiB inner request, separate 4 KiB/36-node contract allowance, response bounds and selected-sketch/journal bounds. Arc payloads do not authorize higher transport budgets.

## 5. One-shot transitions and the entire General chain

### Check

Prepare one exact solve G, acquire the existing execution lease, launch via `sketch_pending.prepare_guarded` and the existing `GuardedJob`. A ready process still owns cleanup until reaped. On main-thread completion, verify pending identity/G/version/selection, consume completion once and then consume the evidence's publication claim once to associate it with the checked draft. Immutable same-owner rereads remain permitted while every binding stays current.

Successful solve with unsupported profile supplies real solved geometry and real DoF for that solve. Failed solve supplies neither. Diagnostic recovery candidates must remain exact authored relation IDs from the failed request; intrinsic arc redundancy does not create a removable relation.

### Radius trial and dependent replay

1. Keep the raw field text, original relation ID/kind/refs/value, input revision and edit lease until all checks and checkpoint publication succeed.
2. Create trial solve G1 and validate successful result3 (or v2 when the exact candidate is legacy).
3. If the sketch is consumed by the extrusion, create distinct replay G2 for the **same exact trial candidate**, under the still-current captured backend generation/lifetime. G1 and G2 have different nonces and expected actions.
4. The completed replay must retain the whole successful graph and supported solid; matching solve success alone cannot accept a consumed edit. Wrong result version/action, a different but equivalent candidate, stale G1, or a different owner must reject even if G2 is good.
5. Retain `(G1 evidence, G2 evidence)` as the solution chain. Preserve downstream replay solved coordinates in the runtime `_Solution` solved-position cache (the accepted seed evidence), as current code does; never write them into canonical authored point records. Read arc geometry from the validated points and directed arc record; do not invent an independently stored arc-radius seed or overwrite authored points merely to match the solve. Reverse sweep changes only the authored direction. It preserves center/start/end IDs, endpoint roles, and every point seed; it must not inherit a generic solved-position rebase. Existing explicit release/recovery operations retain their own separately disclosed position policies.
6. Clone the command/UI wrapper, rebind the same owner, carry the same immutable evidence objects, apply the driver once and checkpoint with exact slot CAS. Revalidate the whole chain after the checkpoint before showing current solved state. If checkpoint/CAS or backend currency fails, leave the original pending raw edit and canonical Part intact.
7. A nonconsumed draft uses only its trial solve evidence. It still needs independent fresh replay on Finish.

### Preserve truthful solve reports when downstream construction fails

The current `GeneralSession.tick` exception path calls `cancel_native`, which clears `trial_evidence`; its ordinary failure inspector is designed for failed solves. Extend that exact owner path so a successful trial solve followed by native profile/extrusion failure is not collapsed into “Check failed” with its genuine DoF lost.

Retain a runtime-only, read-only attempt-report association in the existing General owner. It references the original immutable solve evidence and, when available, the separately validated failed replay evidence, together with their expected prepared G values, exact trial candidate, owner/revision/input token/input revision and selection. Do not call the low-level evidence factory, serialize this association, create a new process/lifecycle owner or grant a second publication claim.

A typed failed downstream replay may consume its own completion/publication claim once for this failure-report association with `require_success=False`, as a failed Check already does for diagnostics. It cannot enter driver acceptance or the Part publisher. Clear the command's trial-acceptance/seed association after the downstream failure; the retained attempt report supplies only explicitly labeled trial/attempt solve status and native failure details. Common contract/transport failure data cannot be promoted to guarded replay evidence.

Every report read revalidates the retained successful solve evidence and exact current pending candidate/input/backend binding. If showing a successful solver report inside the failed replay packet, validate and label it as the replay's solver report, rather than silently substituting it for the earlier trial's result. The two nonces remain distinct. Show, for example, “Trial solve succeeded: 5 DoF. Solid construction failed: unsupported native arc interval.” This is neither accepted-edit nor solid/export authority.

Clear this association on raw input or relation changes, Cancel, replacement Check, successful driver acceptance, local/history changes, backend revocation, suspend/owner retirement and load/rebind. Restoring old bytes cannot recreate it. A failed Finish can similarly retain the exact current Check and separately identify the failed replay, while keeping the draft open; it never converts that Check into a committed Part. Retry must perform fresh solve/downstream/Finish actions as appropriate.

### Finish

`GeneralSession.request_finish` checks the current solve chain and profile eligibility, captures one `PartPublicationIntent`, and launches that intent's exact replay G3. G1/G2/preview evidence cannot be substituted for G3 even if ordinary document bytes match. Finish does not reuse the driver replay as its publication operation.

After job cleanup and lease release, reacquire the shared main-thread replay guard. Recheck owner/base/draft slot/layout/units/selection/G/version before any mutation. Use the existing `_publish_candidate_locked` / `_apply_result` transaction: stage exact display datablocks, replace canonical/RNA state, consume the replay publication claim once, validate after writes and layout publication, then finalize. Clear the saved draft and retire the editor only after successful publication.

Double Finish, repeated consumption, a second intent around an old completion, publication after intent retirement and late completion after Cancel all reject. If an attempt fails before consuming an available claim, revoke that pending claim rather than recycling it. A consumed claim never becomes available again. Legitimate immutable rereads of already published current evidence do not consume another claim.

### Reusable current reads

Part current result, current General solution/DoF, solved picking, fixed/release seed actions, radius annotation values, formula-to-value conversion and failed diagnostics all use live guarded evidence plus exact owner/version/source bindings. They must never inspect a saved `CURRENT`/`READY` flag as authority. Drawing and predicates launch no process and wait on no cleanup.

A same-owner/revision clone may transfer the original full solution chain for an explicit command. It may not revalidate a bare JSON response into a new claim, lose G2, change version, or transfer to a Rectangle/another session. Public display geometry is disposable. Retained outlines drop their current fingerprint and remain clearly marked historical/unverified.

## 6. Revocation, history, rollback and pending process ownership

Retain the single `backend_runtime` generation/lifetime and single existing supervisor. Do not add arc timers, registries, leases or handlers.

- Root/Python/timeout/deflection preference callbacks revoke first, including A→B→A. Effective environment defaults are observed at launch, poll, consumption, current reads/seed-use and publication. Do not claim detection of invisible environment ABA between observations.
- Revocation clears current solutions, trial/downstream chains, failed diagnostics, prepared constraint intents, Part resolved-value authority, Rectangle authority, Assembly current display/report and available publication intents. Preserve canonical data, raw input, IDs, drafts, journal and annotation bytes.
- Starting a replacement Check invalidates the previous solve association. A failed launch/cancel does not restore it. Ready-but-unconsumed results are cancelled on identity or backend change.
- Local Undo/Redo increments command revision, clears authority, serializes the explicit restored sketch and launches only the ordinary explicit command Check behavior. Undo before first AddArc may select result2; redo selects result3. Saved authoring-envelope capability alone is irrelevant to this choice.
- Blender Undo/Redo, load, disable/re-enable, restricted-data deferred rebind, quit and owner retirement retain current ordering: retire RNA-bearing intents and callbacks before invalidating native references, then cancel/reap detached work. Fresh registration/reload gets a new lifetime. Saved receipts, CURRENT strings or reconstructed classes cannot restore evidence.
- Scene/window/workspace/view-layer/area changes, exact base/draft slot replacement, unit-scale change, raw input token/revision change and annotation CAS mismatch reject late work. Unrelated objects, other scenes and user unit settings remain untouched.
- A cancelling or failed child retains its opaque lease until actual process and file cleanup completes. Delayed old cleanup cannot release a new owner's token. The supervisor never accepts a ready response on behalf of a retired owner. No launch, native wait or retry occurs from draw.

Rollback restores canonical/RNA data and exact display identities through the existing seam. Revalidate live generation and the restored prior runtime's own source/version/owner association before restoring prior current status. Generation/lifetime revocation is irreversible by rollback, including change-inside-callback A→B→A. If restoration is incomplete, leave status failed/unverified, hide rejected geometry, retain recoverable authored input and disclose incomplete recovery. Never restore a lease, publication claim or old current label from saved state.

If candidate publication fails with no revocation and the previous canonical/display/runtime state is fully restored and still genuinely current, the existing prior evidence may remain current. The failed candidate evidence cannot authorize that prior model or a later retry. This preserves working v2 recovery rather than unnecessarily erasing all valid history.

## 7. Explicit downstream boundaries

### Part and display

Support profile Finish, sole extrusion creation, fresh regeneration, selected profile display with an existing downstream extrusion, active extrusion display, exact canonical load and same-ID radius edits. Use typed result3 mesh/topology already validated by `result_v3`/`sector_topology_v3`, not a legacy-shaped reconstruction. `_mesh_payload` and the staged display path must accept a strictly validated profile/solid payload without calling a v2-only output validator. A result3 profile can be displayed even though it is not a solid and cannot be captured as an Assembly Part.

All schema3 operation requests use the complete document. Do not omit an unrelated unsupported graph branch to make replay succeed. After arc insertion, attempts to add a second extrusion, primitive sketch, cut or additional arc-bearing feature are explicitly blocked as out of this bounded graph before committed state changes. Existing unrelated features must not be silently deleted or excluded.

### Rectangle

Keep its codec, request choice, diagnostics, saved dimensions and seed semantics v2. Add explicit v2 guards at `sketch_draft.accept_guarded_replay`, `_guarded_report`, preview reuse and Finish validation so generic `GuardedEvidence` support cannot accidentally admit a valid Rectangle-v3 packet. Do not allow the Rectangle owner in a Part that requires result3; direct invocation receives a precise unsupported-workflow explanation. Native legacy Rectangle controls must continue to pass.

### Geometry Check and STEP/STL

The action-aware policy rejects schema3 before `run_geometry_action` clears `_RUNTIME`/`_GEOMETRY_RUNTIME`, changes BUILDING/CHECKING labels, hides display, acquires a launch or creates a temporary destination. UI disables the action with the same reason; direct invocation is guarded independently. No v3 geometry capability is advertised or used. A valid Part3 solid is not accepted by the v2 geometry validator and no geometry report is fabricated from it.

Legacy v2 geometry/export continues unchanged: fresh canonical replay, atomic file writes, historical confirmed-write receipts distinct from stale current state, and unknown outcome after missing/malformed post-launch replies. No automatic retry; Undo/cancel never claim to reverse an external file write. These semantics remain in regression even though v3 export is blocked.

### Snapshot and Assembly

Keep `canonical_snapshot_guarded` and strict snapshot contract native/solver free and v1/v2-document only. Ordinary Save CAD Document is not this action. Snapshot evidence never enters solve/solid/Finish. Canonical snapshot data may feed only an independently guarded supported operation.

Reject schema3 working Part capture/update before launch and source mutation. Reject any schema3 embedded source at Assembly request/transaction preflight, including an inactive/unselected source, arc-empty schema3 and hand-edited imported Assembly files. Repeat the guard at synchronous/async Assembly accepted-response/display/report boundaries; real result3 Part/solve packets cannot satisfy Assembly evidence. Keep v2 Assembly replay/check/sample and failed save/update recovery unchanged. No automatic source conversion or silent retention of a falsely current updated Assembly is allowed.

### Persistence

Keep ordinary `.mcad.json` save and `.blend` save available for committed bounded arc Parts. Reopen/load must choose result3 afresh from embedded schema, never the saved report's version. A successful fresh guarded load may publish; a mismatch leaves the existing Part unchanged and the input file intact. Rebinding an already opened `.blend` restores authored data and historical cache only. Suspend/Resume unfinished arcs uses the separately proposed explicit authoring codec and retains raw input without creating publication evidence.

## 8. Known native representation failure and truthful recovery

Retain the existing underconstrained outward-seeded quarter-sector witness. It solves genuinely with 5 DoF and pure sector readiness; OCCT then returns a same-length trim interval shifted by exactly the stored binary64 tau. The strict native range guard rejects it, so the profile fails, the extrusion is blocked and no current mesh/topology/solid is published.

This is a **known conservative native-representation limitation**, not proof that the arc constraints failed or the mathematical sector is impossible. Preserve its original failed-positive record. Do not relabel that attempt as a newly passing native positive just because a rejection test now checks the correct fail-closed behavior.

Required user semantics:

- Show the genuine successful solve/DoF separately from the native profile failure; never replace it with 0 DoF, a solver error or an export-ready badge.
- Keep the authored candidate, pending radius raw text, direction, seeds and relation IDs. If editing an existing Part, keep the original committed Part and explicitly stale/last-good cache as applicable. A failed fresh Finish does not commit the candidate or close/discard its draft.
- Explain: “The sketch solved, but this arc representation is outside the current solid builder's supported range. Your draft is retained. Complete the intended fixed-center/H/V/radius constraints and Check again, or Undo the edit.” This is a user-directed recovery option, not a promise that adding constraints fixes every case.
- A new explicit action gets a new G and nonce. Do not automatically retry native construction, add constraints, reseed, swap endpoints, change direction, reduce the interval modulo tau or loosen a tolerance.
- Keep the fully constrained 0-DoF quarter/major controls as separately declared positive controls. Do not require a blanket zero-DoF policy for all legacy or all supported sketches merely to hide the limitation.

The known-failure GUI witness is predeclared pure saved General draft intent with an exact canonical base. Ordinary Resume restores it without authority; genuine Check and Finish establish the actual failure. Record fixture/base/witness identities. Failed canonical Part file loading must continue to reject without publication. This negative fixture is separate from the mandatory manually drawn positive workflow.

## 9. Concrete implementation inventory and cutover order

Paths below are relative to `cad_arc_core`. The authoring/persistence companion proposal owns command records, gestures and codecs; the following is the owner-admission work that must land with it.

| File or seam | Bounded action |
|---|---|
| New `blender_addon/mechanical_cad_blender/operation_contracts.py` | Central native-free exact schema/action/owner policy and version dispatch. Delegate to existing strict validators; no new serializer or native work. |
| `guarded_evidence.py` | Strict result2/result3 dispatch, action whitelist, default-v2 expected-version reread/consume API with explicit3 opt-in and separate snapshot-only None; immutable G/O/receipt and one-shot claim unchanged in meaning. |
| `guarded_transport.py` | Preserve exact prepared G across launch/consume and test v3 path; no second transport or result factory. Keep export uncertainty unchanged. |
| `sketch_pending.py` | Guarded production path accepts explicit v2/v3 solve/replay through policy; keep legacy unguarded helper semantics intact. Check transported/prepared G and owner version at consumption. |
| `general_sketch_draft.py` | Candidate-driven solve/replay version selection; strict per-version solve/downstream validation; complete same-owner evidence chain, versioned solved data and retry-safe raw edit acceptance. |
| `general_session.py` | Pin expected prepared completion for solve/trial/downstream as well as Finish; profile eligibility; current reads; truthful exact-bound attempt reports after downstream failure; fresh Finish; no available claim reused after failure/retirement. |
| `constraint_actions.py`, `constraint_diagnostics.py` | Version-aware strict solve validation for current seed/diagnostic use; retain full runtime bindings; no intrinsic-arc diagnostic invention. |
| `general_view_geometry.py`, `general_sketch_overlay.py` | Version-aware validated solved arc display, exact center/start/end ID mapping and current/retained distinction. Companion authoring design defines rendering/picking math. |
| `document_state.py` | Replace v2-only selection with action-aware production policy; bind expected version in transaction/runtime record; retain sole publication/rollback/current-reader seams and formula conversion checks. |
| `part_publication.py` | Select v2/v3 once from exact candidate, carry same prepared request into pending Finish, verify G/version and final CAS, retire once on all outcomes. |
| `display.py`, `sketch_display.py` | Explicit current typed profile/solid rendering; retain v1/v2 helper behavior and genuine open-line display. Never approximate arc geometry to bypass a validator. |
| `sketch_draft.py`, `viewport_sketch.py` | Explicit v2-only Rectangle gates even after generic evidence supports3. Preserve payload bytes and all legacy successful/recovery paths. |
| `geometry_operations.py`, `guarded_operations.py`, `assembly_operator_helpers.py` | Early schema3 unsupported-action rejection before launch/current-state/file/source mutation; snapshot stays separate and native-free. |
| `assembly_state.py`, `assembly_pending.py`, `assembly_display.py` | Audit/reinforce exact v2-only whole-source preflight and accepted evidence; preserve synchronous/async rollback and historical report behavior. |
| `operators.py`, `workspace_ui.py`, `constraint_ui.py`, relevant panel/help modules | Supported extrusion/active-feature controls; graph/action rejection in execution as well as UI; truthful blocked-action and native-failure explanations. |
| `backend_runtime.py`, `registration.py`, existing supervisor/lease modules | No second lifecycle design. Audit/test v3 propagation through existing invalidation and retirement. Change only if a demonstrated uncovered v3 association requires it. |
| `result_v3.py`, `part_contracts_v3.py`, `sketch_contracts_v3.py`, `sector_topology_v3.py` | Reuse qualified strict contracts. A narrow exported pure graph/policy helper may replace private access, with identical accepted/rejected sets and separate review. No relaxation. |
| `service_v3.py` | Remains data-only; no live import and no owner-token promotion. |
| `src/mechanical_cad/*` | Expected unchanged. No new server capabilities, geometry actions, solver or kernel changes in this slice. Any discovered need pauses the dependent work for separate authorization. |

Implementation sequence:

1. Freeze this bounded policy, companion authoring/persistence decisions, exact source and legacy fixtures. Define all expected outcomes before native runs.
2. Implement pure dispatch/evidence extensions and pure tests, keeping existing live selection v2 until every consumer is ready. Do not present this intermediate state as an arc workflow.
3. Implement the versioned authoring/persistence additions and the complete General/Part owner cutover together, plus explicit downstream/Rectangle barriers. Audit every sink from the ADR 0008 publication inventory.
4. Freeze source for an independent mutation/bypass/transaction audit. Resolve findings with new exact-source runs; never reuse outcomes across materially changed code.
5. Run full pure/native/Blender/persistence/installed-GUI qualification. Only then describe the exact tested build as a bounded arc authoring preview. No release replacement or external publication is implied.

## 10. Finite acceptance matrix

This is a finite **predeclared minimum** for the new cutover, in addition to all existing regression suites. Each numbered row must have a result and an artifact/test name; where a row names a finite set, enumerate its members in the run manifest before execution. Do not turn a required positive into a rejection-only pass after a failure. Pure/host-port tests and native Blender/GUI results are distinct.

### A. Contract and immutable evidence (A01–A14)

| ID | Cases | Required disposition |
|---|---|---|
| A01 | Original sketch1 and sketch2 Part solve/replay | Production explicitly2; exact legacy inner bytes and semantics retained |
| A02 | Sector schema3 solve and replay | Correct minimum capabilities; genuine strict result3 retained through GuardedJob |
| A03 | Arc-empty schema3 line loop, open line chain and circle | Explicit3 retained; no downcast; original typed semantics |
| A04 | Legacy-only candidate inside promoted envelope3; Undo and Redo first arc | Version follows exact candidate:2, then3; no envelope inference |
| A05 | Explicit result1/2 against schema3; result3 against a production legacy-only owner | Local rejection; no downgrade launch or mistaken current evidence |
| A06 | bool/float/string/unknown result and nested schema tags | Fail closed with preserved input |
| A07 | Each missing required capability, old backend without contract, wrong imported origin | No accepted current result and no fallback |
| A08 | Missing receipt, wrong phase, wrong nonce, wrong full-G fingerprint, altered capability set | Reject despite plausible successful inner result |
| A09 | Same O/owner/action, new nonce; same nonce with changed action/feature/options/document | Only the exact prepared G accepted |
| A10 | Wrong inner result stamp/hash/fingerprint, arc direction/ID, output algebra, topology/mesh lineage | Strict inner rejection despite a valid outer receipt |
| A11 | Mutated detached G/O/response/projection; forged evidence class/fresh claim; tampered prepared fields | Revalidation rejects; public copies never authority |
| A12 | Repeat reread, repeat completion, repeat publication, cancel available claim | Current reread succeeds; completions/claims one-shot; cancelled claim cannot read current |
| A13 | DataOnlyJob result and saved packet routed into each live sink | Bare data rejected; no factory rehydration production bypass |
| A14 | Client import DAG, static publisher/current-reader version inventory, and exact request/metadata budget edge controls | Default reread/consume remains2; only audited schema-bound owners opt into3; snapshot-only None; no Blender/core/native imports in contract leaves or widened budgets |

### B. General and Part ownership (B01–B14)

| ID | Cases | Required disposition |
|---|---|---|
| B01 | Current schema3 Check with 0-DoF supported sector | Genuine DoF and directed solved display; no canonical publication yet |
| B02 | Successful isolated-arc solve with profile not ready | Solved data readable; Finish blocked; draft suspend/resume available |
| B03 | Genuine failed arc solve and intrinsic redundancy diagnostic | No failed-solve seeds/DoF/readiness; only authored failed IDs eligible for recovery |
| B04 | Nonconsumed radius trial acceptance | Exact input accepted once, raw text preserved on failure |
| B05 | Consumed radius trial plus full extrusion replay | Both exact evidences remain current; one command accepted; IDs preserved |
| B06 | Stale trial with fresh downstream, stale downstream with fresh trial, cross-owner or cross-version pair; genuine solve then failed native downstream | Invalid chain rejected; raw edit retained; genuine current trial DoF separately displayed after native failure, never accepted-edit authority |
| B07 | Same-owner clone, then seed-consuming command | Full original solve/downstream chain transferred; no new claim or lost downstream binding |
| B08 | Prepared constraint intent followed by revision/input/backend change | Reject before changing seed/relation/journal |
| B09 | Finish with exact G3 versus same-document G1/G2/another G3 | Only exact fresh Finish G accepted |
| B10 | Double Finish, retired intent, checkpoint/layout CAS failure | No duplicate commit; draft retained; claim never recycled |
| B11 | Part profile Finish, sole extrusion, active profile with downstream extrusion, active solid | Correct validated display/volume/status; one shared publisher |
| B12 | Same-ID literal radius5→7 and formula-parameter radius5→7 controls | New geometry; original IDs and untouched seeds/expressions preserved |
| B13 | Formula-to-value, DoF label, solved picker, radius annotation, failed diagnostics after revocation | All current affordances unavailable; historical bytes alone insufficient |
| B14 | First arc in incompatible graph; attempted second extrusion/primitive/cut/arc feature | Explicit bounded-scope rejection without deleting unrelated features or changing committed Part |

### C. Lifetime, rollback, process cleanup (C01–C12)

| ID | Cases | Required disposition |
|---|---|---|
| C01 | Root, Python, timeout and deflection callbacks; direct A→B→A after success | All completed v2/v3 evidence revoked; authored bytes unchanged |
| C02 | Effective environment changes at launch, poll, consumption and current-read/publication | Observed mismatch revokes; captured launch values never replaced |
| C03 | Cancel before start, running and ready-but-unconsumed | No late acceptance; cleanup retains lease until reaped |
| C04 | Crash, timeout, malformed response and cleanup delay | Bounded failure; explicit retry only after cleanup; no stranded lease |
| C05 | Old cleanup finishes after newer operation owns a lease | Cannot release newer lease or attach old evidence |
| C06 | Source/base/draft slot/input/units/scene/window/workspace/view-layer/area mismatch | Pending result rejected; no wrong-target mutation |
| C07 | Local Undo/Redo around first arc and accepted radius edit | Correct explicit version/IDs/history; no restored authority |
| C08 | Blender Undo/Redo, file load, disable/re-enable and deferred rebind | New/advanced lifetime; saved CURRENT/receipt cannot regain authority |
| C09 | Owner retirement and actual process exit with running/ready v3 job | RNA intent retired first; supervised cleanup collected; no new owner registry |
| C10 | Inject backend A→B→A then exception inside `_apply_result`, layout publication and final validation | Canonical/display rollback, but revoked authority never restored |
| C11 | Publication exception without revocation and complete prior-state rollback; partial rollback failure | Prior genuinely current evidence may survive first; second remains visibly unverified/failed |
| C12 | Multiple CAD scenes, linked unrelated objects, draw/predicate repetition | No unrelated mutations; no native starts or cleanup waits from draw |

### D. Explicit barriers and backward compatibility (D01–D10)

| ID | Cases | Required disposition |
|---|---|---|
| D01 | Genuine v3 Rectangle solve/replay supplied to Rectangle accept/current seeds/preview/Finish | All rejected; genuine v2 positive controls accepted |
| D02 | Schema3 Check Geometry, STEP and STL UI/direct calls | Block before runtime/display mutation and before any launch/tempfile/write |
| D03 | Schema3 canonical snapshot, capture and update | Block; ordinary Save remains available; no solver/native snapshot import |
| D04 | All three Assembly actions with active, inactive or arc-empty schema3 source | Reject whole request before mutation; preserve prior accepted Assembly/source/report |
| D05 | v3 solve/replay evidence or snapshot evidence in another action/owner's sink | No cross-action/current/export authority |
| D06 | Legacy omitted/result1/result2 differential corpus, early errors and old numeric lexemes | Historical ordinary stdout/exit and accepted behavior unchanged |
| D07 | Legacy canonical hashes, Rectangle drafts, General journals/envelopes and annotations | Untouched legacy bytes; explicit migration only in companion policy |
| D08 | Legacy General, Rectangle, Part, geometry/export, snapshot and Assembly positives | Existing accepted/recovery behavior retained across all nine production action families |
| D09 | v2 exports: pre-dispatch rejection, lost/malformed reply after launch, valid write then stale publication | Destination unchanged for no-dispatch; unknown versus historical written outcome truthful; no retry |
| D10 | Source inventory/frozen qualification references | Historical ce5b50b service records remain immutable; new intended owner semantics documented, not hidden by rewriting old evidence |

### E. Native user workflow and qualification (E01–E10)

| ID | Cases | Required disposition |
|---|---|---|
| E01 | Actual native Blender Center Arc + two shared-ID radial lines + center fixed/H/V/radius | No fixture shortcut: genuine user-created current 0-DoF sector |
| E02 | Fresh Finish, 10-mm extrusion at radius5, same-ID radius7 edit and Finish | Valid single solids, five faces, expected quarter-sector volumes near 196.34954084936206 and 384.84510006474966 mm³ under existing qualified mass policy |
| E03 | Four predeclared directed quarter/major controls, explicit Reverse with stable IDs | Reverse changes only direction, never endpoint roles/seeds; correct solved sweep, side.arc provenance and expected analytic dimensions/volume |
| E04 | Original outward-seeded 5-DoF periodic-range witness via predeclared pure saved draft and ordinary Resume/Check/Finish | Genuine solve retained, strict native rejection, no mesh/solid publication, recovery UX; original required-positive failure remains recorded |
| E05 | Inconsistent radius edit, unsupported profile and out-of-bound height/radius | No silent repair; original Part and pending draft recoverable |
| E06 | Actual GUI cancel/raw field/reopen, suspend/resume and Undo/Redo | Visible status and selection/IDs match retained intent; no stale success |
| E07 | Two-process `.blend` persistence and `.mcad.json` save/load | Authored IDs/expressions recover; no saved evidence authority; fresh replay required |
| E08 | Exact installed candidate with matching backend and baseline-only/mismatched backend, then settings correction | No downgrade; draft retained; fresh corrected Check/Finish succeeds |
| E09 | Existing full Ruff/format/pytest and native Blender gates, including real process-exit gates | Exact final source; all failures fixed or disclosed; no focused-suite substitution |
| E10 | Independent exact-source bypass audit and final source/archive/install manifest | Every declared outcome linked; package/runtime identity recorded; no cross-source reused result or unqualified platform claim |

These 60 numbered rows are the bounded owner-admission acceptance set. The authoring/persistence companion adds its own explicit codec/gesture tests. Existing numerical/native service regressions are retained, not replaced by these workflow tests. Run real native gates serially with bounded runtimes, `--python-exit-code 1`, explicit result markers and verified process collection. Pure host ports alone do not establish Blender RNA/GUI correctness.

## 11. Parent-approved bounded implementation

The parent approved this bounded four-gate implementation on 2026-10-17, conditional on independent consistency review. The approved work is limited to the following, with the product exclusions above:

1. Edit the listed add-on owner/policy/display/UI modules, the companion's explicit arc command/UI/persistence modules, associated tests/examples and scope documentation in `cad_arc_core`, starting from the pinned clean source. Implement solve3/replay3 General/Part admission and early blocking of every unsupported downstream action. Do not edit kernel/solver numerical policy or add v3 geometry/snapshot/Assembly capability.
2. Run pure lint/format/unit checks, then the existing and new real sidecar/native Blender headless/GUI/lifecycle/two-process persistence gates using the already selected pinned runtimes. Create bounded temporary model/export-test files and qualification evidence outside the source checkout; collect every owned process. No new runtime installation or system/security setting changes are included.
3. Build and install a separately named candidate add-on ZIP in an isolated Blender test profile for exact-package qualification, with deliberate matching/mismatching backend tests. Do not overwrite, rename or replace the usable 0.5.2 release artifacts or the prior immutable qualification archives.
4. After independent review, make coherent local source commits and produce a new source/evidence archive if the parent wants those deliverables. No push, merge, public release, external upload, automatic model Git history or publication is included.

If an implementation finding requires a broader arc graph, open-arc canonical save, result3 export/Assembly/snapshot, a revised kernel periodic-range policy, dependency changes or tests on a different machine/platform, stop that dependent scope and request a separate concrete approval. Keep already authorized independent work moving.
