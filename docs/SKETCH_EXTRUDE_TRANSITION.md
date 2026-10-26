# Selected-sketch extrusion handoff

The Feature History shortcut opts into opening Part after successful extrusion
from Sketch. It uses the existing workspace request and focus callback only after
the normal atomic publication and preview-owner cleanup. Cancel and failed Apply
do not request navigation. Ordinary Extrude remains opt-out. The hidden flag is
not saved or inherited from remembered dialog settings; invocation captures the
original window, workspace and scene. Navigation does not replace canonical
output, own Undo, or alter draft/publication failure behavior. A rejected workspace
request reports that extrusion succeeded and asks the user to open Part.

## Bounded source verification, 2026-10-24

- 27 focused tests in `tests/unit/test_saved_sketch_extrude.py`: existing readiness
  and prefill behavior, opt-in wiring, original-context guard, synchronous success
  versus failed FINISHED semantics, accepted modal publication, navigation errors,
  and remembered flag reset.
- Native Blender 5.2.2 with isolated native Python sidecar:
  `blender_saved_sketch_extrude_smoke.py` and
  `blender_sketch_extrude_transition_smoke.py` passed explicit markers. The latter
  checks cancel during work, real zero-depth rejection with unchanged canonical
  text/workspace, then successful publication before a recorded Part request.
  No OCP import is permitted inside Blender.
- Source-loaded cloud GUI: selected-sketch dialog Cancel kept the original Sketch
  and one-feature document; 10 mm Apply opened Part with the solid focused,
  two features and volume 12000 mm³. Returning to Sketch and attempting zero depth
  displayed an error, stayed in Sketch and retained the two-feature accepted solid.
- The first GUI launch crashed in the Gallium/TBB rendering stack. Relaunching with
  `LP_NUM_THREADS=1` completed these observations. This is not platform or renderer
  qualification, an installed-archive check, exhaustive Undo/Redo coverage, or a
  full historical-suite run. Frozen packages are unchanged.
