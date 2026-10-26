# Windows gear geometry development

This is a historical, focused source-development report, not a Windows release qualification.

The geometry implementation uses cubic Hermite involute spans, analytic tip/root arcs and existing below-base transitions. Pitch-circle anchors are exact span endpoints. See [SPUR_GEARS.md](SPUR_GEARS.md) for the error bound and limitations. No trochoidal root, generated fillet or strength assessment is claimed. Canonical gear parameters, phases, ratios and conservative complexity limits remain unchanged.

The Windows export correction reopens only its own completed temporary file in read/write mode before flushing. Native geometry validation and atomic replacement remain active. Existing destinations survive failed writes.

Historical focused results: 82 gear tests passed with 11 skips, 68 export/action regressions passed with 3 skips, and 24 sampled mesh poses showed no common volume. These are bounded samples, not continuous collision proof. Background Blender registration passed; this did not qualify real GUI creation. Full Windows collection encountered a Linux-only fcntl import.

Reproduce relevant checks from the source checkout:

```powershell
python -m pytest -q tests/unit/test_spur_gear_curves.py tests/unit/test_gear_pair.py tests/integration/test_spur_gear.py tests/integration/test_gear_pair_mesh.py tests/integration/test_gear_windows_sidecar.py
python -m ruff check .
blender --background --factory-startup --python-exit-code 1 --python tests/blender_gear_windows_boundary.py
```

Guarded Windows runtime admission requires native package/cache identity, cancellation, cleanup, installed-package and GUI verification. A headless success does not establish general platform parity.
