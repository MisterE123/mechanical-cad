# Bounded visual feature reselection

Edit an existing Fillet, Chamfer or Shell from feature history. Choose
**Reselect edge / opening**, then **Continue**. The viewport shows that feature's
saved **input body**, not the already blended or hollowed output. Pick a supported
exact edge (Fillet/Chamfer), or a stable planar opening (Shell). For blends, F
switches to the explicit two-face fallback. Return to the same feature editor,
review the retained name, expression and dimensions, choose **Apply edits**, and
Continue to rebuild the complete candidate.

Esc/right-click during picking returns to the editor with the previous selection
and pending values. Cancel in the editor leaves the document unchanged. The
original final display and its selection are restored when input review ends.
Blender Undo remains the normal committed-edit history.

The input review has a separate temporary owner, captured source/backend/unit
binding and read-only exact replay receipt. It never changes canonical active
output, replaces the accepted runtime association, or publishes a shortened
history. Edited/transformed review meshes, changed sources, changed backend,
changed units or lost viewport ownership cannot authorize a pick. Apply always
uses the ordinary whole-document atomic rebuild, not the review receipt.

## Deliberate bounds

- Reselection is limited to the saved base of the feature being edited. To change
  the input feature itself, apply that change first and reopen the editor.
- Stable face-pair intent still needs the native unique-edge check. No mesh edge
  index or heuristic identity is saved. Missing/ambiguous provenance fails closed.
- Shell opening picking is limited to stable planar faces; it selects one opening.
- Read-only replay can inspect a successful upstream input even if a downstream
  feature fails. The direct edge catalog still requires a successful complete
  replay. This is not general failed-document recovery. Rejected edits retain
  the accepted model; eligible reference failures can additionally keep one
  transient [unapplied edit for explicit repair](STAGED_EDIT_REPAIR.md).
- Viewport navigation is allowed, but object/scene/backend/unit changes revoke
  review. The temporary review object is not a canonical export source.

## Verification boundary

`tests/blender_solid_reselection_smoke.py` exercises isolated native Blender
5.2.2 LTS background input review, canonical/runtime isolation, temporary ownership,
modified display rejection, source staleness, exact edge-catalog preparation,
selection/visibility restoration, partial read-only replay, raw expression/name
retention, and atomic successful/rejected editing. Existing face and edge picker
smokes cover their shared guarded selection code. These checks are not real GUI
popup/gesture or installed-ZIP qualification. Interactive editor transition,
Escape during native cancellation, Undo/Redo and popup legibility still need that
qualification before release claims.

## Integrated lifecycle check

The next-development integration keeps the saved support-orientation and Shell
lineage baseline intact. Input reviews retire synchronously before history/load/
exit owner teardown, backend invalidation, and file save. Saving cannot persist
a temporary input mesh or its hidden-final-display state. Backend invalidation
still deliberately hides outdated final geometry after review restoration.

The integrated native reselection smoke additionally checks review retirement,
owned-object removal, visibility restoration for ordinary teardown/save, and
unchanged canonical JSON. Targeted integration checks passed 111 unit/native-kernel
tests and full Ruff lint/format. Native background support-orientation and Shell
inner-surface create/separate-process reopen checks also passed. These do not
qualify interactive popup transitions, mouse interaction, Undo/Redo or ZIP install.
No version change is part of this integration.
