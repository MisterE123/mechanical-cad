# Line endpoint Trim / Extend

The sketch palette offers Trim and Extend for explicit straight-line endpoint
edits. Pick the target line near the endpoint to change, then pick a distinct
finite boundary line, full circle or directed arc. A purple line previews the resulting
target geometry.
Apply (or Enter) accepts one journaled point move; Cancel (or Esc) discards the
preview. Local Undo/Redo restores/reapplies the exact original point identity.
The boundary and all other entity IDs remain unchanged.

Trim requires the boundary to cross inside the target line. Extend requires the
intersection beyond the picked endpoint, facing the boundary. The intersection
must lie on the finite boundary segment, full circle or finite arc sweep. For a circular boundary with
two eligible crossings, the first valid crossing reached from the chosen endpoint is
used. Trim moves inward; Extend moves outward. Circle radii come from the
visible resolved sketch, including driving radius dimensions, not a sampled
display polygon. Tangent and nearly tangent contact is refused rather than
treated as a crossing. Arc boundaries retain their authored direction and
minor/major sweep: roots outside that finite sweep never become candidates.
An intersection within 1e-7 mm of an arc endpoint is included; this spatial
tolerance does not grow with radius. Unequal-radius unsolved arc seeds must be
checked first rather than silently projected onto a circle.

Parallel/coincident lines, midpoint
endpoint ambiguity, zero-length results, and out-of-range coordinates fail with
an explanation rather than guessed geometry.

Initial scope is deliberately conservative:

- Straight target lines only; boundaries may be finite lines, full circles or arcs.
  Trimming/splitting circle or arc targets is not yet supported.
- One endpoint moves; this does not split the middle out of a line.
- An endpoint shared with another curve cannot move through this tool.
- Relations referencing the target line or moving endpoint must be released
  explicitly first. Constraints and dimensions are never silently removed.
- The new endpoint meets the boundary geometrically but is not automatically
  merged with another point or given a coincidence relation.
- Preview is transient and is not a saved unfinished drawing proposal.

Focused geometry, identity, journal replay and Undo tests cover both ends and
both modes, circle near/far crossing selection, tangent/disjoint rejection,
resolved radius use, and preserved boundary constraints. The Blender 5.2.2
headless smoke exercises registered actions,
preview rendering data, Cancel, actual native Apply, and Undo/Redo with
deterministic pick inputs. Circle Trim and Extend additionally exercise real
native radius solving, boundary picking, Cancel/repeat, Apply and Undo/Redo.
Actual mouse interaction remains a separate GUI qualification step.

## Circular-boundary development evidence

The focused endpoint-edit and view-geometry suites pass 140 tests. The expanded
native Blender 5.2.2 smoke uses the existing development sidecar and passes its
explicit result marker. Broader arc-command tests retain 11 pre-existing failures
in older arc-admission expectations, reproduced on the integration checkout
without this change (3e8b8f3). They were not hidden or changed in this slice.
Full-suite, installed-ZIP, two-process .blend reopening and real mouse GUI
qualification were not rerun for this bounded change.

## Finite-arc development evidence

The expanded endpoint-edit and view-geometry suites pass 158 focused tests.
The separate native Blender 5.2.2 arc-boundary smoke covers minor, major and
reversed directed sweeps, the actual Reverse Arc command, endpoint hits,
Extend with an excluded nearer supporting-circle root, and no eligible arc
intersection. Accepted edits solve natively, retain boundary entity/constraint
records, and pass local Undo/Redo. Rejected edits remain unchanged and cannot
Apply. Pure checks additionally cover the spatial endpoint tolerance, missing
resolved geometry, unequal-radius refusal and shared/constrained target guards.
This remains a focused development check, not new GUI or package qualification.
