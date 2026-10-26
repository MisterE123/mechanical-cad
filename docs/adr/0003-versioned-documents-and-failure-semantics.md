# ADR 0003: Versioned JSON, snapshot edits and complete replay

Status: accepted for the experimental 0.1 slice, 2026-10-16.

Persist schema-v1 JSON rather than Python object serialization. Reject unknown
schema versions and fields rather than silently discarding data. Copy/freeze
snapshot mappings, and produce a new document when parameters/features change.
Atomic save uses a same-directory temporary file, flush/fsync and replace.

Replay the complete feature DAG initially. Cache invalidation is a future measured
optimization, not an untested source of stale shapes. Invalid features get an
explicit diagnostic and dependent nodes become blocked. Independent branches
continue, but any failed branch makes the document unsuitable for export.

Only one solid is supported per solid feature in this slice. Zero/multiple solids
are reported rather than silently discarding geometry or choosing a body. Negative
extrusion directions, multiple bodies, feature suppression/rollback controls and
schema migration are later work, even if the low-level kernel can express them.


## Separate unapplied repair intent

The Blender scene may persist a separately versioned, bounded repair-intent
checkpoint, outside accepted canonical Part JSON. It contains exact accepted-base
identity, candidate/partial-repair history and annotation intent only. Loading
never executes, replays or publishes it. Explicit Resume freshly validates the
unchanged base and every retained transition under one current backend/context;
only then does it recreate transient ownership. Interactive Resume uses sequential
guarded modal jobs with explicit Cancel, a separate between-job input reservation,
and no geometry publication or canonical Undo step. Unknown/corrupt/stale intent
remains untouched for Save or explicit Discard, with no implicit migration.
JSON/geometry exports remain accepted-only. See STAGED_EDIT_REPAIR.md for bounds,
save failure handling and native verification.

## Explicit ordered Loft sections (development)

An opt-in version-1 `loft_sections` record declares 2–16 ordered profile ports.
All ports are ordinary typed DAG dependencies, with distinct profile feature IDs;
legacy start/end fields cannot coexist. Omitted intent preserves old serialization
and the legacy two-profile entrypoint, with no migration. Client and core validators
agree on the bounded record. Traversal is authored order, never spatial sorting.
Native construction must remain one valid solid with measurable positive volume;
no new persistent face identities are asserted. See [MULTI_SECTION_LOFT](../MULTI_SECTION_LOFT.md).
