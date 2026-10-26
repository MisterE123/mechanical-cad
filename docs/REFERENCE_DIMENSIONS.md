# Read-only reference dimensions

This current-source first slice measures geometry without adding a solver relation.
It is not a statement of packaged or GUI qualification.

Select one authored entity in the general sketch editor and use its inspector:

- **Length (REF)** for a line's endpoint-to-endpoint length.
- **Radius (REF)** or **Diameter (REF)** for a circle or circular arc.
  Arc diameter measures its supporting circle, not the curved arc length.

Each label visibly includes **(REF)** and **Read-only reference**. Measurements
come from the current display geometry. A validated current solution supplies the
solved measurement; an unverified authored draft instead shows **~** and
**unsolved estimate**. The label stores no value, expression or native evidence.
Do not treat an estimate as a checked dimension.

Double-clicking a reference explains the read-only role; it never opens the
numeric input field. To control geometry, use Dimension for length/radius or
Set diameter for diameter. Driving constraints remain separate. Drag a reference
label to move its annotation without changing geometry.

## Correction and persistence

Use **Remove Reference**, the X on the inspector entry, to remove only that label.
This first slice follows existing annotation-placement behavior: local sketch
Undo/Redo edits geometry, not label placement. It has no new interleaved UI undo
history. Committed scene Undo/Redo restores annotation metadata with the scene.

References retain the exact authored entity ID and kind. Deleted or changed-kind
targets show an unavailable binding, with no old measured value displayed and no
nearest-geometry substitution. Geometry Undo can revive the measurement only by
restoring that same identity. An unavailable reference can also be removed.

Finish publishes reference placement in the existing scene annotation store,
separately from canonical Part identity. Save **.blend** preserves accepted labels
and suspended draft metadata; restoring a draft does not restore solver evidence.
Portable **.mcad.json** contains the design, not these scene-only annotations.
Old annotations and drafts without reference labels keep their existing form.

## Deliberate limits

The first set is line length and circle/arc radius/diameter. There is no separate
point-to-point reference distance, reference angle, arc length, reference formula,
or driving/reference conversion. Labels do not add solver constraints and do not
change manufacturing geometry. Existing selection and annotation-overlap limits
still apply; separate overlapping labels before trying to activate one.
