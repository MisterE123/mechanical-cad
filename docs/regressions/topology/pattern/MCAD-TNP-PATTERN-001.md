# MCAD-TNP-PATTERN-001: Authored hole-pattern occurrence surfaces

## User-visible intention

A Linear/Circular Hole Pattern can own a wall or blind-hole floor from a numbered
placement of its cutting tool. “Hole copy 2 from tool / side.circle” means the
second authored placement of that source face, not the closest physical hole.
Copy 1 is the original tool. Edit Feature changes the construction: radius,
height, pitch, axis and sweep edits follow that placement. Changing circular
Count redistributes placements over the saved total sweep, so the same copy may
move. Removing a referenced copy fails the downstream reference, never selects
a remaining hole. Correct Count/placement or explicitly replace the reference.

The existing saved pattern feature defines ordered placements; a downstream
saved face ID encodes the zero-based occurrence and SHA-256 of the complete
source semantic face ID. The digest bounds nested names and hashes identity,
not geometry. No document schema change or enumeration-based face identity is
introduced. Deliberately replacing the tool requires a new source reference.

## Exact bounded proof

Typed result v2/v3 only. Each source face is mapped by native rigid-copy Modified
history. Composed sequential Cut history must have exactly one Modified or
unchanged output, no Generated output claiming it, no competing source (including
unknown sources), and no inherited base claim. The source itself must be stable.
Incomplete transform ancestry refuses the occurrence. Native Common volume
above 1e-12 mm³ marks both intersecting cutter placements unavailable. This is a
conservative exclusion even when the overlap lies outside the plate. Multiple
images, deleted/no-op placements and intersecting cavities stay snapshot-only.
There is no collective merged-cavity naming rule in this slice.

Provenance records `pattern_tool_face`, `source_id`, `occurrence`, `source_count=1`
and `image_count=1`. Native-free validation checks closed fields, role hash,
integer occurrence, actual resolved Count and stable tool-output membership.
Subsequent ordinary modifiers can retain these identities under the existing
one-image rules. Actual planarity/adjacency still gates sketches/projections.

Legacy omitted/explicit result v1 retains snapshot-only new pattern surfaces.
Whole-solid fused linear/circular patterns remain snapshot-only. This does not
solve arbitrary face naming, imported geometry, collective overlapping holes,
or physical-hole tracking across arbitrary construction changes.

## Executable evidence

`tests/integration/test_pattern_face_intent.py` covers both pattern families,
typed v2/v3, through-hole circular references, selected blends, blind floors and
attached face sketches, size/pitch/count/sweep edits, disk save/replay, removed
and no-op occurrences, real split walls and overlap, forged native-free metadata,
nonunique/unknown/native Generated claims, labels and legacy v1.
`test_cut_patterns.py` retains exact volume, connected-solid and manufacturing
checks. These are native kernel/client tests, not installed GUI qualification.
