"""Real Windows CPython child boundary for printable gear replay and exports.

This does not open the guarded Blender runtime admission path.
"""

import json
import os
import subprocess
import sys

import pytest

pytestmark = [
    pytest.mark.kernel,
    pytest.mark.skipif(sys.platform != "win32", reason="Windows child boundary"),
]


def request(document, action="replay", **options):
    payload = dict(
        protocol_version=1, result_version=2, action=action, document=document, **options
    )
    result = subprocess.run(
        [sys.executable, "-m", "mechanical_cad.sidecar"],
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
        env={**os.environ, "PYTHONNOUSERSITE": "1", "PYTHONIOENCODING": "utf-8"},
    )
    # Exactly one JSON value on stdout even when OCCT's STEP writer emits logs.
    response = json.loads(result.stdout)
    assert result.returncode == (0 if response["ok"] else 1), (
        response,
        result.stderr.decode("utf-8", errors="replace"),
    )
    return response


def test_real_windows_sidecar_gear_only_exports_and_invalid_edit(tmp_path):
    document = dict(
        schema_version=1,
        id="windows_gear",
        name="Printable gear only",
        units="mm",
        parameters={"reduction": 0.1},
        active_feature="gear",
        features=[
            dict(
                id="gear",
                kind="spur_gear",
                params=dict(
                    module=2,
                    tooth_count=20,
                    thickness=8,
                    bore_diameter=5,
                    backlash="reduction",
                ),
            )
        ],
    )
    replay = request(document)
    assert replay["ok"] and replay["result"]["status"] == "ok"
    before = replay["result"]["features"][0]["stats"]["volume"]
    document["parameters"]["reduction"] = 0.2
    edited = request(document)
    assert edited["ok"] and edited["result"]["features"][0]["stats"]["volume"] < before
    directory = tmp_path / "gear exports ü"
    directory.mkdir()
    for action, suffix in (("export_stl", ".stl"), ("export_step", ".step")):
        destination = directory / ("gear_a" + suffix)
        result = request(document, action, destination=str(destination))
        assert result["ok"], result
        assert destination.stat().st_size > 100
    document["features"][0]["params"]["tooth_count"] = 17
    destination = directory / "invalid.stl"
    response = request(document, "export_stl", destination=str(destination))
    assert not response["ok"] and not destination.exists()
