"""Focused exact circular-arc reference replay; run only with native scope."""
import copy
import json
import math

import pytest
from test_sketch_corner_fillet import c, d, positions


def source_document():
    draft = d.GeneralSketchDraft(json.dumps({"schema_version": 1, "id": "doc", "name": "Arc reference",
        "units": "mm", "parameters": {}, "features": [], "active_feature": None}), journal_version=3)
    draft.execute(c.AddRectangle(c.PointSeed(0, 0), c.PointSeed(20, 10)))
    points = [p["id"] for p in draft.sketch["points"]]
    draft.execute(c.AddRelation("fixed", (points[0],), target=(0, 0)))
    draft.execute(c.AddRelation("distance", (points[0], points[1]), value=20))
    draft.execute(c.AddRelation("distance", (points[1], points[2]), value=10))
    draft.execute(c.CornerFillet(tuple(line["id"] for line in draft.sketch["lines"][:2]), 2, positions(draft)))
    document = draft.candidate()
    document["features"].append({"id": "pad", "kind": "extrude", "label": "Plate",
        "params": {"length": 5}, "inputs": {"profile": draft.feature_id}})
    document["active_feature"] = "pad"
    return document


def catalog(document, arcs=True):
    import importlib

    from test_solid_edge_projection import bridge

    from mechanical_cad.sidecar import process_request

    request = {"protocol_version": 1, "result_version": 3, "action": "edge_catalog",
               "document": document, "options": {"linear_deflection": .1}}
    if arcs:
        request["options"]["projection_arcs"] = True
    response = process_request(request)
    assert response["ok"], response
    bridge()
    validator = importlib.import_module("mcad_solid_projection_test.edge_catalog_bridge")
    validator.validate_response(request, response)
    return request, response


def projected_document():
    document = source_document()
    _, response = catalog(document)
    entries = [entry for entry in response["result"]["catalogs"]["pad"] if "arc" in entry]
    assert len(entries) == 2  # Both extrusion caps, never an invented side seam.
    entry = max(entries, key=lambda item: item["arc"]["center"][2])
    evidence = entry["arc"]
    draft = d.GeneralSketchDraft(json.dumps(document), journal_version=3)
    points = (evidence["center"], *evidence["points"])
    draft.project_solid_arc("pad", entry["faces"], evidence["endpoint_faces"],
        c.AddProjectionGeometry("arc", tuple(c.PointSeed(*p[:2]) for p in points),
                                direction="ccw" if evidence["sweep"] > 0 else "cw"))
    return draft.candidate(), draft.feature_id, entry


def test_native_fillet_arc_save_reopen_radius_size_edits(tmp_path):
    from test_solid_edge_projection import bridge

    from mechanical_cad.model import Document, load_document, save_document
    from mechanical_cad.sidecar import process_request

    document, feature_id, entry = projected_document()
    path = tmp_path / "arc-reference.mcad.json"
    save_document(Document.from_dict(document), path)
    restored = load_document(path).to_dict()
    reference = next(f for f in restored["features"] if f["id"] == feature_id)
    assert reference["projections"][0]["endpoint_faces"] == entry["arc"]["endpoint_faces"]
    assert "fillet_intent" not in reference["sketch"]["arcs"][0]
    for radius, width in ((2, 20), (3, 25)):
        edited = copy.deepcopy(restored)
        constraints = edited["features"][0]["sketch"]["constraints"]
        next(r for r in constraints if r["kind"] == "radius")["value"] = radius
        next(r for r in constraints if r["kind"] == "distance")["value"] = width
        request = {"protocol_version": 1, "result_version": 3, "document": edited}
        response = process_request(request)
        assert response["ok"], response
        bridge()[1].validate_response(request, response)
        result = next(f for f in response["result"]["features"] if f["id"] == feature_id)
        assert result["projection_edges"][0]["radius"] == pytest.approx(radius)
        assert abs(result["projection_edges"][0]["sweep"]) == pytest.approx(math.pi/2)
        solid = next(f for f in response["result"]["features"] if f["id"] == "pad")
        assert solid["stats"]["volume"] == pytest.approx((width*10-radius**2*(1-math.pi/4))*5)
        assert solid["stats"]["valid"]


def test_legacy_catalog_never_emits_arc_metadata():
    document = source_document()
    _, legacy = catalog(document, False)
    assert not any("arc" in row for rows in legacy["result"]["catalogs"].values() for row in rows)
    request, current = catalog(document)
    assert any("arc" in row for row in current["result"]["catalogs"]["pad"])
    import importlib
    validator = importlib.import_module("mcad_solid_projection_test.edge_catalog_bridge")
    legacy_request = {**request, "options": {"linear_deflection": .1}}
    bad = copy.deepcopy(current)
    bad["input_fingerprint"] = validator.part_contracts.input_fingerprint(legacy_request)
    with pytest.raises(ValueError):
        validator.validate_response(legacy_request, bad)


@pytest.mark.parametrize("flip", [False, True])
@pytest.mark.parametrize("normal_flip", [False, True])
def test_native_arc_endpoint_flip_and_parallel_normal(flip, normal_flip):
    from test_solid_edge_projection import bridge

    from mechanical_cad.sidecar import process_request
    document, feature_id, entry = projected_document()
    feature = next(f for f in document["features"] if f["id"] == feature_id)
    feature["projections"][0]["reverse"] = flip
    if normal_flip:
        feature["sketch"]["plane"]["quaternion"] = [0, 1, 0, 0]
    request = {"protocol_version": 1, "result_version": 3, "document": document}
    response = process_request(request)
    assert response["ok"], response
    bridge()[1].validate_response(request, response)
    result = next(f for f in response["result"]["features"] if f["id"] == feature_id)
    solved = result["sketch"]["solved"]
    arc = solved["arcs"][0]
    points = {p["id"]: (p["u"], p["v"]) for p in solved["points"]}
    expected = entry["arc"]["points"][::-1] if flip else entry["arc"]["points"]
    for role, point in zip(("start", "end"), expected, strict=True):
        assert points[arc[role]] == pytest.approx((point[0], -point[1] if normal_flip else point[1]))


def native_source():
    from mechanical_cad.engine import regenerate
    from mechanical_cad.kernel_ocp import OCPKernel
    from mechanical_cad.model import Document

    kernel = OCPKernel()
    replay = regenerate(Document.from_dict(source_document()), kernel, result_version=3)
    assert replay.ok, replay.result
    shape = replay.shapes["pad"]
    entry = next(e for e in kernel.edge_display_catalog(shape, projection_arcs=True) if "arc" in e)
    return kernel, shape, entry


@pytest.mark.parametrize("mutation", ["missing", "split", "alias", "merged"])
def test_native_endpoint_identity_mutations_refuse(mutation):
    from mechanical_cad.kernel_ocp import KernelError

    kernel, shape, entry = native_source()
    operation = kernel._operations[id(shape)]
    identifier = entry["arc"]["endpoint_faces"][0][0]
    index = next(i for i, (_, row) in enumerate(operation.faces) if row["id"] == identifier)
    face, original = operation.faces[index]
    replacement = copy.deepcopy(original)
    if mutation == "missing":
        operation.faces.pop(index)
    elif mutation == "split":
        replacement["provenance"]["semantic_status"] = "split"
        operation.faces[index] = (face, replacement)
    elif mutation == "merged":
        other_id = entry["arc"]["endpoint_faces"][1][0]
        other_index = next(i for i, (_, row) in enumerate(operation.faces) if row["id"] == other_id)
        other_face, other = operation.faces[other_index]
        replacement = copy.deepcopy(other)
        replacement["id"] = identifier
        operation.faces[other_index] = (other_face, replacement)
    else:
        replacement["id"] += ".alias"
        operation.faces.append((face, replacement))
    with pytest.raises(KernelError, match="endpoint"):
        kernel.projected_arc(shape, entry["faces"])


def test_native_reversed_edge_and_face_traversal_retains_roles(monkeypatch):
    kernel, shape, entry = native_source()
    expected = kernel.projected_arc(shape, entry["faces"])
    operation = kernel._operations[id(shape)]
    operation.faces = [(face.Reversed(), row) for face, row in operation.faces]
    assert kernel.projected_arc(shape, entry["faces"]) == expected
    selected = kernel._selected_edges(shape, entry["faces"])[0]
    monkeypatch.setattr(kernel, "_selected_edges", lambda shape, faces: [selected.Reversed()])
    assert kernel.projected_arc(shape, entry["faces"]) == expected


def major_document(*, chord=False):
    from mechanical_cad.model import Document, Feature
    from mechanical_cad.sketch_model import Arc, Constraint, Line, Point, SketchDefinition

    sketch = SketchDefinition("sector", (Point("c", 0, 0), Point("s", 2, 0), Point("e", 0, -2)),
        ((Line("chord", "e", "s"),) if chord else (Line("back", "e", "c"), Line("out", "c", "s"))),
        tuple(Constraint("fix_"+name, "fixed", (name,), target=point)
              for name, point in (("c", (0, 0)), ("s", (2, 0)), ("e", (0, -2)))),
        schema_version=3, arcs=(Arc("rim", "c", "s", "e", "ccw"),))
    document = Document("major", "Major sector", {},
        (Feature("sector", "sketch_constrained", "Sector", {}, sketch=sketch),
         Feature("pad", "extrude", "Sector pad", {"length": 5}, {"profile": "sector"})),
        "pad", schema_version=2)
    return document


def test_native_major_arc_retains_sweep():
    _, response = catalog(major_document().to_dict())
    arcs = [entry["arc"] for entry in response["result"]["catalogs"]["pad"] if "arc" in entry]
    assert len(arcs) == 2
    assert all(abs(arc["sweep"]) == pytest.approx(1.5*math.pi) for arc in arcs)


def test_native_explicit_repair_retains_dependent_profile_and_solve():
    from test_solid_edge_projection import bridge

    from mechanical_cad.projection_repair import replace_reference
    from mechanical_cad.sidecar import process_request

    document, feature_id, entry = projected_document()
    target = next(f for f in document["features"] if f["id"] == feature_id)
    arc = target["sketch"]["arcs"][0]
    center = entry["arc"]["center"]
    target["sketch"]["points"].append({"id": "bore_center", "u": center[0], "v": center[1]})
    target["sketch"]["circles"].append({"id": "bore", "center": "bore_center", "radius": .5})
    target["sketch"]["constraints"].extend([
        {"id": "follow_center", "kind": "coincident", "refs": [arc["center"], "bore_center"]},
        {"id": "bore_radius", "kind": "radius", "refs": ["bore"], "value": .5}])
    document["features"].append({"id": "boss", "kind": "extrude", "label": "Dependent boss",
        "params": {"length": 2}, "inputs": {"profile": feature_id}})
    document["active_feature"] = "boss"
    saved_row = copy.deepcopy(target["projections"][0])
    target["projections"][0]["endpoint_faces"] = [["missing.a"], ["missing.b"]]
    request = {"protocol_version": 1, "result_version": 3, "document": document}
    failed = process_request(request)
    assert not failed["ok"]
    assert next(f for f in failed["result"]["features"] if f["id"] == "boss")["status"] == "blocked"
    repaired = replace_reference(document, feature_id, arc["id"],
        {k:v for k,v in saved_row.items() if k != "target"}, source_id="pad",
        edge={"kind": "arc", "faces": entry["faces"], **entry["arc"]}, reverse=True)
    request["document"] = repaired
    result = process_request(request)
    assert result["ok"], result
    bridge()[1].validate_response(request, result)
    assert result["result"]["features"][-1]["stats"]["volume"] == pytest.approx(math.pi*.5**2*2)
    solved = process_request({**request, "action": "solve_sketch", "feature_id": feature_id})
    assert solved["ok"], solved
    bridge()[1].validate_solve_response(solved, {**request, "action": "solve_sketch", "feature_id": feature_id})
    repaired_target = next(f for f in repaired["features"] if f["id"] == feature_id)
    assert repaired_target["sketch"]["constraints"][-2:] == target["sketch"]["constraints"][-2:]


def test_guarded_native_arc_catalog_admits_capability():
    import importlib

    from test_solid_edge_projection import bridge

    from mechanical_cad.sidecar import process_request

    bridge()
    contracts = importlib.import_module("mcad_solid_projection_test.backend_contracts")
    request = {"protocol_version": 1, "result_version": 3, "action": "edge_catalog",
               "document": source_document(),
               "options": {"linear_deflection": .1, "projection_arcs": True}}
    guarded = contracts.compose_request(request)
    response = process_request(guarded)
    assert response["ok"], response
    assert "mcad.solid-arc-projection/1" in response["backend_receipt"]["confirmed_capabilities"]


def test_persisted_arc_replays_after_target_normal_edit(tmp_path):
    from test_solid_edge_projection import bridge

    from mechanical_cad.model import Document, load_document, save_document
    from mechanical_cad.sidecar import process_request

    document, feature_id, _ = projected_document()
    request = {"protocol_version": 1, "result_version": 3, "document": document}
    initial = process_request(request)
    assert initial["ok"], initial
    bridge()[1].validate_response(request, initial)
    before = next(f for f in initial["result"]["features"] if f["id"] == feature_id)["sketch"]["solved"]
    path = tmp_path / "normal-edit.mcad.json"
    save_document(Document.from_dict(document), path)
    changed = load_document(path).to_dict()
    feature = next(f for f in changed["features"] if f["id"] == feature_id)
    saved_arc = copy.deepcopy(feature["sketch"]["arcs"][0])
    saved_points = copy.deepcopy(feature["sketch"]["points"])
    feature["sketch"]["plane"]["quaternion"] = [0, 1, 0, 0]
    request["document"] = changed
    after_response = process_request(request)
    assert after_response["ok"], after_response
    bridge()[1].validate_response(request, after_response)
    after = next(f for f in after_response["result"]["features"] if f["id"] == feature_id)["sketch"]["solved"]
    assert after["arcs"][0]["direction"] != before["arcs"][0]["direction"]
    for role in ("center", "start", "end"):
        assert after["arcs"][0][role] == before["arcs"][0][role] == saved_arc[role]
    before_points = {p["id"]: p for p in before["points"]}
    for point in after["points"]:
        old = before_points[point["id"]]
        assert (point["u"], point["v"]) == pytest.approx((old["u"], -old["v"]))
    assert feature["sketch"]["arcs"][0] == saved_arc
    assert feature["sketch"]["points"] == saved_points


def test_chord_only_major_arc_refuses_ambiguous_endpoints():
    from mechanical_cad.engine import regenerate
    from mechanical_cad.kernel_ocp import KernelError, OCPKernel

    kernel = OCPKernel()
    replay = regenerate(major_document(chord=True), kernel, result_version=3)
    assert replay.ok, replay.result
    shape = replay.shapes["pad"]
    display = kernel.edge_display_catalog(shape, projection_arcs=True)
    curved = [entry for entry in display if len(entry["points"]) > 2]
    assert len(curved) == 2
    assert not any("arc" in entry for entry in curved)
    for entry in curved:
        with pytest.raises(KernelError, match="ambiguous incident-face identity"):
            kernel.projected_arc(shape, entry["faces"])
