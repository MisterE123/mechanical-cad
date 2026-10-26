# Correct a refused circle expression without retyping the draft

Direct primitive circle Edit Feature dialogs (free or face-supported) can now
return a refused expression draft. Only an authenticated, guarded per-feature
replay failure with `unknown_parameter` or `invalid_expression`, attributed to
that exact edited feature, qualifies. The prepublication boundary preserves this
existing typed code; there is no message-string classification or protocol change.

The accepted model must still exactly match the original. Copied fields are a
bounded, string-only whitelist, with exact feature/context checks. The existing
single-shot callback rejects changed/closed/rebound contexts, a newer editor,
non-Object mode and active operation leases. Consent is never retained. The user
must correct the restored value and explicitly Apply; Cancel does not return again.
No source/model schema, repair proposal, automatic evaluation or auto-Apply is added.

## Verified scope

- 107 focused unit tests passed, including 19 typed-seam cases and bounded draft
  checks; Ruff passed.
- Native Blender 5.2.2: free/face circle typed-refusal dispatch, actual resume invoke,
  authority reset, mismatched IDs/codes, altered original/candidate, and both retry
  modes across the existing context/single-shot matrix passed.
- Actual source GUI: unknown `missing_radius` returned intact with correction
  notice while model stayed unchanged. Cancel closed without a loop. A second
  refused draft corrected to5 applied once; one Undo restored original named
  radius4 and one Redo restored local5. Selection/output remained separate.
  Saved model independently reopened and rebuilt at volume11214.6015625.
- First GUI attempt exposed a previously unexercised resume assumption that every
  feature kind had inputs. Free circles have none; safe empty lookup fixed it.
  Failed-attempt evidence remains retained alongside final verification.
- Static review caught order-dependent dynamic face enums in copied drafts.
  Input IDs now restore before their dependent face choices, independent of JSON
  order. Native reversed-order retries check changed support and semantic face,
  plus the existing consent target/end-face path.

## Limits

Other editors, geometry/transport/context failures, unsupported expression codes,
and errors attributed to other features keep their prior behavior. Invalid shared
parameter definitions can fail global document validation before any per-feature
attribution, so they are deliberately **not** automatically returned by this pilot.
This is source-only work after frozen1.28; no new installer or broad aggregate pass.
