# Suspended rectangle drafts

This development milestone keeps a viewport rectangle's unfinished authoring
state when leaving Sketch. It does not change the canonical CAD schema, feature
history, kernel, sidecar protocol, or the delivered 0.2.0 release archives.

## Separate ownership

- The scene's `document_json` remains the only canonical design. A draft is an
  optimistic transaction against its **exact original JSON bytes**, with a SHA-256
  checksum. It is never rebased onto a changed document, even if the changes seem
  unrelated or are only serialization whitespace.
- A scene has one UI draft slot. It is not a feature and never participates in
  replay/export. New/Edit cannot replace it without explicit Resume or Discard.
- Only one modal draft can be active across Blender windows. A different window
  can Resume a scene's suspended draft when no other modal draft is active. The
  viewport/window/workspace and timers are always newly acquired on Resume.
- A restored outline is **unverified**. No persisted solver report, current DoF,
  or validated-candidate claim is trusted. Apply Dimensions or Finish performs a
  fresh native sidecar replay before making a current result claim.

## Preserved authoring intent

The version-1 UI snapshot stores original base JSON, feature identity, named
parameter keys, original exact parameter values/text, placement phase, corners,
authoring seed bounds, last visible dimensions and outline, raw width/height
strings, fixed-position intent/target, explicit release-anchor seed overrides,
and the last solved point identities needed for later release/refix operations.

Whitespace, invalid formulas, blank strings, invalid unit suffixes, and decimal
text remain exact. Input currently in the native Dimensions dialog is retained
separately from the last-applied draft after Blender commits the edited field to
its RNA property. A restored pending dialog must be reopened and Applied or
Cancelled before Finish; Finish cannot silently ignore those inputs. A native
text field's unconfirmed keystrokes are owned by Blender until field confirmation
or focus loss; this is a GUI verification boundary, not a promise to intercept
Blender's private edit buffer.

Unknown versions/fields, malformed JSON, duplicate fields, invalid coordinates,
unsupported identities, checksum mismatches, and snapshots larger than 8 MiB
fail closed. The stored text is left intact, with an error and explicit Discard
available. Data is JSON only, never pickle or executable model content.

## Lifecycle rules

| Event | Draft result | Canonical result |
| --- | --- | --- |
| Leave Sketch / change area or mode | Suspend in owning scene; release draw handles, event timer, popup-close timer, cursor and status text | Unchanged |
| Change scene | Suspend in source scene; never transfer into destination scene | Both scenes unchanged |
| Return to Sketch | Show Resume / Discard; do not automatically start a modal | Unchanged |
| Resume compatible base | Reacquire viewport resources and restore exact UI input; outline/DoF unverified | Unchanged |
| Resume changed base | Reject; retain snapshot and explain recovery | External edits preserved |
| Dimensions Apply | Fresh solve of temporary candidate; retain rejected raw text | Unchanged |
| Dimensions Cancel | Abandon only unapplied popup input | Unchanged |
| Esc / Cancel Sketch | Explicitly discard this draft and release resources | Unchanged |
| Discard Saved Draft | Remove this scene's suspended UI slot | Unchanged |
| Successful Finish | Fresh validation, one canonical transaction, clear draft slot, release resources, request Part | Accepted edit committed |
| Failed Finish | Keep draft and actionable error; no old DoF claim. The general editor may transfer a complete existing-sketch edit into one explicitly unapplied reference-repair proposal; see STAGED_EDIT_REPAIR.md | Unchanged |
| Blender Undo / Redo | Suspend before history changes; restore latest UI snapshot afterward using original runtime scene ID | Blender applies requested canonical history change |
| Save `.blend` | Checkpoint active draft or retain suspended snapshot; do not leave active editing | Save committed scene design independently |
| Load `.blend` | Read saved UI snapshot; no automatic handlers/solver/replay | Existing loaded-document validation rules apply |
| Disable add-on | Snapshot active draft, release all owned resources; retain scene UI data | Unchanged |
| Re-enable add-on | Rebind data; offer explicit Resume/Discard | Unchanged |

`.mcad.json` stores committed feature history only. It does not contain drafts.
Part authoring, New/Open Document and exports require resolving a saved draft
first, so the tool never silently changes its base or exports a preview as a part.

## Stale-base recovery

Resume never changes the current document to make the draft fit. Restore the
exact original document using the user's chosen Undo/Redo or file workflow, then
Resume; alternatively explicitly Discard the old draft and begin editing the
current document. No “best effort” merge, identity substitution, or silent seed
regeneration is performed.

The latest UI draft is retained across canonical Undo/Redo. Empty draft slots are
also retained, so Undo cannot resurrect a draft explicitly Finished or Discarded.
If Undo or scene deletion removes its owning scene, an in-memory recovery record
remains keyed by Blender's original scene runtime identity. It is visibly
unavailable, never transferred to a similarly named scene. Restoring the original
scene with Undo/Redo restores its draft. This deleted-scene recovery is limited
to the current Blender session; it is not durable backup or cross-file recovery.
Loading another `.blend` clears that runtime journal and reads the selected
file's own saved UI state. Unsaved changes are subject to Blender's normal file
save/load behavior. Save `.blend` before leaving the file if the draft is needed.

An externally replaced UI slot is never overwritten by checkpoint/Finish.
Interruption retains a separate in-memory recovery copy and shows a recovery
notice. This exceptional conflict path does not merge the copies automatically.

## Verification and limitations

- `tests/unit/test_draft_store.py`: pure versioned snapshot round trips, exact raw
  input, all placement phases, release/refix seeds, original doubles, stable IDs,
  downstream output, pending popup values, stale-base rejection and corruption.
- `tests/blender_draft_suspension_smoke.py`: native Blender 5.2.2 LTS RNA/timers,
  real solver/rebuild, repeated suspension, same-revision Resume, changed-base
  rejection, Cancel/Finish, real Undo/Redo, enable/disable, and a separate fresh
  native Blender process reopening an actual `.blend` with active draft input.
- `tests/blender_viewport_sketch_smoke.py`: existing geometry, modal transaction,
  branch rejection and downstream identity checks retained, with navigation
  assertions updated from discard to suspend plus explicit Discard cleanup.

Headless success does not establish native popup usability, mouse routing,
visual labels, or every window/layout combination. Native GUI acceptance and
platform evidence must be recorded separately. Windows/macOS remain unqualified.
