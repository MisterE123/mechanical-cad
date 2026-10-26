"""Pure analytic arc projection boundaries; no kernel or solver imports."""
import copy
import math

import pytest

from mechanical_cad.sketch_projection import project_solid_edges, validate_solid_edges


def fixture(sweep=math.pi / 2):
    row = {"kind": "arc", "faces": ["cap", "wall"],
           "endpoint_faces": [["left"], ["right"]], "target": "ref"}
    edge = {**{k: v for k, v in row.items() if k != "target"},
            "center": [0, 0, 4], "normal": [0, 0, 1], "radius": 2,
            "points": [[2, 0, 4], [2 * math.cos(sweep), 2 * math.sin(sweep), 4]],
            "sweep": sweep}
    sketch = {"plane": {"origin": [0, 0, 9], "quaternion": [1, 0, 0, 0]},
              "points": [{"id": name, "u": 0, "v": 0} for name in ("c", "a", "b")],
              "lines": [], "circles": [], "arcs": [{"id": "ref", "center": "c",
              "start": "a", "end": "b", "direction": "ccw", "construction": True}],
              "constraints": [{"id": "fix_"+name, "kind": "fixed", "refs": [name],
                               "target": [0, 0]} for name in ("c", "a", "b")]}
    return sketch, edge, row


@pytest.mark.parametrize("sweep", [math.pi/2, -math.pi/2, 3*math.pi/2, -3*math.pi/2, math.pi])
@pytest.mark.parametrize("flip", [False, True])
@pytest.mark.parametrize("normal_flip", [False, True])
def test_arc_roles_and_branch(sweep, flip, normal_flip):
    sketch, edge, row = fixture(sweep)
    original = copy.deepcopy(sketch)
    row["reverse"] = flip
    if normal_flip:
        sketch["plane"]["quaternion"] = [0, 1, 0, 0]
    result = project_solid_edges(sketch, [edge], [row])
    points = {p["id"]: (p["u"], p["v"]) for p in result["points"]}
    expected = edge["points"][::-1] if flip else edge["points"]
    for name, point in zip(("a", "b"), expected, strict=True):
        assert points[name] == pytest.approx((point[0], -point[1] if normal_flip else point[1]))
    sign = sweep * (-1 if flip else 1) * (-1 if normal_flip else 1)
    assert result["arcs"][0]["direction"] == ("ccw" if sign > 0 else "cw")
    assert sketch["points"] == original["points"]
    assert result["arcs"][0]["start"] == "a"


@pytest.mark.parametrize("key,value", [("sweep", 0), ("sweep", 2*math.pi),
                                        ("sweep", math.pi), ("radius", 4),
                                        ("normal", [1, 0, 0])])
def test_bad_analytic_evidence_refused(key, value):
    sketch, edge, row = fixture()
    edge[key] = value
    with pytest.raises(ValueError):
        project_solid_edges(sketch, [edge], [row])


def test_changed_identity_and_oblique_refused():
    sketch, edge, row = fixture()
    bad = copy.deepcopy(edge)
    bad["endpoint_faces"] = [["new"], ["right"]]
    with pytest.raises(ValueError, match="identity changed"):
        validate_solid_edges([bad], [row])
    sketch["plane"]["quaternion"] = [math.cos(.2), math.sin(.2), 0, 0]
    with pytest.raises(ValueError, match="parallel"):
        project_solid_edges(sketch, [edge], [row])


def test_arc_command_checkpoint_undo_and_explicit_repair():
    import json

    from test_solid_projection_owner import C, D, document

    from mechanical_cad.model import Document
    from mechanical_cad.projection_repair import replace_reference

    _, edge, row = fixture()
    draft = D.GeneralSketchDraft(json.dumps(document()), journal_version=3)
    command = C.AddProjectionGeometry("arc", (C.PointSeed(0, 0), C.PointSeed(2, 0), C.PointSeed(0, 2)))
    outcome = draft.project_solid_arc("pad", row["faces"], row["endpoint_faces"], command)
    assert len(outcome.entity_ids) == 4
    target = outcome.entity_ids[-1]
    data = draft.candidate()
    feature = data["features"][-1]
    assert feature["sketch"]["arcs"][0]["construction"] is True
    assert len(feature["sketch"]["constraints"]) == 3
    assert Document.from_dict(data).to_dict()["features"][-1]["projections"] == feature["projections"]
    restored = D.GeneralSketchDraft.from_checkpoint_payload(draft.checkpoint_payload(), expected_journal_version=3)
    assert restored.candidate() == data
    restored.undo()
    restored.redo()
    assert restored.candidate() == data
    with pytest.raises(ValueError, match="direction follows"):
        restored.execute(C.ReverseArcSweep(target))
    repaired = replace_reference(data, feature["id"], target,
        {k:v for k,v in row.items() if k != "target"}, source_id="pad", edge=edge, reverse=True)
    assert repaired["features"][-1]["sketch"]["arcs"][0]["direction"] == "cw"


def test_arc_capability_is_explicit_and_matches_backend():
    from test_solid_projection_owner import load

    from mechanical_cad.backend_contract import minimum_capabilities

    client = load("backend_contracts")
    operation = {"protocol_version": 1, "result_version": 3, "action": "edge_catalog",
                 "options": {"linear_deflection": .1}, "document": {"features": []}}
    capability = "mcad.solid-arc-projection/1"
    assert capability not in minimum_capabilities(operation)
    assert capability not in client.minimum_capabilities(operation)
    operation["options"]["projection_arcs"] = True
    assert capability in minimum_capabilities(operation)
    assert capability in client.minimum_capabilities(operation)
    del operation["options"]["projection_arcs"]
    operation["document"]["features"] = [{"projections": [fixture()[2]]}]
    assert capability in minimum_capabilities(operation)
    assert capability in client.minimum_capabilities(operation)
    del operation["document"]
    assert capability not in minimum_capabilities(operation)
    assert capability not in client.minimum_capabilities(operation)


def test_duplicate_topology_identity_refuses():
    _, edge, row = fixture()
    topology = [{"id": face, "provenance": {"semantic_status": "stable"}}
                for face in ("cap", "wall", "left", "right", "left")]
    with pytest.raises(ValueError, match="aliased"):
        validate_solid_edges([edge], [row], topology)


def test_staged_arc_repair_keeps_unrelated_geometry():
    from test_solid_projection_owner import load

    from mechanical_cad.projection_repair import replace_reference

    sketch, edge, row = fixture()
    feature = {"id": "target", "kind": "sketch_constrained", "inputs": {"external": "pad"},
               "sketch": sketch, "projections": [row]}
    document = {"features": [feature]}
    repaired = replace_reference(document, "target", "ref", {k:v for k,v in row.items() if k != "target"},
                                 source_id="pad", edge=edge, reverse=True)
    scope = load("repair_scope")
    assert scope.repair_target(feature, repaired["features"][0]) == "ref"
    bad = copy.deepcopy(repaired["features"][0])
    bad["sketch"]["arcs"][0]["start"] = "b"
    with pytest.raises(ValueError, match="unrelated"):
        scope.repair_target(feature, bad)


def test_arc_row_and_saved_scaffold_strictness():
    import json

    from test_solid_projection_owner import C, D, document

    _, _, row = fixture()
    draft = D.GeneralSketchDraft(json.dumps(document()), journal_version=3)
    result = draft.project_solid_arc("pad", row["faces"], row["endpoint_faces"],
        C.AddProjectionGeometry("arc", (C.PointSeed(0, 0), C.PointSeed(2, 0), C.PointSeed(0, 2))))
    target = result.entity_ids[-1]
    with pytest.raises(ValueError, match="construction"):
        draft.execute(C.SetConstruction((("arc", target),), False))
    checkpoint = draft.checkpoint_payload()
    bad = copy.deepcopy(checkpoint)
    # Canonical source bindings reject unknown authority fields even if a saved
    # journal contains a geometrically plausible local construction arc.
    bad["external"]["projections"][0]["cached_native_edge"] = "forged"
    with pytest.raises(ValueError):
        D.GeneralSketchDraft.from_checkpoint_payload(bad, expected_journal_version=3)


@pytest.mark.parametrize("extra", ["kind", "faces", "authority"])
def test_catalog_nested_arc_payload_rejects_extra_fields(monkeypatch, extra):
    from test_solid_projection_owner import load

    validator = load("edge_catalog_bridge")
    monkeypatch.setattr(validator.result_v3, "validate_response", lambda request, response: None)
    _, edge, _ = fixture()
    payload = {k: v for k, v in edge.items() if k not in {"kind", "faces"}}
    payload[extra] = edge.get(extra, "forged")
    request = {"protocol_version": 1, "result_version": 3, "action": "edge_catalog",
               "document": {}, "options": {"linear_deflection": .1, "projection_arcs": True}}
    response = {"protocol_version": 1, "result_version": 3, "action": "edge_catalog", "ok": True,
                "error": None, "input_fingerprint": validator.part_contracts.input_fingerprint(request),
                "result": {"replay": {"features": [{"id": "pad", "output": {"kind": "solid"},
                    "topology": [{"id": face, "kind": "face", "provenance": {"semantic_status": "stable"}}
                                 for face in ("cap", "wall", "left", "right")]}]},
                    "catalogs": {"pad": [{"faces": edge["faces"], "points": edge["points"], "arc": payload}]}}}
    with pytest.raises(ValueError):
        validator.validate_response(request, response)
