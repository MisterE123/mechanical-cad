# Contributing and verification

Keep the canonical model, CAD kernel and Blender UI separated. Prefer a small
feature with exact analytic/geometry checks over a broad UI that silently falls
back to mesh modelling. Every operation needs failure tests and replay/edit tests.

Run `.venv/bin/python -m ruff check .` and `.venv/bin/python -m pytest -q`.
Run `BLENDER=/path/to/blender scripts/run_checks.sh` for real Blender background
integration. Add `MCAD_BPY_PYTHON=/path/to/bpy-venv/bin/python` to test the standalone
LTS Python API separately. GUI review is still required for visual changes and
modal dialogs; successful headless tests do not prove usability.

- Add stable regression IDs under `docs/regressions/catalog.json` for naming and
  identity edge cases. Planned cases must not be reported as passing.
- New serialized fields/feature types need a documented schema migration policy.
- Never persist OCCT handles, pickles, Blender mesh indices or heuristic matches as
  authoritative design intent.
- Geometry similarity may suggest a reference correction. Explicit user acceptance
  must remain visible; ambiguity is not permission to choose the closest face.
- Keep source Git commits coherent. The application does not auto-commit users'
  models or repositories. Never publish the repository without permission.
- Document binding licenses and platform testing before bundling dependencies.

The local CI definition covers core tests on Python 3.11/3.12/3.13 when published;
it has not run on GitHub because this repository has not been published.

When invoking native Blender directly for tests, always pass `--python-exit-code 1`
and verify the printed JSON success marker. Blender otherwise can return exit 0
even when a Python test raises an exception.
