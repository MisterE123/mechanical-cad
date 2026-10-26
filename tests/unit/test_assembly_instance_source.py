"""Instance pencils dispatch the guarded editor without drawing dynamic enums."""

import ast
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_assembly_workflow_ui import draw_controls

ROOT = Path(__file__).resolve().parents[2]


def test_each_instance_pencil_carries_exact_cached_source_identity():
    events, data = draw_controls()
    pencils = [
        e for e in events if e[0] == "operator" and e[1] == "mcad.assembly_edit_instance_source"
    ]
    parts = {p["id"]: p for p in data["parts"]}
    assert len(pencils) == len(data["instances"])
    for event, instance in zip(pencils, data["instances"], strict=True):
        props = event[4]
        assert props.instance_id == instance["id"]
        assert props.source_part_id == instance["part_id"]
        assert props.assembly_id == data["id"]
        assert props.source_digest == parts[instance["part_id"]]["source_digest"]
        assert props.output_feature_id == parts[instance["part_id"]]["output_feature_id"]


@pytest.mark.parametrize(
    "changed", [None, "assembly", "missing", "rebound", "revision", "output", "busy"]
)
@pytest.mark.parametrize("child_result", [{"RUNNING_MODAL"}, {"CANCELLED"}])
def test_launcher_validates_before_invoking_existing_confirmation(changed, child_result):
    data = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    instance = data["instances"][1]
    part = next(p for p in data["parts"] if p["id"] == instance["part_id"])
    button = SimpleNamespace(
        assembly_id=data["id"],
        instance_id=instance["id"],
        source_part_id=part["id"],
        source_digest=part["source_digest"],
        output_feature_id=part["output_feature_id"],
    )
    if changed == "assembly":
        data["id"] = "another"
    if changed == "missing":
        data["instances"].remove(instance)
    if changed == "rebound":
        instance["part_id"] = "another"
    if changed == "revision":
        part["source_digest"] = "changed"
    if changed == "output":
        part["output_feature_id"] = "another"
    before = copy.deepcopy(data)
    calls = []

    def idle(_):
        if changed == "busy":
            raise ValueError("Busy")

    namespace = {
        "state_api": SimpleNamespace(require_idle=idle),
        "assembly": lambda _: data,
        "bridge": SimpleNamespace(BridgeError=ValueError),
        "reject": lambda *args: {"CANCELLED"},
        "bpy": SimpleNamespace(
            ops=SimpleNamespace(
                mcad=SimpleNamespace(
                    assembly_open_part=lambda *args, **kw: calls.append((args, kw)) or child_result
                )
            )
        ),
    }
    source = ROOT / "blender_addon/mechanical_cad_blender/assembly_operators.py"
    cls = next(
        n
        for n in ast.parse(source.read_text()).body
        if isinstance(n, ast.ClassDef) and n.name == "MCAD_OT_assembly_edit_instance_source"
    )
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "execute")
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
    result = namespace["execute"](button, object())
    assert data == before
    assert result == ({"CANCELLED"} if changed or "CANCELLED" in child_result else {"FINISHED"})
    assert calls == ([] if changed else [(("INVOKE_DEFAULT",), {"part_id": part["id"]})])


@pytest.mark.parametrize("count,noun", [(1, "instance"), (3, "instances")])
@pytest.mark.parametrize(
    "retained", [None, "document_name", "sketch_draft_json", "error", "last_good_label"]
)
def test_source_dialog_uses_natural_shared_count(count, noun, retained):
    source = ROOT / "blender_addon/mechanical_cad_blender/assembly_operators.py"
    cls = next(
        n
        for n in ast.parse(source.read_text()).body
        if isinstance(n, ast.ClassDef) and n.name == "MCAD_OT_assembly_open_part"
    )
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "draw")
    labels = []
    properties = []
    layout = SimpleNamespace(
        prop=lambda *args, **kw: properties.append((args, kw)),
        label=lambda **kw: labels.append(kw["text"]),
    )
    spec = importlib.util.spec_from_file_location(
        "instance_source_compact", ROOT / "blender_addon/mechanical_cad_blender/compact_status.py"
    )
    compact = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compact)
    namespace = {
        "rows": lambda *args: [{"part_id": "shared"}] * count,
        "help_lines": lambda *args: None,
        "compact_status": compact,
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
    working = SimpleNamespace(document_json="", status="EMPTY", features=[], document_name="")
    if retained:
        setattr(working, retained, "Retained content")
    context = SimpleNamespace(scene=SimpleNamespace(mechanical_cad=working))
    namespace["draw"](SimpleNamespace(layout=layout, part_id="shared"), context)
    assert f"Source used by {count} {noun}. Update All Instances applies to all." in labels
    warning = "Save the working Part first if you want to retain its edits."
    assert (warning in labels) is bool(retained)
    assert ("No working Part open" in labels) is (retained is None)
    confirmed = next(kw for args, kw in properties if args[1] == "confirmed")
    assert confirmed == ({} if retained else {"text": "Open as working Part"})
