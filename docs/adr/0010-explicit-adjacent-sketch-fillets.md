# ADR 0010: explicit adjacent sketch-fillet lineage

Status: unreleased source implementation; bounded native geometry verified, interactive qualification pending.

## Decision

Retain the original intersection points as dimensionable witnesses, the original
line IDs as supporting-line identities, and explicit arc start/end tangent roles.
Do not infer relationships from coincident coordinates, labels, or endpoint order.
Isolated fillets retain unchanged version-1 metadata and the original journal
opcode. An adjacent operation upgrades only its directly affected arc intents to
version 2 in the same atomic command that authors the new arc.

Version 2 adds two ordered nullable `neighbors` arc IDs aligned with `lines` and
`outer`. Original outer witness IDs remain unchanged. A declared neighbor must
reciprocate the exact line role, swap corner/outer witness IDs, and own the other
finite endpoint through its corresponding arc start/end. Supporting lines have
exactly the declared one or two owners. V2 tangent endpoints cannot be shared by
unrelated lines or arcs. Four-corner cycles are legitimate: validation checks local
reciprocity, without recursion or treating those relationships as feature-DAG edges.

Required radius, two tangency and two witness-on-infinite-line relations remain
ordinary explicit constraints. No existing relation is silently deleted. Selected
line relations other than H/V or the exact declared peer's required relations
remain unsupported. Existing shared/coincident/projected-corner refusals remain.
Deleting a linked arc fails closed if it would leave a dangling peer; no automatic
unlink/reconnection or general fillet-chain deletion is introduced.

## Numeric and transactional boundaries

Independent core and add-on validators retain individual interior witness-span
bounds and the original directed minor branch. For each shared line they also
project the ordered difference between its two tangents onto the original witness
span and require at least 1e-6 mm separation. Individual interior bounds alone do
not prevent overlapping adjacent radii. The checks apply to solve, consumed replay
and fresh export, not only interactive creation.

The new `adjacent_corner_fillet` journal-3 command records complete before/after
peer-intent replacements plus the complete allocated construction and support
seeds. Replay strictly parses metadata, recomputes the construction and compares
all records before mutation. Undo restores the exact old metadata, including
version 1; Redo restores the same IDs. Preview/Cancel never allocate or upgrade.
Recovery and save/reopen retain raw intent only, never native solve authority.

Unknown fields, malformed present metadata and unknown versions fail closed.
Absent metadata remains legacy geometry. Old readers reject version 2 and the
new opcode rather than silently dropping constraints or design intent. No schema
or release-number bump, migration of unrelated arcs, topology heuristic, solver
backend or native-in-Blender dependency is added by this decision.

## Verification

Focused contracts and geometry tests are in
`tests/integration/test_sketch_corner_fillet.py`; lifecycle harnesses are in
`tests/blender_sketch_adjacent_fillet_smoke.py` and
`tests/blender_sketch_adjacent_fillet_reopen.py`. Current observed scope and
pending qualification are recorded in `docs/SKETCH_CORNER_FILLET.md`.
