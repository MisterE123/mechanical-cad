"""Real sidecar evidence behind the retained-upstream-edit Blender scenarios."""

import copy
import importlib
import math
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.projection_repair import replace_reference
from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from staged_edit_cases import feature, projection_case, support_case  # noqa: E402

package = types.ModuleType("mcad_staged_repair_integration")
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[package.__name__] = package
support_edit = importlib.import_module(package.__name__ + ".support_intent_edit")


def replay(document):
    return process_request({"protocol_version": 1, "result_version": 3, "document": document})


def test_actual_upstream_split_requires_explicit_support_repair():
    base, proposed = support_case()
    assert replay(base)["ok"]
    original = copy.deepcopy(proposed)
    failed = replay(proposed)
    assert not failed["ok"]
    rows = {row["id"]: row for row in failed["result"]["features"]}
    assert rows["slot_tool"]["status"] == rows["slotted"]["status"] == "ok"
    assert rows["attached"]["status"] == "failed"
    assert rows["boss"]["status"] == "blocked"
    repaired = support_edit.edit_support_candidate(
        proposed,
        "attached",
        "PRESERVE_PLANE",
        "slotted",
        "block/face/cap.end",
        failed["result"],
        orientation="WORLD_AXES",
    )
    result = replay(repaired)
    assert result["ok"], result
    assert feature(repaired, "slot_tool")["params"]["length"] == 5
    assert feature(repaired, "attached")["sketch"] == feature(base, "attached")["sketch"]
    assert result["result"]["features"][-1]["stats"]["volume"] == pytest.approx(8 * math.pi)
    assert proposed == original
    assert not replay(proposed)["ok"]


def test_actual_upstream_identity_change_keeps_projection_dependants_after_repair():
    base, proposed = projection_case()
    assert replay(base)["ok"]
    original = copy.deepcopy(proposed)
    failed = replay(proposed)
    assert not failed["ok"]
    rows = {row["id"]: row for row in failed["result"]["features"]}
    assert rows["source"]["status"] == "ok"
    assert rows["target"]["status"] == "failed"
    assert rows["solid"]["status"] == "blocked"
    repaired = replace_reference(
        proposed,
        "target",
        "reference",
        {"source": "replacement_ring"},
        source_id="source",
        source_solved=rows["source"]["sketch"]["solved"],
    )
    result = replay(repaired)
    assert result["ok"], result
    assert feature(repaired, "source") == feature(proposed, "source")
    old = feature(proposed, "target")["sketch"]
    new = feature(repaired, "target")["sketch"]
    assert [c["id"] for c in old["constraints"]] == [c["id"] for c in new["constraints"]]
    assert next(c for c in new["constraints"] if c["id"] == "match") == next(
        c for c in old["constraints"] if c["id"] == "match"
    )
    assert [c["id"] for c in new["circles"]] == [c["id"] for c in old["circles"]]
    assert new["circles"][1] == old["circles"][1]
    assert new["circles"][0]["radius"] == 4
    assert result["result"]["features"][-1]["stats"]["volume"] == pytest.approx(80 * math.pi)
    assert proposed == original
    assert not replay(proposed)["ok"]


@pytest.mark.parametrize("failure", ["support", "projection"])
def test_unexpected_native_reference_runtime_error_is_not_repairable(monkeypatch, failure):
    from mechanical_cad.kernel_ocp import OCPKernel
    from mechanical_cad.model import Document
    from mechanical_cad.sketch_support import resolve_solid_projected_feature

    def crash(*args, **kwargs):
        raise RuntimeError("Unexpected native failure, not an unresolved reference")

    if failure == "support":
        base, _ = support_case()
        monkeypatch.setattr(OCPKernel, "support_face_signature", crash)
        result = replay(base)
        row = next(r for r in result["result"]["features"] if r["id"] == "attached")
        assert row["error"]["code"] == "kernel_error"
    else:
        base, _ = projection_case()
        target = next(f for f in Document.from_dict(base).features if f.id == "target")
        kernel = types.SimpleNamespace(projected_edges=crash)
        with pytest.raises(RuntimeError, match="Unexpected native failure"):
            resolve_solid_projected_feature(target, kernel, object())
        from mechanical_cad.errors import CADException

        def typed_crash(*args, **kwargs):
            raise CADException("kernel_error", "Explicit kernel failure")

        kernel.projected_edges = typed_crash
        with pytest.raises(CADException) as caught:
            resolve_solid_projected_feature(target, kernel, object())
        assert caught.value.code == "kernel_error"


def test_coupled_schema_three_reference_repairs_keep_relation_and_fail_inconsistent_choice():
    from staged_edit_cases import coupled_projection_case

    base, proposed = coupled_projection_case()
    assert replay(base)["ok"]
    failed = replay(proposed)
    solved = next(r for r in failed["result"]["features"] if r["id"] == "source")["sketch"][
        "solved"
    ]
    first = replace_reference(
        proposed,
        "target",
        "reference",
        {"source": "replacement_ring"},
        source_id="source",
        source_solved=solved,
    )
    assert not replay(first)["ok"]
    complete = replace_reference(
        first,
        "target",
        "reference2",
        {"source": "replacement_ring2"},
        source_id="source",
        source_solved=solved,
    )
    assert replay(complete)["ok"]
    assert (
        feature(complete, "target")["sketch"]["constraints"][-1]
        == feature(base, "target")["sketch"]["constraints"][-1]
    )
    # Both bindings resolve, but the authored equality is genuinely inconsistent.
    feature(complete, "source")["sketch"]["constraints"][-1]["value"] = "r + 2"
    failed = replay(complete)
    assert not failed["ok"]
    target = next(r for r in failed["result"]["features"] if r["id"] == "target")
    assert target["error"]["code"] not in {"invalid_sketch_projection", "invalid_sketch_support"}
