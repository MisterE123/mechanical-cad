"""Saved-model contract plus fresh subprocess native geometry regression."""

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from mechanical_cad.model import Document

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "examples/imported_mounting_adapter/imported_mounting_adapter.mcad.json"


def test_saved_adapter_has_separate_unlinked_branches():
    doc = Document.from_json(MODEL.read_text())
    data = doc.to_dict()
    assert data["active_feature"] == "bore_5"
    assert len(data["features"]) == 18
    assert data["features"][0]["kind"] == "import_step"
    assert data["features"][0]["step_data"]["encoding"] == "base64"
    for feature in data["features"][1:]:
        assert "imported_base" not in feature["inputs"].values()
        assert "support_face" not in feature and "support_intent" not in feature
        assert not feature.get("projections")
        if feature["kind"] == "sketch_constrained":
            assert not feature["inputs"]
    planes = [f["sketch"]["plane"] for f in data["features"] if "sketch" in f]
    assert len(planes) == 6 and all(p == planes[0] for p in planes)
    assert Document.from_json(doc.to_json()).to_dict() == data


@pytest.mark.kernel
def test_fresh_native_adapter_replay_and_export(tmp_path):
    pytest.importorskip("OCP")
    pytest.importorskip("slvs")
    output = tmp_path / "evidence"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/generate_imported_adapter.py"), str(output)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "IMPORTED_ADAPTER_VERIFIED" in completed.stdout
    report = json.loads((output / "verification.json").read_text())
    assert math.isclose(report["separation_mm"], 2, abs_tol=1e-6)
    assert report["cylindrical_bores"] == 5
    assert report["source_replaced_adapter_unchanged"]
    assert report["invalid_export_wrote_no_file"]
    # A second independent process loads the checked-in self-contained model,
    # not the source STEP file or any display cache.
    check = subprocess.run(
        [sys.executable, "-c", "from pathlib import Path; "
         "from mechanical_cad.model import Document; "
         "from mechanical_cad.actions import run_geometry_action; "
         f"d=Document.from_json(Path({str(MODEL)!r}).read_text()); "
         "r=run_geometry_action(d, 'check_geometry', result_version=3); "
         "assert r['ok'], r.get('error'); print('SAVED_ADAPTER_REPLAY_OK')"],
        cwd=ROOT, capture_output=True, text=True, timeout=120, check=False,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    assert "SAVED_ADAPTER_REPLAY_OK" in check.stdout
