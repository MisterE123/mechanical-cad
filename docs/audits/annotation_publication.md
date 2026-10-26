# Annotation publication: bounded independent verification

Date: 2026-10-16. Exact source:
`46226ed4175d5caa1ad069eff72ad347242c3feb`.
Runtime: native Blender 5.2.2 LTS (`d13f752e3b9c`), Linux x86_64, pinned
CPython sidecar. All 798 archived source files were checked against Git blobs.

No defect was found in the reviewed scene-only layout/publication seam. The
independent run passed 2,899 pytest tests and 19,597 subtests, including 99 store
cases; Ruff passed. Repository native gates passed annotation publication 38 plus
four separate-process reopen checks and the existing Part publication 131 checks.
A separate adversarial probe passed 59 native and nine fresh-process assertions.

The independent probes checked exact canonical bytes, command history, native
requests and source hashes. Moving a label left a real downstream disk's complete
replay result unchanged, including topology, mesh and volume. Missing/changed
bindings were retained, and unrelated Parts/features kept their placement data.

Late whitespace, equivalent-JSON and empty-layout changes all rejected exact-old
publication without overwriting external bytes. Pre-write, partial-write,
wrong-post-write, canonical-mutation and owner-mutation failures restored every
scene field and original display identity without leaked candidates or unrelated
object/mesh changes. A compound diameter 30→40 update observed new solid, canonical
Part and layout at the failing boundary, then restored all three exactly.

Actual native Undo/Redo and independent `.blend` reopening retained accepted
layout and suspended draft separately. Resume restored unfinished placement while
requiring fresh evidence; explicit discard followed by a new edit restored the
last accepted placement. Legacy callers without layout arguments preserved their
prior behavior.

## Reproduce maintained gates

Check out the exact commit above, prepare the pinned environment, and set `BLENDER`
to native 5.2.2:

```sh
export MCAD_ROOT="$PWD" MCAD_PYTHON="$PWD/.venv/bin/python"
"$MCAD_PYTHON" -m pytest -q
"$MCAD_PYTHON" -m ruff check .
"$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python tests/blender_sketch_annotation_smoke.py
"$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python tests/blender_part_publication_smoke.py
```

This is an immutable-source, native-headless boundary result. It does not qualify
GUI label usability, installed ZIPs, later changes, other platforms, arbitrary
workplanes, or every possible native crash. Standalone CAD JSON intentionally
excludes scene-only placement metadata.
