# ADR 0009: Explicit per-projection source ports

Status: accepted for the bounded multi-source projection contract.

## Decision

A projection row may carry `input`, naming its exact feature input port. Omission
still means `external`; existing documents are not rewritten. Additional ports
are `external_2`, `external_3`, and so on. Each used port maps to one explicit
source feature in `feature.inputs`. Every projection port must be used and each
port has one homogeneous source kind (drawn sketch or solid). Different ports
may have different kinds. Extended records require distinct, earlier source
features; normal DAG/type checks also apply. Legacy rows retain their existing
schema and dependency-order meaning.

Source identity is `(input port, bound source feature, source entity identity)`,
not a flattened face-label namespace. A transformed solid can legitimately carry
the same semantic face IDs as another solid. Both full replay and solve-only
responses therefore key solid projection edge evidence by port for extended
records. Legacy evidence remains the original flat list. Independent Blender
validation verifies each group against its exact bound source.

Managed target IDs, source rows, formulas, support, and user constraints retain
their existing meanings. Managed points cannot be shared across projections.
Replacement changes the selected source entity within its bound port only; it
cannot change the port or source feature. No proximity matching is introduced.

## Authoring and repair

The sketch owner allocates stable ports and retains its allocation ledger across
Undo/Redo, reference deletion, and Resume. Only used ports enter the canonical
candidate. Project Geometry selects explicit earlier sketches. Use Solid Edge selects an
explicit earlier solid within the live sketch and temporarily displays its exact
owned input body. It never changes canonical active output or accepted runtime;
source-qualified native evidence still authorizes every pick. See
[the workflow and limits](../MULTI_SOURCE_PROJECTION.md).

Sequential proposal repair remains atomic at publication. Its validation-only
minimal probe removes omitted references and their unused projection ports, but
retains the selected port and support. The real candidate is never pruned. A
repair cannot publish unless the complete real candidate replays successfully.

## Consequences

This is an additive extension within document versions 2 and 3. Older readers
that do not implement the optional row field reject it rather than silently
binding it to `external`. The sidecar and add-on contracts must be updated
together. No new kernel, nearest-geometry heuristic, or document migration is
required. Simultaneous picking from arbitrary hidden solid bodies is not added.

## Bounded analytic evidence check

Native cylinder face signatures now optionally include `axis_origin`, the exact
OCCT axis location, not the trimmed face centroid. When present, independent edge
validation checks cylinder incidence, radius and axis orientation against the
bound source's own face rows. Plane incidence uses the source plane; line
endpoints also check their incident face signatures. Reversed normals are valid.
Older transcripts without the optional field remain readable, and nonanalytic
surfaces retain their existing native trust boundary. This is not independent
reconstruction of every OCCT surface or protection against a wholly forged
trusted-native response. It rejects a coordinated wrong-source target response
when genuine analytic source rows remain unchanged.

The field is diagnostic replay evidence only: canonical document hashes and
saved feature/entity/face references do not include it. Semantic face IDs derive
from feature/role identity, and unresolved snapshot handles remain index-local;
no ID generation uses the new axis field.
