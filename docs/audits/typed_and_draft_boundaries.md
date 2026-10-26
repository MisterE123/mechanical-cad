# Typed results and general draft audit receipt

Date: 2026-10-16. These are bounded code/numerical reviews, not native GUI acceptance or a released general sketch workflow.

## Typed Part / assembly result boundary

Frozen source: `1f0e48a5a2002d9479e06293e5013292f2054f57`.
All 743 tracked files in the independent extraction matched Git. The sorted path/NUL/SHA-256 manifest digest was `9d23279a5a62d7224ac33596cbd98e3fb23d2dfd7521cb419932ab62be3ee68a`.

The complete development suite passed 2,188 tests. Independent review then passed 232 checks, separately from that suite:

- 165 native/canonical/version/fingerprint/import and targeted stale-source checks.
- All 14 previously accepted malformed/contradictory response cases now reject: unavailable/failed profile ports, malformed nested checks, signatures, topology, mesh face IDs, contradictory source summaries, and nonexistent authored curve/tool-face lineage.
- Valid reordered embedded sketch constraints roundtrip through assembly canonicalization.
- A shared-container direct-Python DAG rejects under bounded preflight rather than expanding recursively.
- 44 additional export, native failure, cut and multi-cut checks. Real STL binary32 precision rejection preserved the existing destination. A failed STEP write retained valid partial check evidence and claimed no completed export.
- Seven legacy Part/assembly responses were byte-identical to the pre-fix version.

Assembly summaries intentionally omit intermediate face payloads: they validate authored roles and ancestry domains, while full Part replay additionally validates exact base/tool face membership. The native kernel remains the geometry authority. Rehashing a response is not a substitute for its semantic validation.

Committed regression entry points:

```
.venv/bin/pytest -q tests/integration/test_part_result_v2.py \
  tests/integration/test_assembly_result_v2.py \
  tests/unit/test_assembly_v2_geometry_evidence.py \
  tests/unit/test_geometry_evidence.py
```

## General command journal and saved draft

Frozen repair source: `ea487197f7555ad483933351f4683a7867ddce6e`.
The four reviewed module hashes matched that exact commit. Independent retest passed 184 tests, including 24 external adversarial/sequence tests, all general/native draft tests, and 57 legacy rectangle tests. No remaining concrete defect was found in this bounded review.

Two findings were fixed before UI integration:

1. Pruned history could accept a forged retained add that reused an identity allocated/deleted before its anchor. Journal v2 carries allocation watermarks and verifies allocator transitions, including imported IDs and abandoned branches.
2. A maximum accepted counter could overflow on the next edit, creating unsaveable live state. Counter successors now reject before mutation, preserving raw text, history, accepted intent and evidence.

Independent mixed command/Undo/Redo/prune/save/restore sequences exercised 2,160 operations. Old unreleased general journal-v1 payloads explicitly reject with original bytes retained; rectangle-v1 codec behavior is unchanged. No automatic migration is claimed.

Committed regression entry points:

```
.venv/bin/pytest -q tests/unit/test_general_sketch_draft.py \
  tests/unit/test_general_draft_store.py \
  tests/integration/test_general_sketch_draft_native.py \
  tests/unit/test_draft_store.py tests/unit/test_sketch_draft.py
```

These audits do not qualify the later shared Blender owner refactor, native text editor, or general line/circle viewport authoring. Each requires its own evidence.
