# Feature history search

Open the existing filter drawer below feature history and enter a name or stable
feature ID. Matching is case-insensitive and retains Blender's native wildcard
semantics. Labels and IDs are combined with OR; duplicate labels remain separate
features. Clearing restores all rows in their original order.

The search drawer remains visible while text is active, with a match count (or
an explicit no-match message) and a short notice if the selected feature is
hidden. Clearing the field allows the drawer to be collapsed again. The empty
collapsed drawer adds no new permanent controls. Sorting and inversion are not
exposed because construction history keeps its canonical order.

This is presentation only, over the existing bounded feature collection. No
canonical data, selection, active output, feature indices or edit targets change.
The Part's failed/dirty/stale summary stays outside the filtered rows. Display and
editing continue to target the selected feature; each row's pencil targets that
row's stable ID, never a filtered ordinal.

## Verification boundary

- `blender_history_filter_smoke.py`: native Blender RNA collection, prior default
  name-filter gap, labels/IDs/case/globs/no matches/clear, original indices and
  stable row edit targets, hidden selection notices and canonical non-mutation.
- `blender_history_direct_edit_smoke.py`: existing guarded row dispatch.
- `blender_feature_action_placement_smoke.py`: status and repair guidance remain
  outside history; a stale empty-document fixture and obsolete dual-editor
  expectation were reconciled with the existing contextual-action contract.
- Source-loaded Linux Blender 5.2.2 GUI checks: narrow sidebar search, hidden
  selection, no matches, clearing and collapsing, dirty/failure summaries.

No new geometry behavior, package installation, persistence qualification,
Windows verification or full historical-suite claim is made.
