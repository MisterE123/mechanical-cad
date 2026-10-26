"""Actual-process admission, native controls, and exact legacy wire preservation."""

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "mcad.backend-contract/1"
GUARD = "mcad.solver-dof-cycle-guard/1"
NONCE = "abcdef0123456789abcdef0123456789"
MAX_OLD = 2 * 1024 * 1024
ACTIONS = (
    "replay",
    "canonical_snapshot",
    "solve_sketch",
    "check_geometry",
    "export_step",
    "export_stl",
    "assembly_replay",
    "assembly_check",
    "assembly_sample",
)


def legacy_sidecar_source():
    """Load the exact pre-contract source, including from a Git-free archive."""
    source = (ROOT / "tests/fixtures/backend_capability/sidecar-b965df1.py.txt").read_bytes()
    assert hashlib.sha256(source).hexdigest() == (
        "026d6194c68cc6340482a624a84772d1ac514bd1217b81409631e2b3a0be0dfe"
    ), (
        "The preserved b965df1 sidecar fixture changed; see fixtures/backend_capability/provenance.json"
    )
    return source.decode("utf-8")


def document(name="drilled_plate"):
    return json.loads((ROOT / f"examples/{name}.mcad.json").read_text())


def operation(action="canonical_snapshot", destination=None):
    request = {"protocol_version": 1, "action": action, "document": document()}
    if action != "canonical_snapshot":
        request["result_version"] = 2
    if action == "solve_sketch":
        request.update(document=document("open_line_sketch"), feature_id="profile")
    if action.startswith("assembly_"):
        request.pop("document")
        request.update(
            kind="assembly",
            assembly_protocol_version=1,
            assembly=json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text()),
            coordinates={"slide_a": 100, "slide_b": 200},
            requirements=[],
        )
        if action == "assembly_sample":
            request["samples"] = {"joint_id": "slide_a", "values": [100, 120]}
    if action.startswith("export_"):
        request["destination"] = str(destination)
    return request


def guard(request, extra=()):
    names = [BASELINE] if request.get("action") == "canonical_snapshot" else [BASELINE, GUARD]
    return {
        **copy.deepcopy(request),
        "backend_contract": {
            "version": 1,
            "request_id": NONCE,
            "required_capabilities": sorted([*names, *extra]),
        },
    }


def digest(request):
    return hashlib.sha256(
        json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def run(request=None, *, raw=None, root=ROOT, no_site=False, script=None):
    command = [sys.executable, "-B"]
    if no_site:
        command.append("-S")
    command.extend(["-c", script] if script else ["-m", "mechanical_cad.sidecar"])
    env = dict(os.environ, PYTHONPATH=str(root / "src"), PYTHONNOUSERSITE="1")
    env.pop("PYTHONHOME", None)
    result = subprocess.run(
        command,
        input=json.dumps(request).encode() if raw is None else raw.encode(),
        capture_output=True,
        timeout=60,
        cwd=root,
        env=env,
        check=False,
    )
    return result, json.loads(result.stdout)


SNAPSHOT_GUARD = """
import builtins, importlib.abc, runpy, sys
blocked = {"OCP", "slvs", "bpy", "cadquery", "engine", "actions", "kernel_ocp",
           "sketch_solver", "profile_region", "sketch_evaluation", "assembly_service"}
original = builtins.__import__
def checked(name, *args, **kwargs):
    if any(piece in blocked for piece in name.split(".")):
        raise AssertionError("forbidden snapshot import: " + name)
    return original(name, *args, **kwargs)
class Blocked(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if any(piece in blocked for piece in fullname.split(".")):
            raise AssertionError("forbidden snapshot dynamic import: " + fullname)
builtins.__import__ = checked
sys.meta_path.insert(0, Blocked())
runpy.run_module("mechanical_cad.sidecar", run_name="__main__")
"""


@pytest.mark.parametrize("name", ["drilled_plate", "open_line_sketch", "viewport_rectangle"])
def test_guarded_snapshot_real_minus_s_blocks_every_solver_engine_profile_native_import(name):
    ordinary = operation()
    ordinary["document"] = document(name)
    request = guard(ordinary)
    result, response = run(request, no_site=True, script=SNAPSHOT_GUARD)
    assert result.returncode == 0, (response, result.stderr)
    receipt = response.pop("backend_receipt")
    legacy_process, legacy = run(ordinary, no_site=True, script=SNAPSHOT_GUARD)
    assert legacy_process.returncode == 0 and response == legacy
    assert response["input_fingerprint"] == digest(ordinary)
    assert receipt["request_fingerprint"] == digest(request)
    assert receipt["phase"] == "dispatched" and receipt["backend"]["solver_origin"] is None
    assert receipt["confirmed_capabilities"] == [BASELINE] and receipt["missing_capabilities"] == []
    assert receipt["backend"]["project_root"] == str(ROOT)
    assert receipt["backend"]["python_executable"] == os.path.abspath(sys.executable)
    assert receipt["backend"]["python_executable_target"] == str(Path(sys.executable).resolve())


def test_snapshot_solver_requirement_is_rejected_without_even_importing_adapter():
    request = guard(operation(), extra=(GUARD,))
    result, response = run(request, no_site=True, script=SNAPSHOT_GUARD)
    assert result.returncode == 1
    assert response["error"]["code"] == "backend_capability_missing"
    assert response["backend_receipt"]["phase"] == "rejected_before_dispatch"
    assert response["backend_receipt"]["backend"]["solver_origin"] is None


@pytest.mark.parametrize("action", ACTIONS)
def test_actual_process_rejects_each_action_before_model_parser_or_dispatch(action, tmp_path):
    destination = tmp_path / "previous.step"
    destination.write_bytes(b"unchanged")
    request = guard(operation(action, destination), extra=("unimplemented/1",))
    script = """
import runpy
from mechanical_cad.model import Document
def forbidden(*args, **kwargs):
    raise AssertionError("ordinary model parser was entered")
Document.from_dict = forbidden
runpy.run_module("mechanical_cad.sidecar", run_name="__main__")
"""
    result, response = run(request, no_site=True, script=script)
    assert result.returncode == 1
    assert response["error"]["code"] == "backend_capability_missing"
    assert response["backend_receipt"]["phase"] == "rejected_before_dispatch"
    assert "result_version" not in response
    assert destination.read_bytes() == b"unchanged" and list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("adapter", ["missing", "old_marker", "broken_import"])
def test_real_copied_missing_old_or_broken_adapter_never_borrows_new_sidecar_marker(
    tmp_path, adapter
):
    selected = tmp_path / "selected"
    shutil.copytree(
        ROOT / "src/mechanical_cad",
        selected / "src/mechanical_cad",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    solver = selected / "src/mechanical_cad/sketch_solver.py"
    if adapter == "missing":
        solver.unlink()
    elif adapter == "old_marker":
        text = solver.read_text()
        text = text.replace(
            'BACKEND_CAPABILITIES = frozenset({"mcad.solver-dof-cycle-guard/1"})', ""
        )
        solver.write_text(text)
    else:
        solver.write_text('raise ImportError("broken optional adapter installation")\n')
    result, response = run(guard(operation("replay")), root=selected, no_site=True)
    assert result.returncode == 1
    assert response["error"]["code"] == "backend_capability_missing"
    receipt = response["backend_receipt"]
    assert receipt["missing_capabilities"] == [GUARD]
    assert receipt["backend"]["core_origin"] == str(selected / "src/mechanical_cad")
    assert receipt["backend"]["solver_origin"] == (str(solver) if adapter == "old_marker" else None)
    assert receipt["phase"] == "rejected_before_dispatch"


@pytest.mark.kernel
@pytest.mark.parametrize("action", ACTIONS)
def test_genuine_guarded_action_success_retains_exact_ordinary_envelope(action, tmp_path):
    pytest.importorskip("OCP")
    pytest.importorskip("slvs")
    suffix = ".stl" if action == "export_stl" else ".step"
    destination = tmp_path / ("part" + suffix)
    ordinary = operation(action, destination)
    request = guard(ordinary)
    result, response = run(request)
    assert result.returncode == 0 and response["ok"] is True, (response, result.stderr)
    receipt = response.pop("backend_receipt")
    old_process, old_response = run(ordinary)
    assert old_process.returncode == 0, old_process.stderr
    assert response == old_response
    assert response["input_fingerprint"] == digest(ordinary)
    assert receipt["request_fingerprint"] == digest(request)
    assert receipt["phase"] == "dispatched"
    assert receipt["backend"]["solver_origin"] == (
        None
        if action == "canonical_snapshot"
        else str(ROOT / "src/mechanical_cad/sketch_solver.py")
    )
    if action.startswith("export_"):
        assert destination.stat().st_size == response["export"]["bytes"]
        assert list(tmp_path.iterdir()) == [destination]
    else:
        assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("action", ACTIONS)
def test_admitted_ordinary_early_failure_keeps_exact_old_inner_shape(action, tmp_path):
    ordinary = operation(action, tmp_path / "unwritten.step")
    if action.startswith("assembly_"):
        ordinary["assembly"] = None
    else:
        ordinary["document"] = None
    result, response = run(guard(ordinary), no_site=True)
    assert result.returncode == 1 and response["ok"] is False
    receipt = response.pop("backend_receipt")
    _, old_response = run(ordinary, no_site=True)
    assert response == old_response
    assert receipt["phase"] == "dispatched" and receipt["missing_capabilities"] == []
    assert list(tmp_path.iterdir()) == []


def test_admitted_solve_dependency_failure_is_truthful_and_keeps_confirmed_guard():
    ordinary = operation("solve_sketch")
    result, response = run(guard(ordinary), no_site=True)
    assert result.returncode == 1 and response["error"]["code"] == "solver_unavailable"
    assert response["backend_receipt"]["phase"] == "dispatched"
    assert response["backend_receipt"]["confirmed_capabilities"] == [BASELINE, GUARD]
    assert response["result"] is None and response["input_fingerprint"] == digest(ordinary)


def test_genuine_coordinate_cycle_guard_failure_requires_no_native_packages():
    ordinary = operation("solve_sketch")
    sketch = ordinary["document"]["features"][0]["sketch"]
    sketch["points"] = [{"id": name, "u": i * 2, "v": 0} for i, name in enumerate("abc")]
    sketch["lines"] = [
        {"id": f"l{i}", "start": a, "end": b}
        for i, (a, b) in enumerate((("a", "b"), ("b", "c"), ("c", "a")))
    ]
    sketch["constraints"] = [
        {"id": f"h{i}", "kind": "horizontal", "refs": [f"l{i}"], "value": None, "target": None}
        for i in range(3)
    ]
    result, response = run(guard(ordinary), no_site=True)
    assert result.returncode == 1 and response["error"]["code"] == "solver_dof_indeterminate"
    assert response["backend_receipt"]["phase"] == "dispatched"
    assert response["result"] is None and response["input_fingerprint"] == digest(ordinary)


@pytest.mark.parametrize("variant", ["contract_key", "version", "capabilities", "nested_document"])
def test_duplicate_wire_members_never_receive_guarded_receipt(variant):
    raw = json.dumps(guard(operation()))
    if variant == "contract_key":
        raw = raw.replace('"backend_contract":', '"backend_contract": null, "backend_contract":', 1)
    elif variant == "version":
        raw = raw.replace('"version": 1', '"version": 1, "version": 1', 1)
    elif variant == "capabilities":
        raw = raw.replace(
            '"required_capabilities":', '"required_capabilities": [], "required_capabilities":', 1
        )
    else:
        raw = raw.replace('"schema_version": 1', '"schema_version": 2, "schema_version": 1', 1)
    result, response = run(raw=raw, no_site=True)
    assert result.returncode == 1 and response["error"]["code"] == "invalid_json"
    assert "backend_receipt" not in response


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_guarded_nonfinite_wire_numbers_reject_before_receipt(constant):
    raw = json.dumps(guard(operation()))[:-1] + ', "probe": ' + constant + "}"
    result, response = run(raw=raw, no_site=True)
    assert result.returncode == 1 and response["error"]["code"] == "invalid_json"
    assert "backend_receipt" not in response


@pytest.mark.parametrize("length,expected", [(128, "invalid_request"), (129, "resource_limit")])
def test_original_numeric_token_budget_is_not_erased_by_json_detachment(length, expected):
    ordinary = {"protocol_version": 1, "action": "replay", "result_version": 2, "document": None}
    raw = json.dumps(guard(ordinary))[:-1] + ', "probe": 0.' + "0" * (length - 2) + "}"
    _, response = run(raw=raw, no_site=True)
    assert response["error"]["code"] == expected
    assert ("backend_receipt" in response) == (length == 128)
    assert ("result_version" in response) == (length == 128)
    legacy = (
        json.dumps({"protocol_version": 1, "document": None})[:-1]
        + ', "probe": 0.'
        + "0" * (length - 2)
        + "}"
    )
    _, old_response = run(raw=legacy, no_site=True)
    assert old_response["error"]["code"] == "invalid_request"


def test_raw_wire_limits_keep_legacy_2mib_and_allow_only_guarded_4k_overhead():
    legacy = json.dumps(operation())
    result, response = run(raw=legacy + " " * (MAX_OLD - len(legacy)), no_site=True)
    assert result.returncode == 0 and response["ok"] is True
    _, response = run(raw=legacy + " " * (MAX_OLD + 1 - len(legacy)), no_site=True)
    assert response["error"] == {
        "code": "document_too_large",
        "message": "Request exceeds the 2 MiB limit.",
    }
    guarded_raw = json.dumps(guard(operation()))
    result, response = run(
        raw=guarded_raw + " " * (MAX_OLD + 4096 - len(guarded_raw)), no_site=True
    )
    assert result.returncode == 0 and response["backend_receipt"]["phase"] == "dispatched"
    _, response = run(raw=guarded_raw + " " * (MAX_OLD + 4097 - len(guarded_raw)), no_site=True)
    assert response["error"]["code"] == "document_too_large" and "backend_receipt" not in response


@pytest.mark.parametrize("action", ACTIONS)
def test_unguarded_failure_wire_bytes_match_original_sidecar_exactly(action, tmp_path):
    original = legacy_sidecar_source()
    script = (
        "__package__ = 'mechanical_cad'\nexec(compile("
        + repr(original)
        + ", 'legacy_sidecar.py', 'exec'))"
    )
    request = operation(action, tmp_path / "keep.step")
    if action.startswith("assembly_"):
        request["assembly"] = None
    else:
        request["document"] = None
    result, _ = run(request, no_site=True)
    old, _ = run(request, no_site=True, script=script)
    assert result.returncode == old.returncode == 1
    assert result.stdout == old.stdout


def test_unguarded_snapshot_success_wire_bytes_match_original_sidecar_exactly():
    original = legacy_sidecar_source()
    script = (
        "__package__ = 'mechanical_cad'\nexec(compile("
        + repr(original)
        + ", 'legacy_sidecar.py', 'exec'))"
    )
    request = operation()
    result, _ = run(request, no_site=True)
    old, _ = run(request, no_site=True, script=script)
    assert result.returncode == old.returncode == 0
    assert result.stdout == old.stdout


def test_oversized_legacy_v2_wire_error_does_not_acquire_a_version_stamp():
    request = operation("replay")
    raw = json.dumps(request)
    _, response = run(raw=raw + " " * (MAX_OLD + 1 - len(raw)), no_site=True)
    assert response == {
        "protocol_version": 1,
        "ok": False,
        "result": None,
        "error": {"code": "document_too_large", "message": "Request exceeds the 2 MiB limit."},
    }


@pytest.mark.parametrize("kind", [None, "assembly", "wrong"])
def test_cross_family_snapshot_wire_never_imports_assembly_or_solver(kind):
    request = guard(operation())
    request["kind"] = kind
    result, response = run(request, no_site=True, script=SNAPSHOT_GUARD)
    assert result.returncode == 1 and response["error"]["code"] == "backend_contract_invalid"
    assert "backend_receipt" not in response


@pytest.mark.kernel
@pytest.mark.parametrize("action", ["replay", "check_geometry", "export_step", "export_stl"])
def test_dispatched_native_modelling_failure_retains_receipt_and_never_replaces_export(
    action, tmp_path
):
    pytest.importorskip("OCP")
    destination = tmp_path / ("existing.stl" if action == "export_stl" else "existing.step")
    destination.write_bytes(b"previous successful export")
    ordinary = operation(action, destination)
    ordinary["document"]["parameters"]["width"] = -1
    result, response = run(guard(ordinary))
    assert result.returncode == 1 and response["ok"] is False
    receipt = response.pop("backend_receipt")
    _, old_response = run(ordinary)
    assert response == old_response
    assert response["result"]["status"] == "failed"
    assert receipt["phase"] == "dispatched" and receipt["missing_capabilities"] == []
    assert destination.read_bytes() == b"previous successful export"
    assert list(tmp_path.iterdir()) == [destination]


def sector_pre_service_fixtures():
    """Exact captures from the committed, Git-free pre-service source/runtime."""
    directory = ROOT / "tests/fixtures/result_v3/legacy_30383a1"
    raw = (directory / "manifest.json").read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "d75cc45cb7010dfcea4cae6b06ce77bd8e983bc4f474b83d8388b414d390a50d"
    )
    return directory, json.loads(raw)


def sector_pre_service_script(directory, manifest):
    """Restore the dispatch and native signature closure, without eager OCP imports.

    Other leaves remain shared: unchanged golden bytes detect drift in these
    requests, rather than claiming a complete historical Python environment.
    """
    kernel = directory / "kernel_ocp-30383a1.py.txt"
    kernel_sha = "77f3f3033f95cbe72a97dbdab70769f1f0c3d34604f2d2ac036d6e10f78224ac"
    assert hashlib.sha256(kernel.read_bytes()).hexdigest() == kernel_sha
    sources = {}
    for name, entry in manifest["sources"].items():
        raw = (directory / entry["fixture"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        sources[name] = raw.decode("utf-8")
    return (
        "import sys, types, importlib.abc, importlib.util, hashlib\n"
        "from pathlib import Path\n"
        "class HistoricalKernel(importlib.abc.MetaPathFinder, importlib.abc.Loader):\n"
        " def find_spec(self, fullname, path=None, target=None):\n"
        "  if fullname == 'mechanical_cad.kernel_ocp':\n"
        "   return importlib.util.spec_from_loader(fullname, self)\n"
        " def create_module(self, spec): return None\n"
        " def exec_module(self, module):\n"
        f"  raw = Path({str(kernel)!r}).read_bytes()\n"
        f"  assert hashlib.sha256(raw).hexdigest() == {kernel_sha!r}\n"
        f"  exec(compile(raw, {str(kernel)!r}, 'exec'), module.__dict__)\n"
        "sys.meta_path.insert(0, HistoricalKernel())\n"
        "engine = types.ModuleType('mechanical_cad.engine')\n"
        "engine.__package__ = 'mechanical_cad'\n"
        "sys.modules[engine.__name__] = engine\n"
        f"exec(compile({sources['engine']!r}, 'pre_service_engine.py', 'exec'), engine.__dict__)\n"
        "__package__ = 'mechanical_cad'\n"
        f"exec(compile({sources['sidecar']!r}, 'pre_service_sidecar.py', 'exec'))\n"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            case,
            id=case["name"],
            marks=() if case["no_site"] else (pytest.mark.kernel,),
        )
        for case in sector_pre_service_fixtures()[1]["cases"]
    ],
)
def test_exact_pre_service_request_stdout_exit_and_source_differential(case):
    directory, manifest = sector_pre_service_fixtures()
    stored = (directory / (case["name"] + ".request.txt")).read_bytes()
    assert hashlib.sha256(stored).hexdigest() == case["stored_request_sha256"]
    raw = stored + b" " * case["trailing_spaces"]
    assert len(raw) == case["request_bytes"]
    assert hashlib.sha256(raw).hexdigest() == case["request_sha256"]
    expected = (directory / (case["name"] + ".stdout.txt")).read_bytes()
    assert hashlib.sha256(expected).hexdigest() == case["stdout_sha256"]
    if not case["no_site"]:
        pytest.importorskip("OCP")
        pytest.importorskip("slvs")
    current, _ = run(raw=raw.decode("utf-8"), no_site=case["no_site"])
    original, _ = run(
        raw=raw.decode("utf-8"),
        no_site=case["no_site"],
        script=sector_pre_service_script(directory, manifest),
    )
    assert current.returncode == original.returncode == case["returncode"]
    assert original.stdout == expected
    assert_reviewed_pre_service_stdout(case["name"], expected, current.stdout)


def reviewed_pre_service_stdout(name, expected):
    """Apply only independently specified, documented protocol extensions.

    ADR 0009 adds optional diagnostic cylinder origins, including to v1.
    FILE_FORMAT's v1-unchanged ancestry promise concerns Cut ancestry only:
    neither that ledger nor the v2 stable tool-wall identity is added to v1.
    Original bytes/hashes remain authoritative for the archived implementation.
    """
    if name == "primitive_cut_result_2":
        # Preserve the historical capture and the previously reviewed ordinary
        # Cut wall/triangle identity delta, before adding diagnostics below.
        value = json.loads(expected)
        output = value["result"]["features"][-1]
        walls = [face for face in output["topology"] if face["role"] == "cut.wall"]
        assert len(walls) == 1
        wall = walls[0]
        assert wall["id"] == "snapshot:body:face:6"
        assert wall["provenance"] == {
            "semantic_status": "generated",
            "kernel": "OCCT",
            "operation": "cut",
            "operation_id": "body",
            "relation": "tool_surface",
            "evolution": "tool_surface",
            "sources": ["hole_tool/face/side.circle"],
            "id_scope": "evaluation_snapshot_only",
        }
        previous = json.dumps(wall, separators=(",", ":")).encode()
        wall.update(id="hole_tool/face/side.circle", feature_id="hole_tool", role="side.circle")
        wall["provenance"] = {
            "semantic_status": "stable",
            "kernel": "OCCT",
            "operation": "cut",
            "operation_id": "body",
            "relation": "tool_unchanged",
            "evolution": "tool_unchanged",
            "source_id": "hole_tool/face/side.circle",
            "modifying_feature_id": "body",
            "source_count": 1,
            "image_count": 1,
        }
        replacement = json.dumps(wall, separators=(",", ":")).encode()
        assert expected.count(previous) == 1
        expected = expected.replace(previous, replacement)
        expected = expected.replace(b'"snapshot:body:face:6"', b'"hole_tool/face/side.circle"')
    # The plate is 40 x 30, with a centered tool; the failed graph has
    # width=-1 and tool x=width/2. Sketch/parameter pads use the global axis.
    origins = {
        "primitive_cut_result_None": [
            ("hole_tool", "hole_tool/face/side.circle", [20.0, 15.0, 0.0]),
            ("body", "snapshot:body:face:6", [20.0, 15.0, 0.0]),
        ],
        "primitive_cut_result_1": [
            ("hole_tool", "hole_tool/face/side.circle", [20.0, 15.0, 0.0]),
            ("body", "snapshot:body:face:6", [20.0, 15.0, 0.0]),
        ],
        "primitive_cut_result_2": [
            ("hole_tool", "hole_tool/face/side.circle", [20.0, 15.0, 0.0]),
            ("body", "hole_tool/face/side.circle", [20.0, 15.0, 0.0]),
        ],
        "replay_circle_sketch_part": [("pad", "pad/face/side.circle.rim", [0.0, 0.0, 0.0])],
        "replay_parameter_chain": [("pad", "pad/face/side.circle", [0.0, 0.0, 0.0])],
        "independent_failure_graph": [
            ("hole_tool", "hole_tool/face/side.circle", [-0.5, 15.0, 0.0])
        ],
    }
    if name not in origins:
        return expected
    value = json.loads(expected)
    # Round-tripping must not silently normalize any historical wire difference.
    assert json.dumps(value, separators=(",", ":")).encode() + b"\n" == expected
    features = {feature["id"]: feature for feature in value["result"]["features"]}
    for feature_id, face_id, origin in origins[name]:
        faces = [face for face in features[feature_id]["topology"] if face["id"] == face_id]
        assert len(faces) == 1
        signature = faces[0]["signature"]
        assert "axis_origin" not in signature
        signature["axis_origin"] = origin
    if name in ("primitive_cut_result_2", "independent_failure_graph"):
        body = features["body"]
        assert "cut_ancestry" not in body
        # Preserve wire key order: the ledger precedes the output port.
        output = body.pop("output")
        body["cut_ancestry"] = (
            primitive_cut_ancestry() if name == "primitive_cut_result_2" else None
        )
        body["output"] = output
    return json.dumps(value, separators=(",", ":")).encode() + b"\n"


def primitive_cut_ancestry():
    """Plate side walls survive; caps are drilled; tool caps disappear."""
    entries = []
    for port, source, relation in [
        ("base", "pad/face/side.y_min", "unchanged"),
        ("base", "pad/face/side.x_max", "unchanged"),
        ("base", "pad/face/side.y_max", "unchanged"),
        ("base", "pad/face/side.x_min", "unchanged"),
        ("base", "pad/face/cap.start", "modified"),
        ("base", "pad/face/cap.end", "modified"),
        ("tool", "hole_tool/face/side.circle", "unchanged"),
        ("tool", "hole_tool/face/cap.start", "deleted"),
        ("tool", "hole_tool/face/cap.end", "deleted"),
    ]:
        entries.append(
            {
                "port": port,
                "source_id": source,
                "deleted": relation == "deleted",
                "modified": [source] if relation == "modified" else [],
                "generated": [],
                "unchanged": [source] if relation == "unchanged" else [],
            }
        )
    return {"version": 1, "sources": entries}


def assert_reviewed_pre_service_stdout(name, original, current):
    assert current == reviewed_pre_service_stdout(name, original)


@pytest.mark.parametrize(
    "mutation",
    [
        "origin",
        "missing_origin",
        "extra_signature",
        "port",
        "deleted",
        "source",
        "wall",
        "triangle",
    ],
)
def test_reviewed_native_deltas_reject_mutations(mutation):
    directory, _ = sector_pre_service_fixtures()
    name = "primitive_cut_result_2"
    original = (directory / (name + ".stdout.txt")).read_bytes()
    value = json.loads(reviewed_pre_service_stdout(name, original))
    body = value["result"]["features"][-1]
    wall = next(face for face in body["topology"] if face["id"] == "hole_tool/face/side.circle")
    if mutation == "origin":
        wall["signature"]["axis_origin"][0] += 1
    elif mutation == "missing_origin":
        del wall["signature"]["axis_origin"]
    elif mutation == "extra_signature":
        wall["signature"]["unreviewed"] = True
    elif mutation == "port":
        body["cut_ancestry"]["sources"][0]["port"] = "tool"
    elif mutation == "deleted":
        body["cut_ancestry"]["sources"][-1]["deleted"] = False
    elif mutation == "source":
        body["cut_ancestry"]["sources"][0]["source_id"] = "forged/face"
    elif mutation == "wall":
        wall["id"] = "snapshot:body:face:6"
    else:
        # Corrupt only a mesh binding, retaining the correct topology identity.
        raw = json.dumps(body["mesh"], separators=(",", ":"))
        assert '"hole_tool/face/side.circle"' in raw
        body["mesh"] = json.loads(
            raw.replace('"hole_tool/face/side.circle"', '"snapshot:body:face:6"', 1)
        )
    changed = json.dumps(value, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(AssertionError):
        assert_reviewed_pre_service_stdout(name, original, changed)


@pytest.mark.parametrize("name", ["primitive_cut_result_None", "primitive_cut_result_1"])
@pytest.mark.parametrize("mutation", ["ancestry", "identity"])
def test_v1_does_not_receive_v2_cut_extensions(name, mutation):
    directory, _ = sector_pre_service_fixtures()
    original = (directory / (name + ".stdout.txt")).read_bytes()
    value = json.loads(reviewed_pre_service_stdout(name, original))
    body = value["result"]["features"][-1]
    assert "cut_ancestry" not in body
    wall = next(face for face in body["topology"] if face["role"] == "cut.wall")
    assert wall["id"] == "snapshot:body:face:6"
    if mutation == "ancestry":
        body["cut_ancestry"] = primitive_cut_ancestry()
    else:
        wall["id"] = "hole_tool/face/side.circle"
    with pytest.raises(AssertionError):
        assert_reviewed_pre_service_stdout(
            name, original, json.dumps(value, separators=(",", ":")).encode() + b"\n"
        )


def test_historical_kernel_closure_rejects_tampering(tmp_path):
    directory, manifest = sector_pre_service_fixtures()
    for entry in manifest["sources"].values():
        shutil.copyfile(directory / entry["fixture"], tmp_path / entry["fixture"])
    kernel = "kernel_ocp-30383a1.py.txt"
    (tmp_path / kernel).write_bytes((directory / kernel).read_bytes() + b"\n# drift\n")
    with pytest.raises(AssertionError):
        sector_pre_service_script(tmp_path, manifest)


def test_historical_kernel_loader_is_lazy_and_rechecks_bytes(tmp_path):
    directory, manifest = sector_pre_service_fixtures()
    for entry in manifest["sources"].values():
        shutil.copyfile(directory / entry["fixture"], tmp_path / entry["fixture"])
    kernel = "kernel_ocp-30383a1.py.txt"
    shutil.copyfile(directory / kernel, tmp_path / kernel)
    script = sector_pre_service_script(tmp_path, manifest)
    # Tamper after parent validation: a snapshot must not import the kernel,
    # whereas a child attempting that import must reject the changed bytes.
    (tmp_path / kernel).write_bytes(b"raise RuntimeError('must never execute')\n")
    raw = (directory / "snapshot_drilled_plate.request.txt").read_text()
    result, _ = run(raw=raw, no_site=True, script=script)
    assert result.returncode == 0
    assert result.stdout == (directory / "snapshot_drilled_plate.stdout.txt").read_bytes()
    loader = script.split("engine = types.ModuleType", 1)[0]
    result = subprocess.run(
        [sys.executable, "-B", "-S", "-c", loader + "import mechanical_cad.kernel_ocp\n"],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONNOUSERSITE": "1"},
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert b"AssertionError" in result.stderr
    assert b"must never execute" not in result.stderr
