"""Bounded exact Loft geometry and canonical replay, not GUI qualification."""

import math

import pytest
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.TopAbs import TopAbs_WIRE
from OCP.TopoDS import TopoDS

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import KernelError, OCPKernel, _subshapes
from mechanical_cad.loft_sections import set_sections
from mechanical_cad.model import Document


def document(ruled=1, count=3):
    profiles = [
        {"id": f"p{i}", "kind": "sketch_circle", "params": {"radius": r, "z": z}}
        for i, (r, z) in enumerate([(2, 0), (5, 5), (3, 13)])
    ]
    if count != 3:
        profiles = [
            {"id": f"p{i}", "kind": "sketch_circle", "params": {"radius": 2, "z": i}}
            for i in range(count)
        ]
    f = {"id": "loft", "kind": "loft", "params": {"ruled": ruled}}
    set_sections(f, [p["id"] for p in profiles])
    return Document.from_dict(
        {
            "schema_version": 1,
            "id": "d",
            "name": "D",
            "units": "mm",
            "parameters": {},
            "features": profiles + [f],
            "active_feature": "loft",
        }
    )


@pytest.mark.parametrize("ruled", [0, 1])
def test_three_sections_exact_valid_and_unknown_generated_faces(ruled):
    kernel = OCPKernel()
    doc = document(ruled)
    replay = regenerate(Document.from_json(doc.to_json()), kernel, result_version=3)
    assert replay.ok, replay.result
    result = replay.result["features"][-1]
    assert result["stats"]["valid"] and result["stats"]["solids"] == 1
    assert result["stats"]["volume"] > 0
    if ruled:
        expected = math.pi / 3 * (5 * (4 + 10 + 25) + 8 * (25 + 15 + 9))
        assert result["stats"]["volume"] == pytest.approx(expected, rel=1e-6)
    assert all(f["provenance"]["semantic_status"] != "stable" for f in result["topology"])


@pytest.mark.parametrize("count", [2, 16])
def test_supported_endpoints(count):
    replay = regenerate(document(1, count), OCPKernel())
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(
        math.pi * 4 * (count - 1)
    )


def test_middle_section_edit_changes_exact_result_and_roundtrips():
    first = document()
    raw = first.to_dict()
    raw["features"][1]["params"]["radius"] = 4
    second = Document.from_dict(raw)
    a, b = [regenerate(doc, OCPKernel()) for doc in (first, second)]
    assert a.ok and b.ok
    assert a.result["features"][-1]["stats"]["volume"] > b.result["features"][-1]["stats"]["volume"]
    assert second.features[-1].to_dict() == first.features[-1].to_dict()


def test_holes_and_solid_sections_fail_closed():
    kernel = OCPKernel()
    outer = TopoDS.Wire(_subshapes(kernel.circle(5), TopAbs_WIRE)[0])
    inner = TopoDS.Wire(_subshapes(kernel.circle(2), TopAbs_WIRE)[0].Reversed())
    builder = BRepBuilderAPI_MakeFace(outer)
    builder.Add(inner)
    end = kernel.circle(4, z=10)
    for bad in (builder.Face(), kernel.extrude(kernel.circle(2), 3)):
        with pytest.raises(KernelError):
            kernel.loft_sections([bad, end])


def test_authored_order_is_not_sorted_and_legacy_entrypoint_preserved():
    class ObservedKernel(OCPKernel):
        def loft_sections(self, sections, ruled=0):
            self.order = [self.inspect(p)["area"] for p in sections]
            return super().loft_sections(sections, ruled)

    raw = document().to_dict()
    set_sections(raw["features"][-1], ["p2", "p1", "p0"])
    kernel = ObservedKernel()
    replay = regenerate(Document.from_dict(raw), kernel)
    assert replay.ok, replay.result
    assert kernel.order == pytest.approx([9 * math.pi, 25 * math.pi, 4 * math.pi])
    assert raw["features"][-1]["inputs"]["section_1"] == "p2"


def test_coplanar_degenerate_sections_refuse_zero_volume_solid():
    kernel = OCPKernel()
    with pytest.raises(KernelError, match="positive measurable volume"):
        kernel.loft_sections([kernel.circle(2), kernel.circle(3)])


@pytest.mark.parametrize("version", [2, 3])
def test_exact_export_crosses_client_boundary_and_preserves_order(version, tmp_path):
    from pathlib import Path

    from mechanical_cad.sidecar import process_request

    bridge = client("geometry_result_v3" if version == 3 else "part_result_bridge")
    request = {
        "protocol_version": 1,
        "result_version": version,
        "document": document().to_dict(),
        "action": "export_step",
        "destination": str(tmp_path / f"loft_{version}.step"),
    }
    response = process_request(request)
    assert response["ok"], response
    bridge.validate_response(request, response)
    assert Path(request["destination"]).stat().st_size > 1000


def test_embedded_assembly_retains_all_profile_dependencies():
    from mechanical_cad.sidecar import process_request

    edit = client("assembly_edit")
    validator = client("assembly_bridge")
    request = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "result_version": 2,
        "action": "assembly_replay",
        "assembly": edit.new_from_part(document().to_dict()),
    }
    response = process_request(request)
    assert response["ok"], response
    validator.validate_response(request, response)


def client(name):
    import importlib
    import sys
    import types
    from pathlib import Path

    if "multi_loft_boundary" not in sys.modules:
        package = types.ModuleType("multi_loft_boundary")
        package.__path__ = [
            str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
        ]
        sys.modules[package.__name__] = package
    return importlib.import_module("multi_loft_boundary." + name)


@pytest.mark.parametrize("version", [2, 3])
def test_open_section_blocks_and_client_accepts_honest_failure(version):
    from mechanical_cad.sidecar import process_request

    source = document().to_dict()
    source["schema_version"] = 2
    source["features"][1] = {
        "id": "p1",
        "kind": "sketch_constrained",
        "sketch": {
            "schema_version": 2,
            "id": "open",
            "units": "mm",
            "plane": {"id": "xy", "origin": [0, 0, 5], "quaternion": [1, 0, 0, 0]},
            "points": [{"id": "a", "u": 0, "v": 0}, {"id": "b", "u": 10, "v": 0}],
            "lines": [{"id": "ab", "start": "a", "end": "b"}],
            "circles": [],
            "constraints": [],
        },
    }
    request = {"protocol_version": 1, "result_version": version, "document": source}
    response = process_request(request)
    assert not response["ok"], response
    last = response["result"]["features"][-1]
    assert last["status"] == "blocked" and last["error"]["code"] == "profile_unavailable"
    client("result_v3" if version == 3 else "part_result_bridge").validate_response(
        request, response
    )
