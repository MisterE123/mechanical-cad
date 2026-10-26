"""Canonical explicit-relation plate: real solve, edit, provenance and export.

The pure general-editor adapter checks below are not Blender GUI evidence.
"""

import importlib
import sys
import types
from collections import Counter
from pathlib import Path

import pytest

pytest.importorskip("OCP")
pytest.importorskip("slvs")

from mechanical_cad.actions import run_geometry_action
from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel, _shape_bounds
from mechanical_cad.model import Document, load_document
from mechanical_cad.sidecar import process_request
from mechanical_cad.topology import resolve_reference

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/explicit_constraint_plate.mcad.json"
POINT_IDS = {"corner_origin", "corner_east", "corner_far", "corner_north"}
LINE_IDS = {"edge_south", "edge_east", "edge_north", "edge_west"}
CONSTRAINT_IDS = {
    "origin_lock",
    "south_axis",
    "east_axis",
    "north_axis",
    "west_axis",
    "width_driver",
    "depth_driver",
}
pytestmark = pytest.mark.kernel


@pytest.fixture
def document():
    return load_document(EXAMPLE)


@pytest.fixture(scope="module")
def editor_modules():
    # Import only native-free adapter leaves, without loading bpy/registration.
    name = "mcad_constraint_example_tests"
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
    sys.modules[name] = package
    return tuple(
        importlib.import_module(f"{name}.{module}")
        for module in ("general_sketch_draft", "sketch_draft", "constraint_selection")
    )


def replay(document):
    result = regenerate(document, OCPKernel(), result_version=2)
    assert result.ok, result.result
    return result


def assert_plate(result, width=40, depth=25, thickness=8):
    features = {feature["id"]: feature for feature in result.result["features"]}
    outline, body = features["plate_outline"], features["plate_body"]
    report = outline["sketch"]
    assert report["solver"] == "libslvs"
    assert report["status"] == "okay"
    assert report["remaining_dof"] == 0
    assert report["failed_constraints"] == report["redundant_constraints"] == []
    assert report["max_residual_mm"] < 1e-7
    assert report["dimensions"] == {"width_driver": width, "depth_driver": depth}
    solved = {point["id"]: (point["u"], point["v"]) for point in report["solved"]["points"]}
    for identifier, coordinates in {
        "corner_origin": (0, 0),
        "corner_east": (width, 0),
        "corner_far": (width, depth),
        "corner_north": (0, depth),
    }.items():
        assert solved[identifier] == pytest.approx(coordinates, abs=1e-7)
    assert outline["output"]["profile"] == {
        "state": "available",
        "region_kind": "line_loop",
    }
    assert body["output"]["kind"] == "solid"
    assert body["stats"]["valid"] and body["stats"]["solids"] == 1
    assert body["stats"]["faces"] == 6
    assert body["stats"]["volume"] == pytest.approx(width * depth * thickness, rel=1e-10)
    assert _shape_bounds(result.shapes["plate_body"]) == pytest.approx(
        (0, 0, 0, width, depth, thickness), abs=1e-7
    )
    return outline, body


def test_canonical_example_has_shared_ids_explicit_relations_and_no_hidden_shape(document):
    assert EXAMPLE.read_bytes() == document.to_json().encode("utf-8")
    assert Document.from_json(document.to_json()) == document
    assert document.schema_version == 2 and document.units == "mm"
    assert document.active_feature == "plate_body"
    assert [(feature.id, feature.kind) for feature in document.features] == [
        ("plate_outline", "sketch_constrained"),
        ("plate_body", "extrude"),
    ]
    sketch = document.features[0].sketch
    assert sketch.schema_version == 2 and not sketch.circles
    assert {point.id for point in sketch.points} == POINT_IDS
    assert {line.id for line in sketch.lines} == LINE_IDS
    assert Counter(endpoint for line in sketch.lines for endpoint in (line.start, line.end)) == {
        point_id: 2 for point_id in POINT_IDS
    }
    relations = {relation.id: relation for relation in sketch.constraints}
    assert set(relations) == CONSTRAINT_IDS
    assert Counter(relation.kind for relation in relations.values()) == {
        "fixed": 1,
        "horizontal": 2,
        "vertical": 2,
        "distance": 2,
    }
    assert relations["origin_lock"].refs == ("corner_origin",)
    assert relations["origin_lock"].target == (0, 0)
    assert relations["width_driver"].value == "width"
    assert relations["depth_driver"].value == "depth"
    assert dict(document.features[1].inputs) == {"profile": "plate_outline"}
    assert dict(document.features[1].params) == {"length": "thickness"}


def test_native_solve_and_geometry_gate_do_not_rewrite_authored_seeds(document):
    before = document.to_json()
    outline, _body = assert_plate(replay(document))
    assert outline["sketch"]["solved"]["points"] != document.features[0].sketch.to_dict()["points"]
    checked = run_geometry_action(document, "check_geometry", result_version=2)
    assert checked["ok"], checked
    assert checked["result"]["document_hash"] == document.content_hash
    assert checked["export"] is None
    assert checked["geometry_check"]["brep"]["volume"] == pytest.approx(8000)
    mesh = checked["geometry_check"]["mesh"]
    assert mesh["watertight"] and mesh["consistently_oriented"] and mesh["vertex_manifold"]
    assert document.to_json() == before


@pytest.mark.parametrize(
    "width,depth,thickness", [(60, 25, 8), (40, 35, 8), (40, 25, 10), (60, 35, 10)]
)
def test_parameter_edits_keep_feature_entity_constraint_and_side_identity(
    document, width, depth, thickness
):
    _outline, before = assert_plate(replay(document))
    edited = document.with_parameter("width", width).with_parameter("depth", depth)
    edited = edited.with_parameter("thickness", thickness)
    assert edited.features == document.features
    _outline, after = assert_plate(replay(edited), width, depth, thickness)
    assert {face["role"] for face in after["topology"]} == {
        "cap.start",
        "cap.end",
        *(f"side.line.{identifier}" for identifier in LINE_IDS),
    }
    for face in before["topology"]:
        reference = {key: face[key] for key in ("feature_id", "role", "kind")}
        resolution = resolve_reference(reference, after["topology"])
        assert resolution.status == "resolved"
        assert resolution.candidate.id == face["id"]
    for face in after["topology"]:
        assert face["provenance"]["semantic_status"] == "stable"
        if face["role"].startswith("side."):
            assert face["provenance"]["source_boundary"] == face["role"].removeprefix("side.")
            assert face["provenance"]["relation"] == "generated_from_profile_edge"


def test_record_reordering_keeps_native_geometry_and_line_provenance(document):
    reordered = document.to_dict()
    sketch = reordered["features"][0]["sketch"]
    for key in ("points", "lines", "constraints"):
        sketch[key].reverse()
    reordered["features"].reverse()
    before = replay(document)
    after = replay(Document.from_dict(reordered))
    assert_plate(after)
    assert {feature["id"]: feature for feature in before.result["features"]} == {
        feature["id"]: feature for feature in after.result["features"]
    }


def test_general_editor_accepts_example_and_checked_formula_edit(document, editor_modules):
    general, rectangle, selection = editor_modules
    base = document.to_json()
    draft = general.GeneralSketchDraft(base, "plate_outline", is_edit=True)
    assert draft.consumed_by == ("plate_body",)
    assert Document.from_dict(draft.candidate()) == document
    with pytest.raises(rectangle.DraftError, match="four-corner rectangle"):
        rectangle.RectangleDraft(base, "plate_outline", is_edit=True)
    for kind, identifier, action, expected in (
        ("line", "edge_south", "horizontal", "south_axis"),
        ("line", "edge_east", "vertical", "east_axis"),
        ("point", "corner_origin", "fix_origin", "origin_lock"),
    ):
        relation = selection.selection_contract(
            draft.sketch, ({"kind": kind, "id": identifier},)
        ).action(action)
        assert relation.state == "existing" and relation.relation_ids == (expected,)
    draft.begin_edit("width_driver")
    draft.update_edit("width * 1.5")
    request = draft.solve_request(trial=True)
    response = process_request(request)
    assert response["ok"], response
    assert draft.record_validated_solution(
        request,
        response,
        draft.revision,
        expected_input_revision=draft.pending_edit.input_revision,
    )
    with pytest.raises(general.DraftError, match="full replay"):
        draft.accept_driver()
    request = draft.replay_request(trial=True)
    response = process_request(request)
    assert response["ok"], response
    assert draft.accept_driver(replay_request=request, replay_response=response).changed
    edited = Document.from_dict(draft.candidate())
    assert_plate(replay(edited), width=60)
    assert {relation.id for relation in edited.features[0].sketch.constraints} == CONSTRAINT_IDS
    assert {line.id for line in edited.features[0].sketch.lines} == LINE_IDS
    assert {point.id for point in edited.features[0].sketch.points} == POINT_IDS
    assert draft.document_json == base and document.to_json() == base


def test_origin_release_and_undo_use_current_native_evidence(document, editor_modules):
    general, _rectangle, _selection = editor_modules
    draft = general.GeneralSketchDraft(document.to_json(), "plate_outline", is_edit=True)

    def check():
        request = draft.solve_request()
        response = process_request(request)
        assert response["ok"], response
        assert draft.record_validated_solution(request, response, draft.revision)
        return response["result"]["sketch"]

    original = check()
    preview = draft.preview_delete((("constraint", "origin_lock"),))
    assert draft.execute(general.DeleteBatch(preview)).changed
    released = check()
    assert released["remaining_dof"] == 2
    assert released["solved"]["points"] == original["solved"]["points"]
    draft.undo()
    assert not draft.has_current_solution
    assert check()["remaining_dof"] == 0
    assert Document.from_dict(draft.candidate()) == document


@pytest.mark.parametrize("action,suffix", [("export_step", ".step"), ("export_stl", ".stl")])
def test_exports_replay_edited_parameters_and_pass_geometry_gates(
    document, tmp_path, action, suffix
):
    edited = document.with_parameter("width", 60)
    destination = tmp_path / f"explicit-plate-60{suffix}"
    exported = run_geometry_action(
        edited, action, destination=destination, linear_deflection=0.03, result_version=2
    )
    assert exported["ok"], exported
    assert exported["export"]["document_hash"] == edited.content_hash != document.content_hash
    assert exported["export"]["active_feature"] == "plate_body"
    assert exported["export"]["bytes"] == destination.stat().st_size > 0
    checks = exported["geometry_check"]
    assert checks["brep"]["valid"] and checks["brep"]["solids"] == 1
    assert checks["brep"]["volume"] == pytest.approx(12000)
    assert checks["mesh"]["watertight"] and checks["mesh"]["consistently_oriented"]
    if action == "export_step":
        kernel = OCPKernel()
        imported = kernel.import_step(destination)
        assert kernel.inspect(imported)["volume"] == pytest.approx(12000)
        assert _shape_bounds(imported) == pytest.approx((0, 0, 0, 60, 25, 8), abs=1e-7)
    else:
        encoded = checks["encoded_mesh"]
        assert encoded["watertight"] and encoded["consistently_oriented"]
        assert encoded["vertex_manifold"]
        assert encoded["signed_volume"] == pytest.approx(12000)
        assert destination.stat().st_size == 84 + 50 * encoded["triangles"]
        assert (
            checks["encoding"]["maximum_vertex_error_mm"]
            <= checks["encoding"]["allowed_vertex_error_mm"]
        )
