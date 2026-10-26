# Direct depth entry from a selected sketch

**Extrude Selected Sketch** already binds an explicit recorded profile. In
Blind or Symmetric mode, its first popup display now activates the depth text
field, so typing replaces the initial depth without another pointer trip.

This uses Blender's native `UILayout.activate_init` API, verified in bundled
Blender 5.2.2. The request is transient, initialized only when both profile and
shortcut navigation properties are explicit, and consumed by the first draw.
Neither repeated preview redraw nor switching back from Up to planar face can
re-request initial focus. Generic extrusion entry remains unchanged. No synthetic
input, automatic Apply, schema or expression parser changes are involved.

The existing depth field accepts units and formulas. Editing a field is not
acceptance: leave the text field to update its preview, then explicitly Apply.
Native text editing and confirmation behavior is otherwise unchanged.

## Verification

- 43 saved-sketch shortcut tests, including 16 new focus cases; combined with
  preview tests, 117 pass. Ruff passes.
- Actual fresh source GUI: shortcut starts with `10.0` selected. Typing `1/2 in`
  directly produces a valid preview. Blind → Symmetric → Up to planar face →
  Blind retains the text; hidden depth is not activated. Cancel clears the
  preview and preserves exact canonical document/output.
- Reopened shortcut again activates only its initial depth. Explicit Apply of
  half-inch input creates one 12.7 mm extrusion (638.37164 mm³); Undo restores
  the original document. Direct `height*2` entry then explicit Apply creates
  one 20 mm extrusion (1005.30963 mm³). The stored formula survives independent
  saved-model reopen and regeneration.
- Generic/remembered-intent and first-draw/mode-switch assertions are automated;
  no claim of actual generic-menu GUI qualification. No full aggregate rerun or
  new installed archive. Frozen 1.28 and existing broader test limits remain.

Evidence: `evidence/extrude-depth-entry-20261025/` and
`evidence/initial-depth-focus-20261025/`. One denied Apply attempt was confirmed
unexecuted; a later single retry after newly supplied explicit example-file QA
authorization succeeded. Both outcomes are recorded, not treated as a product bug.
