"""Feature-owned native offset walls and lip, not guessed outer-face identities."""

import copy
import importlib
import sys
import types
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature, load_document, save_document
from mechanical_cad.sidecar import process_request

package = types.ModuleType("shell_generated_client")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package


def identity(source="b/face/side.x_min", rim=False):
    return (
        "s/face/shell.opening_lip"
        if rim
        else "s/face/shell.inner." + sha256(source.encode()).hexdigest()
    )


def document(*, attached=False, circular=False, closed=False):
    features = [
        Feature("p", "sketch_circle", "Outline", {"radius": "width"})
        if circular
        else Feature("p", "sketch_rectangle", "Outline", {"width": "width", "height": 15}),
        Feature("b", "extrude", "Block", {"length": 10}, {"profile": "p"}),
        Feature(
            "s",
            "shell",
            "Enclosure",
            {"thickness": "wall"},
            {"base": "b"},
            opening_faces=None if closed else ("b/face/cap.end",),
        ),
    ]
    if attached:
        features.append(
            Feature(
                "attached",
                "sketch_face_circle",
                "Inner wall sketch",
                {"radius": 1},
                {"support": "s"},
                support_face=identity(),
            )
        )
    return Document(
        "d", "Offset wall reference", {"width": 20, "wall": 1}, tuple(features), features[-1].id
    )


@pytest.mark.parametrize("version", [2, 3])
def test_inner_wall_native_attachment_thickness_size_edit_save_replay(tmp_path, version):
    path = tmp_path / "inner_wall.mcad.json"
    save_document(document(attached=True), path)
    for width, wall in [(20, 1), (30, 2)]:
        doc = replace(load_document(path), parameters={"width": width, "wall": wall})
        kernel = OCPKernel()
        replay = regenerate(doc, kernel, result_version=version)
        assert replay.ok, replay.result
        shell = replay.result["features"][2]
        assert shell["stats"]["valid"]
        assert shell["stats"]["volume"] == pytest.approx(
            width * 150 - (width - 2 * wall) * (15 - 2 * wall) * (10 - wall)
        )
        operation = kernel._operations[id(replay.shapes["s"])]
        base = kernel._operations[id(replay.shapes["b"])]
        own = [(f, c) for f, c in operation.faces if c["feature_id"] == "s"]
        assert len(own) == 6
        for face, candidate in own:
            provenance = candidate["provenance"]
            source = next(f for f, c in base.faces if c["id"] == provenance["source_id"])
            changes = (
                operation.builder.Modified(source)
                if provenance["relation"] == "rim_from_opening"
                else operation.builder.Generated(source)
            )
            assert any(face.IsSame(image) for image in changes)
            assert not face.IsSame(source)
        origin, _ = kernel.supported_workplane(replay.shapes["s"], identity())
        assert origin == pytest.approx([wall, 7.5, (wall + 10) / 2])
        edge = kernel.projected_edge_endpoints(
            replay.shapes["s"], [sorted([identity(), identity("b/face/cap.start")])]
        )[0]
        assert len(edge["points"]) == 2
        request = {"protocol_version": 1, "result_version": version, "document": doc.to_dict()}
        response = process_request(request)
        assert response["ok"], response
        importlib.import_module(
            package.__name__ + (".part_result_bridge" if version == 2 else ".result_v3")
        ).validate_response(request, response)


def test_cylindrical_inner_wall_and_lip_circle_are_not_misrepresented_as_planes():
    kernel = OCPKernel()
    replay = regenerate(document(circular=True), kernel, result_version=3)
    assert replay.ok
    shape = replay.shapes["s"]
    inner = identity("b/face/side.circle")
    rim = identity("b/face/cap.end", rim=True)
    circle = kernel.projected_circle(shape, sorted([inner, rim]))
    assert circle["radius"] == pytest.approx(19)
    with pytest.raises(ValueError, match="planar"):
        kernel.support_face_signature(shape, inner)
    assert kernel.support_face_signature(shape, rim)["surface"] == "plane"
    request = {
        "protocol_version": 1,
        "result_version": 3,
        "document": document(circular=True).to_dict(),
    }
    importlib.import_module(package.__name__ + ".result_v3").validate_response(
        request, process_request(request)
    )


@pytest.mark.parametrize("version,closed", [(1, False), (3, True)])
def test_legacy_and_closed_shell_generated_surfaces_stay_unknown(version, closed):
    replay = regenerate(document(closed=closed), OCPKernel(), result_version=version)
    assert replay.ok
    assert not any(
        f["role"].startswith("shell.") for f in replay.result["features"][-1]["topology"]
    )


@pytest.mark.parametrize(
    "ambiguity", ["duplicate_source", "duplicate_identity", "split", "competing_source"]
)
def test_ambiguous_offset_not_promoted(ambiguity):
    kernel = OCPKernel()
    replay = regenerate(document(), kernel, result_version=3)
    shell = kernel._operations[id(replay.shapes["s"])]
    base = kernel._operations[id(replay.shapes["b"])]
    source, candidate = next((f, c) for f, c in base.faces if c["id"] == "b/face/side.x_min")
    target = next(f for f, c in shell.faces if c["id"] == identity())
    faces = [f for f, c in shell.faces]
    if ambiguity in {"duplicate_source", "duplicate_identity"}:
        other = copy.deepcopy(candidate)
        if ambiguity == "duplicate_source":
            other["id"] = "snapshot:b:face:99"
            other["provenance"]["semantic_status"] = "unknown"
            base.faces.append((source, other))
        else:
            base.faces.append(
                (next(f for f, c in base.faces if c["id"] == "b/face/side.x_max"), other)
            )
    else:
        original = shell.builder

        class AmbiguousHistory:
            def __getattr__(self, name):
                return getattr(original, name)

            def Generated(self, face):
                if face.IsSame(source):
                    return (
                        [target, next(f for f in faces if not f.IsSame(target))]
                        if ambiguity == "split"
                        else [target]
                    )
                return [target] if ambiguity == "competing_source" else original.Generated(face)

        shell.builder = AmbiguousHistory()
    assignments = kernel._open_shell_topology(shell, faces, "s")
    assert identity() not in {c["id"] for _, c in assignments}


@pytest.mark.parametrize("mutation", ["count", "role", "source", "opening", "closed"])
def test_strict_client_refuses_forged_offset_intent(mutation):
    request = {"protocol_version": 1, "result_version": 3, "document": document().to_dict()}
    response = process_request(request)
    face = next(f for f in response["result"]["features"][-1]["topology"] if f["id"] == identity())
    if mutation == "count":
        face["provenance"]["image_count"] = 2
    elif mutation == "source":
        face["provenance"]["source_id"] = "b/face/side.x_max"
    elif mutation == "role":
        face["role"] = face["role"].replace("inner", "rim")
    elif mutation == "opening":
        face["provenance"].update(relation="rim_from_opening", evolution="rim_from_opening")
    else:
        row = response["result"]["features"][-1]
        with pytest.raises(ValueError):
            importlib.import_module(package.__name__ + ".topology_evidence").validate_topology(
                row["topology"],
                feature_id="s",
                kind="shell",
                mesh=row["mesh"],
                source_features=document(closed=True).to_dict()["features"],
            )
        return
    with pytest.raises(ValueError):
        importlib.import_module(package.__name__ + ".result_v3").validate_response(
            request, response
        )


def test_inner_edge_reference_saved_and_resolved_after_thickness_change(tmp_path):
    from mechanical_cad.sketch_model import Circle, Constraint, Line, Point, SketchDefinition

    doc = document()
    kernel = OCPKernel()
    replay = regenerate(doc, kernel, result_version=3)
    pair = sorted([identity(), identity("b/face/cap.start")])
    edge = kernel.projected_edge_endpoints(replay.shapes["s"], [pair])[0]
    sketch = SketchDefinition(
        "projection",
        (Point("a", 0, 0), Point("b", 1, 0), Point("c", 0, 0)),
        (Line("ref", "a", "b", construction=True),),
        (
            Constraint("a_fixed", "fixed", ("a",), target=(0, 0)),
            Constraint("b_fixed", "fixed", ("b",), target=(1, 0)),
            Constraint("c_fixed", "fixed", ("c",), target=(0, 0)),
            Constraint("radius", "radius", ("circle",), 1),
        ),
        schema_version=2,
        circles=(Circle("circle", "c", 1),),
    )
    projection = Feature(
        "projection",
        "sketch_constrained",
        "Inner wall reference",
        {},
        {"external": "s"},
        sketch=sketch,
        projections=({"faces": pair, "endpoint_faces": edge["endpoint_faces"], "target": "ref"},),
    )
    doc = replace(
        doc, schema_version=2, features=(*doc.features, projection), active_feature="projection"
    )
    path = tmp_path / "inner_reference.mcad.json"
    save_document(doc, path)
    for wall in [1, 2]:
        edited = replace(load_document(path), parameters={"width": 30, "wall": wall})
        request = {"protocol_version": 1, "result_version": 3, "document": edited.to_dict()}
        response = process_request(request)
        assert response["ok"], response
        importlib.import_module(package.__name__ + ".result_v3").validate_response(
            request, response
        )
        points = {
            p["id"]: p for p in response["result"]["features"][-1]["sketch"]["solved"]["points"]
        }
        assert points["a"]["u"] == pytest.approx(wall)
        assert points["b"]["u"] == pytest.approx(wall)
        assert abs(points["b"]["v"] - points["a"]["v"]) == pytest.approx(15 - 2 * wall)


def test_changing_opening_does_not_reinterpret_inner_wall_as_lip():
    doc = document(attached=True)
    shell = replace(doc.features[2], opening_faces=("b/face/side.x_min",))
    changed = replace(doc, features=(*doc.features[:2], shell, doc.features[3]))
    replay = regenerate(changed, OCPKernel(), result_version=3)
    assert not replay.ok
    assert replay.result["features"][2]["status"] == "ok"
    assert replay.result["features"][-1]["status"] == "failed"
    assert identity() not in {f["id"] for f in replay.result["features"][2]["topology"]}


def test_output_enumeration_never_changes_constructed_identity():
    kernel = OCPKernel()
    replay = regenerate(document(), kernel, result_version=3)
    shell = kernel._operations[id(replay.shapes["s"])]
    faces = [f for f, _ in shell.faces]
    before = {c["id"]: c for _, c in kernel._open_shell_topology(shell, faces, "s")}
    after = {c["id"]: c for _, c in kernel._open_shell_topology(shell, list(reversed(faces)), "s")}
    assert before == after


@pytest.mark.parametrize("version", [2, 3])
def test_lip_intent_follows_deliberately_changed_current_opening(tmp_path, version):
    doc = document()
    attached = Feature(
        "attached",
        "sketch_face_circle",
        "On current lip",
        {"radius": 0.25},
        {"support": "s"},
        support_face=identity(rim=True),
    )
    doc = replace(doc, features=(*doc.features, attached), active_feature="attached")
    for role, normal in [("cap.end", [0, 0, 1]), ("side.x_min", [-1, 0, 0])]:
        opening = "b/face/" + role
        shell = replace(doc.features[2], opening_faces=(opening,))
        changed = replace(doc, features=(*doc.features[:2], shell, attached))
        path = tmp_path / (role + ".mcad.json")
        save_document(changed, path)
        restored = load_document(path)
        kernel = OCPKernel()
        replay = regenerate(restored, kernel, result_version=version)
        assert replay.ok, replay.result
        lip = next(
            f for f in replay.result["features"][2]["topology"] if f["id"] == identity(rim=True)
        )
        assert lip["provenance"]["source_id"] == opening
        assert lip["provenance"]["relation"] == "rim_from_opening"
        assert lip["signature"]["normal"] == pytest.approx(normal)
        assert restored.features[-1].support_face == identity(rim=True)
        request = {"protocol_version": 1, "result_version": version, "document": restored.to_dict()}
        response = process_request(request)
        validator = importlib.import_module(
            package.__name__ + (".part_result_bridge" if version == 2 else ".result_v3")
        )
        validator.validate_response(request, response)
        # A previously selected face cannot masquerade as the current opening's lip.
        forged = copy.deepcopy(response)
        target = next(
            f for f in forged["result"]["features"][2]["topology"] if f["id"] == identity(rim=True)
        )
        target["provenance"]["source_id"] = "b/face/cap.start"
        with pytest.raises(ValueError):
            validator.validate_response(request, forged)


def test_split_lip_history_does_not_choose_a_fragment():
    kernel = OCPKernel()
    replay = regenerate(document(), kernel, result_version=3)
    operation = kernel._operations[id(replay.shapes["s"])]
    faces = [f for f, _ in operation.faces]
    base = kernel._operations[id(replay.shapes["b"])]
    opening = next(f for f, c in base.faces if c["id"] == "b/face/cap.end")
    original = operation.builder

    class SplitLipHistory:
        def __getattr__(self, name):
            return getattr(original, name)

        def Modified(self, face):
            return faces[:2] if face.IsSame(opening) else original.Modified(face)

    operation.builder = SplitLipHistory()
    assert identity(rim=True) not in {
        c["id"] for _, c in kernel._open_shell_topology(operation, faces, "s")
    }
