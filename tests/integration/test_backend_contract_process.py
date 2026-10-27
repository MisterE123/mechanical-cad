"""Actual-process admission, native controls, and exact legacy wire preservation."""

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from process_source_binding import (
    SourceBindingError,
    require_source_binding,
    source_bound_script,
)

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
    return json.loads((ROOT / f"examples/{name}.mcad.json").read_text(encoding="utf-8"))


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
            assembly=json.loads(
                (ROOT / "examples/reused_blocks.mcad-assembly.json").read_text(encoding="utf-8")
            ),
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


CHILD_TEXT_FRAMING = r"""
import os, sys
for _wire_stream in (sys.stdin, sys.stdout, sys.stderr):
    _wire_stream.reconfigure(encoding="utf-8", errors="strict", newline="\n")
_wire_original_fdopen = os.fdopen
def _wire_fdopen(fd, mode="r", *args, **kwargs):
    # Both unchanged sidecars create this UTF-8 response stream from dup(1).
    # Configure the child's text writer, never normalize captured output bytes.
    if mode == "w" and kwargs.get("encoding") == "utf-8" and "newline" not in kwargs:
        kwargs["newline"] = "\n"
    return _wire_original_fdopen(fd, mode, *args, **kwargs)
os.fdopen = _wire_fdopen
"""


def framed_child_script(script=None):
    return CHILD_TEXT_FRAMING + (
        script
        if script is not None
        else "import runpy\nrunpy.run_module('mechanical_cad.sidecar', run_name='__main__')\n"
    )


CONTROLLED_UNAVAILABLE = {
    "invalid_deflection": ("OCP",),
    "solver_dependency_absent": ("slvs",),
    "kernel_dependency_absent": ("OCP",),
}


def controlled_unavailability_script(roots):
    assert roots and set(roots) <= {"OCP", "slvs"}
    return f"""
import builtins, importlib.abc, sys
_wire_unavailable_roots = {tuple(roots)!r}
for _wire_name in sys.modules:
    assert not any(_wire_name == root or _wire_name.startswith(root + '.')
                   for root in _wire_unavailable_roots), 'preloaded unavailable module: ' + _wire_name
def _wire_missing(name):
    for root in _wire_unavailable_roots:
        if name == root or name.startswith(root + '.'):
            raise ModuleNotFoundError("No module named '" + root + "'", name=root)
_wire_original_import = builtins.__import__
def _wire_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level == 0:
        _wire_missing(name)
    return _wire_original_import(name, globals, locals, fromlist, level)
class _WireUnavailable(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        _wire_missing(fullname)
        return None
builtins.__import__ = _wire_import
sys.meta_path.insert(0, _WireUnavailable())
"""


def run(
    request=None,
    *,
    raw=None,
    root=ROOT,
    no_site=False,
    script=None,
    framed=False,
    unavailable=(),
):
    command = [sys.executable, "-B"]
    if no_site:
        command.append("-S")
    if framed:
        script = framed_child_script(script)
    entry = (
        script or "import runpy\nrunpy.run_module('mechanical_cad.sidecar', run_name='__main__')\n"
    )
    if unavailable:
        entry = controlled_unavailability_script(unavailable) + entry
    proof = Path(tempfile.mkdtemp(prefix="process-source-")) / "binding.json"
    child = proof.with_name("entry.py")
    child.write_bytes(
        source_bound_script(root, entry, proof, historical_pins=historical_pins()).encode("utf-8")
    )
    command.append(str(child))
    env = dict(os.environ, PYTHONPATH=str(root / "src"), PYTHONNOUSERSITE="1")
    env.pop("PYTHONHOME", None)
    result = subprocess.run(
        command,
        input=json.dumps(request).encode("utf-8") if raw is None else raw.encode("utf-8"),
        capture_output=True,
        timeout=60,
        cwd=root,
        env=env,
        check=False,
    )
    require_source_binding(result, proof)
    return result, json.loads(result.stdout)


@pytest.mark.parametrize("name", ["OCP", "slvs"])
def test_controlled_unavailability_blocks_roots_and_descendants(name):
    script = f"""
import importlib, json
from mechanical_cad.model import Document
assert Document is not None
blocked = []
for candidate in [{name!r}, {name!r} + '.descendant']:
    try:
        importlib.import_module(candidate)
    except ModuleNotFoundError as error:
        assert error.name == {name!r}
        blocked.append(candidate)
    else:
        raise AssertionError('unavailable import succeeded')
try:
    sys.meta_path[0].find_spec({name!r} + '.direct_descendant')
except ModuleNotFoundError as error:
    assert error.name == {name!r}
else:
    raise AssertionError('descendant finder did not reject')
print(json.dumps({{'blocked': blocked}}, separators=(',', ':')))
"""
    process, value = run(script=script, no_site=True, framed=True, unavailable=(name,))
    assert process.returncode == 0 and value == {"blocked": [name, name + ".descendant"]}
    assert process.stderr == b""


@pytest.mark.parametrize("name", ["OCP", "OCP.descendant", "slvs", "slvs.descendant"])
def test_controlled_unavailability_rejects_already_loaded_modules(tmp_path, name):
    entry = (
        f"import sys, types\nsys.modules[{name!r}] = types.ModuleType({name!r})\n"
        + controlled_unavailability_script((name.split(".")[0],))
        + "print('{\"must_not_run\":true}')\n"
    )
    process, proof = _binding_control(tmp_path, entry=entry)
    assert require_source_binding(process, proof)["status"] == "verified"
    assert process.returncode != 0 and process.stdout == b""
    assert b"preloaded unavailable module" in process.stderr


def test_positive_native_cases_receive_no_unavailability_policy():
    _, manifest = sector_pre_service_fixtures()
    for case in manifest["cases"]:
        if not case["no_site"]:
            assert CONTROLLED_UNAVAILABLE.get(case["name"], ()) == ()
    process, value = run(
        no_site=True,
        framed=True,
        script="import json\nprint(json.dumps({'policy_installed': '_wire_unavailable_roots' in globals()}))\n",
    )
    assert process.returncode == 0 and value == {"policy_installed": False}


def historical_pins():
    directory, manifest = sector_pre_service_fixtures()
    pins = {
        "pre_service_" + name + ".py": {
            "sha256": entry["sha256"],
            "module": "mechanical_cad.engine" if name == "engine" else None,
        }
        for name, entry in manifest["sources"].items()
    }
    kernel = directory / "kernel_ocp-30383a1.py.txt"
    pins[str(kernel)] = dict(
        sha256="77f3f3033f95cbe72a97dbdab70769f1f0c3d34604f2d2ac036d6e10f78224ac",
        module="mechanical_cad.kernel_ocp",
    )
    pins["legacy_sidecar.py"] = dict(
        sha256=hashlib.sha256(legacy_sidecar_source().encode("utf-8")).hexdigest(), module=None
    )
    return pins


def _binding_control(tmp_path, *, prelude="", entry=None, tamper=False):
    root, older = tmp_path / "intended", tmp_path / "older"
    for folder in [root, older]:
        package = folder / "src/mechanical_cad"
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_bytes(b"")
        (package / "engine.py").write_bytes(b"VALUE = 'intended'\n")
    (older / "src/mechanical_cad/engine.py").write_bytes(
        b"raise AssertionError('OLDER_SOURCE_MUST_NOT_EXECUTE')\n"
    )
    proof = Path(tempfile.mkdtemp(prefix="proof-", dir=tmp_path)) / "binding.json"
    body = entry or (
        "from mechanical_cad.engine import VALUE\n"
        "import json\nprint(json.dumps({'value': VALUE}, separators=(',', ':')))\n"
    )
    program = source_bound_script(root, CHILD_TEXT_FRAMING + body, proof, historical_pins={})
    if tamper:
        (root / "src/mechanical_cad/engine.py").write_bytes(b"VALUE = 'changed'\n")
    child = proof.with_name("entry.py")
    child.write_bytes((prelude.format(older=str(older / "src")) + program).encode("utf-8"))
    process = subprocess.run(
        [sys.executable, "-B", "-S", str(child)],
        capture_output=True,
        timeout=30,
        check=False,
    )
    return process, proof


def test_child_binding_overrides_ambient_older_source_and_rejects_preload(tmp_path):
    process, proof = _binding_control(tmp_path)
    assert require_source_binding(process, proof)["status"] == "verified"
    assert process.returncode == 0 and process.stdout == b'{"value":"intended"}\n'
    ambient = "import sys\nsys.path.insert(0, {older!r})\n"
    process, proof = _binding_control(tmp_path, prelude=ambient)
    assert require_source_binding(process, proof)["status"] == "verified"
    assert process.returncode == 0 and process.stdout == b'{"value":"intended"}\n'
    process, proof = _binding_control(tmp_path, prelude=ambient + "import mechanical_cad\n")
    with pytest.raises(SourceBindingError, match="preloaded project module"):
        require_source_binding(process, proof)
    assert process.returncode != 0 and process.stdout == b""


def test_child_binding_rejects_mismatched_module_origin_before_accepting_output(tmp_path):
    process, proof = _binding_control(tmp_path)
    assert require_source_binding(process, proof)["status"] == "verified"
    entry = (
        "import mechanical_cad.engine as engine\n"
        "engine.__spec__.origin = 'foreign/engine.py'\n"
        'print(\'{"value":"untrusted"}\')\n'
    )
    process, proof = _binding_control(tmp_path, entry=entry)
    with pytest.raises(SourceBindingError, match="module origin mismatch"):
        require_source_binding(process, proof)
    assert process.stdout == b'{"value":"untrusted"}\n'
    assert process.returncode != 0


def test_child_binding_rejects_live_bytes_changed_after_capture(tmp_path):
    process, proof = _binding_control(tmp_path)
    assert require_source_binding(process, proof)["status"] == "verified"
    process, proof = _binding_control(tmp_path, tamper=True)
    with pytest.raises(SourceBindingError, match="source bytes mismatch"):
        require_source_binding(process, proof)
    assert process.returncode != 0 and process.stdout == b""


@pytest.mark.parametrize("port", ["stdout", "fdopen"])
def test_child_text_framing_is_utf8_lf(monkeypatch, port):
    monkeypatch.setenv("PYTHONIOENCODING", "ascii:strict")
    text = "\u03bb\u4e2d\U0001f527"
    script = f"""
import json, os, sys
request = json.loads(sys.stdin.read())
output = sys.stdout if {port!r} == 'stdout' else os.fdopen(os.dup(1), 'w', encoding='utf-8')
output.write(json.dumps(request, ensure_ascii=False, separators=(',', ':')) + '\\n')
output.flush()
sys.stderr.write(request['value'] + '\\n')
"""
    result, response = run(
        raw=json.dumps({"value": text}, ensure_ascii=False),
        no_site=True,
        script=script,
        framed=True,
    )
    assert result.returncode == 0
    assert response == {"value": text}
    assert result.stdout == ('{"value":"' + text + '"}\n').encode("utf-8")
    assert result.stderr == (text + "\n").encode("utf-8")


@pytest.mark.parametrize("port", ["binary", "explicit_text_newline"])
def test_child_framing_preserves_explicit_output_bytes(port):
    script = f"""
import os, sys
if {port!r} == 'binary':
    sys.stdout.buffer.write(b'{{"value":1}}\\r\\n')
else:
    output = os.fdopen(os.dup(1), 'w', encoding='utf-8', newline='\\r\\n')
    output.write('{{"value":1}}\\n')
    output.flush()
sys.stderr.buffer.write(b'\\xff\\r\\n')
"""
    result, response = run(no_site=True, script=script, framed=True)
    assert result.returncode == 0 and response == {"value": 1}
    assert result.stdout == b'{"value":1}\r\n'
    assert result.stderr == b"\xff\r\n"


@pytest.mark.parametrize("kind", ["part", "assembly"])
def test_request_documents_are_read_as_utf8(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    examples = tmp_path / "examples"
    examples.mkdir()
    value = {"label": "\u03bb\u4e2d\U0001f527"}
    raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
    (examples / "drilled_plate.mcad.json").write_bytes(raw)
    (examples / "reused_blocks.mcad-assembly.json").write_bytes(raw)
    request = operation("canonical_snapshot" if kind == "part" else "assembly_replay")
    assert request["document" if kind == "part" else "assembly"] == value


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


PLATFORM_NATIVE_CASES = frozenset(
    {
        "primitive_cut_result_None",
        "primitive_cut_result_1",
        "primitive_cut_result_2",
        "replay_circle_sketch_part",
        "replay_parameter_chain",
        "independent_failure_graph",
    }
)


def _pre_service_cases(*, native=None, mark_native=True):
    return [
        pytest.param(
            case,
            id=case["name"],
            marks=() if case["no_site"] or not mark_native else (pytest.mark.kernel,),
        )
        for case in sector_pre_service_fixtures()[1]["cases"]
        if native is None or (case["name"] in PLATFORM_NATIVE_CASES) == native
    ]


def _pre_service_documents(case):
    directory, manifest = sector_pre_service_fixtures()
    stored = (directory / (case["name"] + ".request.txt")).read_bytes()
    assert hashlib.sha256(stored).hexdigest() == case["stored_request_sha256"]
    raw = stored + b" " * case["trailing_spaces"]
    assert len(raw) == case["request_bytes"]
    assert hashlib.sha256(raw).hexdigest() == case["request_sha256"]
    expected = (directory / (case["name"] + ".stdout.txt")).read_bytes()
    assert hashlib.sha256(expected).hexdigest() == case["stdout_sha256"]
    return directory, manifest, raw, expected


def _pre_service_process_pair(case):
    directory, manifest, raw, expected = _pre_service_documents(case)
    if not case["no_site"]:
        pytest.importorskip("OCP")
        pytest.importorskip("slvs")
    unavailable = CONTROLLED_UNAVAILABLE.get(case["name"], ())
    current, _ = run(
        raw=raw.decode("utf-8"), no_site=case["no_site"], framed=True, unavailable=unavailable
    )
    original, _ = run(
        raw=raw.decode("utf-8"),
        no_site=case["no_site"],
        script=sector_pre_service_script(directory, manifest),
        framed=True,
        unavailable=unavailable,
    )
    return current, original, expected


def _assert_exact_pre_service_golden(case):
    current, original, expected = _pre_service_process_pair(case)
    assert current.returncode == original.returncode == case["returncode"]
    assert original.stdout == expected
    assert_reviewed_pre_service_stdout(case["name"], expected, current.stdout)


@pytest.mark.parametrize("case", _pre_service_cases(mark_native=False))
def test_pre_service_fixture_identity_is_exact_on_every_host(case):
    _pre_service_documents(case)


@pytest.mark.parametrize("case", _pre_service_cases(native=False))
def test_exact_pre_service_request_stdout_exit_and_source_differential(case):
    _assert_exact_pre_service_golden(case)


@pytest.mark.skipif(
    sys.platform != "linux", reason="Six platform-sensitive Linux-sealed native goldens"
)
@pytest.mark.parametrize("case", _pre_service_cases(native=True))
def test_linux_native_pre_service_golden(case):
    _assert_exact_pre_service_golden(case)


@pytest.mark.skipif(
    sys.platform != "win32", reason="Full Windows historical/live native differential"
)
@pytest.mark.parametrize("case", _pre_service_cases(native=True))
def test_windows_native_pre_service_full_raw_differential(case):
    current, original, _ = _pre_service_process_pair(case)
    assert current.returncode == original.returncode == case["returncode"]
    assert_reviewed_pre_service_stdout(case["name"], original.stdout, current.stdout)


@pytest.mark.parametrize("name", sorted(PLATFORM_NATIVE_CASES))
@pytest.mark.parametrize("mutation", ["vertex", "triangle", "nonnumeric", "error", "key_order"])
def test_full_native_differential_rejects_unreviewed_changes(name, mutation):
    _, manifest = sector_pre_service_fixtures()
    case = next(case for case in manifest["cases"] if case["name"] == name)
    _, _, _, original = _pre_service_documents(case)
    current = reviewed_pre_service_stdout(name, original)
    assert_reviewed_pre_service_stdout(name, original, current)
    value = json.loads(current)
    feature = next(feature for feature in value["result"]["features"] if feature.get("mesh"))
    if mutation == "vertex":
        feature["mesh"]["vertices"][0][0] += 0.125
    elif mutation == "triangle":
        triangle = feature["mesh"]["triangles"][0]
        triangle[0] = (triangle[0] + 1) % len(feature["mesh"]["vertices"])
    elif mutation == "nonnumeric":
        feature["id"] += "-unreviewed"
    elif mutation == "error":
        value["error"] = {"code": "unreviewed", "message": "unexpected failure"}
    else:
        value = dict(reversed(list(value.items())))
    changed = json.dumps(value, separators=(",", ":")).encode("utf-8") + b"\n"
    assert changed != current
    with pytest.raises(AssertionError):
        assert_reviewed_pre_service_stdout(name, original, changed)


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
    raw = (directory / "snapshot_drilled_plate.request.txt").read_text(encoding="utf-8")
    result, _ = run(raw=raw, no_site=True, script=script, framed=True)
    assert result.returncode == 0
    assert result.stdout == (directory / "snapshot_drilled_plate.stdout.txt").read_bytes()
    loader = script.split("engine = types.ModuleType", 1)[0]
    proof = Path(tempfile.mkdtemp(prefix="process-source-")) / "binding.json"
    child = proof.with_name("entry.py")
    child.write_bytes(
        source_bound_script(
            ROOT,
            framed_child_script(loader + "import mechanical_cad.kernel_ocp\n"),
            proof,
            historical_pins=historical_pins(),
        ).encode("utf-8")
    )
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-S",
            str(child),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONNOUSERSITE": "1"},
        capture_output=True,
        timeout=30,
    )
    require_source_binding(result, proof)
    assert result.returncode != 0
    assert b"AssertionError" in result.stderr
    assert b"must never execute" not in result.stderr
