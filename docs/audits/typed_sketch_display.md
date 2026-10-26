# Typed sketch display and Part publication audit receipt

Date: 2026-10-16. Exact repaired source:
`7a3e7d5c4336a52641359dd6bd83522299667536`.

The independent review found no remaining blocker in its bounded native-headless
Part display/publication scope. It does not qualify the later general viewport
editor, installed package, interactive Undo/Redo or other operating systems.
Runtime: native Blender 5.2.2 LTS, build `d13f752e3b9c`, Linux x86_64.

## Independently repeated evidence

- 111 supplied display pytest tests.
- 198 native checks and 18 checks in a separate `.blend` reopen process.
- 170 additional precision, units, ownership, stale binding, shape availability,
  rollback phase, unrelated-data and cleanup assertions.
- 46 focused assertions across eight recovery variants.

The tests cover open line display and save/reopen, same-ID closure/extrusion,
active-open geometry/export rejection with existing destination preservation,
arbitrary workplanes and scene scales, shared-scene object ownership, immutable
unit preferences and exact canonical/display restoration. No OCP or slvs import
occurs inside Blender. Display precision is tolerance-bounded, not exact float32
positioning or manufacturing certification.

## Findings closed

1. Changing the owner field after publication could leave both the accepted wire
   and rejected candidate visible after canonical rollback.
2. Replacing the current last-good mesh pointer during failure could delete an
   unrelated mesh and leak the actual candidate cache.
3. Incomplete first-publication cleanup could leave a rejected solid visible and
   renderable after restoring the original empty document/owner.

Publication now records exact created object, display-mesh and cache identities
in a scoped acquisition ledger. Rollback removes only those resources, restores
old links/state independently and hides any rejected objects that could not be
removed. Mutable owner tags and current cache pointers grant no deletion
permission. Tests include initially empty and existing Parts, another Part's
cache, a newly created unrelated object, and cleanup refusal for wire and solid.

## Reproduce

Set `MCAD_ROOT` to the frozen source and `MCAD_PYTHON` to the configured sidecar
interpreter, then run the native gate with failure exit codes enabled:

```
blender --background --factory-startup --python-exit-code 1 \
  --python tests/blender_typed_sketch_display_smoke.py
```

The script launches its separate reopen process. Preserve logs in a persistent
workspace directory. The independent review's additional probes are supplemental
engineering evidence, not a replacement for the tracked regression suite.
