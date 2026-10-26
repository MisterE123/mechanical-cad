"""Open shells retain exact unchanged outside faces, not offset walls or rims."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature
from mechanical_cad.sidecar import process_request

package = types.ModuleType("shell_lineage_client")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
validator = importlib.import_module(package.__name__ + ".part_result_bridge")
validator3 = importlib.import_module(package.__name__ + ".result_v3")


def document(thickness=1, width=20, *, closed=False, sketch=False):
    features = [
        Feature("p", "sketch_rectangle", "P", {"width": width, "height": 15}),
        Feature("b", "extrude", "B", {"length": 10}, {"profile": "p"}),
        Feature(
            "s",
            "shell",
            "S",
            {"thickness": thickness},
            {"base": "b"},
            opening_faces=None if closed else ("b/face/cap.end",),
        ),
    ]
    if sketch:
        features.append(
            Feature(
                "attached",
                "sketch_face_circle",
                "On outside wall",
                {"radius": 2},
                {"support": "s"},
                support_face="b/face/side.x_min",
            )
        )
    return Document("d", "Enclosure", {}, tuple(features), features[-1].id)


@pytest.mark.parametrize("thickness,width", [(1, 20), (2, 30)])
def test_exact_outer_native_identity_and_face_support_survive_edits(thickness, width):
    kernel = OCPKernel()
    replay = regenerate(document(thickness, width, sketch=True), kernel, result_version=3)
    assert replay.ok, replay.result
    base = kernel._operations[id(replay.shapes["b"])]
    shell = kernel._operations[id(replay.shapes["s"])]
    stable = [
        (f, c)
        for f, c in shell.faces
        if c["provenance"]["semantic_status"] == "stable" and c["feature_id"] != "s"
    ]
    assert len(stable) == 5
    assert "b/face/cap.end" not in {c["id"] for _, c in shell.faces}
    for face, candidate in stable:
        source, old = next((f, c) for f, c in base.faces if c["id"] == candidate["id"])
        assert face.IsSame(source) and not shell.builder.IsDeleted(source)
        assert not list(shell.builder.Modified(source))
        assert candidate["signature"] == old["signature"]
        assert candidate["provenance"]["relation"] == "unchanged"
    # The same supported_workplane seam is used by associative mate frames.
    origin, quaternion = kernel.supported_workplane(replay.shapes["s"], "b/face/side.x_min")
    assert origin == pytest.approx([0, 7.5, 5])
    assert len(quaternion) == 4
    unresolved = [c for _, c in shell.faces if c["provenance"]["semantic_status"] != "stable"]
    assert len(unresolved) == 0
    assert sum(c["role"].startswith("shell.") for _, c in shell.faces) == 6
    assert all(c["id"].startswith("snapshot:s:") for c in unresolved)


@pytest.mark.parametrize("version", [2, 3])
def test_strict_client_accepts_open_shell_and_downstream_attached_sketch(version):
    request = {
        "protocol_version": 1,
        "result_version": version,
        "document": document(sketch=True).to_dict(),
    }
    response = process_request(request)
    assert response["ok"], response
    validate = validator.validate_response if version == 2 else validator3.validate_response
    validate(request, response)


@pytest.mark.parametrize("mutation", ["modified", "split", "signature", "removed_lid", "closed"])
def test_strict_client_rejects_false_outer_identity(mutation):
    request = {"protocol_version": 1, "result_version": 2, "document": document().to_dict()}
    response = process_request(request)
    assert response["ok"], response
    forged = copy.deepcopy(response)
    row = forged["result"]["features"][-1]
    face = next(f for f in row["topology"] if f["id"] == "b/face/side.x_min")
    if mutation == "modified":
        face["provenance"].update(relation="modified", evolution="modified")
    elif mutation == "split":
        face["provenance"]["image_count"] = 2
    elif mutation == "signature":
        face["signature"]["centroid"][0] = 1
    elif mutation == "removed_lid":
        old = face["id"]
        face.update(id="b/face/cap.end", role="cap.end")
        face["provenance"]["source_id"] = face["id"]
        row["mesh"]["triangle_face_ids"] = [
            face["id"] if x == old else x for x in row["mesh"]["triangle_face_ids"]
        ]
    else:
        # Direct strict topology validation checks canonical mode, without
        # unrelated document-hash rejection masking the ancestry rejection.
        evidence = importlib.import_module(package.__name__ + ".topology_evidence")
        source = document(closed=True).to_dict()["features"]
        with pytest.raises(ValueError):
            evidence.validate_topology(
                row["topology"],
                feature_id="s",
                kind="shell",
                mesh=row["mesh"],
                source_features=source,
            )
        return
    with pytest.raises(ValueError):
        validator.validate_response(request, forged)


def test_legacy_closed_shell_retains_snapshot_only_topology():
    kernel = OCPKernel()
    replay = regenerate(document(closed=True), kernel, result_version=3)
    assert replay.ok
    assert all(
        face["id"].startswith("snapshot:s:") for face in replay.result["features"][-1]["topology"]
    )


@pytest.mark.parametrize("ambiguity", ["duplicate_source", "duplicate_identity", "multiple_images"])
def test_ambiguous_native_identity_is_not_promoted(ambiguity):
    kernel = OCPKernel()
    replay = regenerate(document(), kernel, result_version=3)
    base = kernel._operations[id(replay.shapes["b"])]
    shell = kernel._operations[id(replay.shapes["s"])]
    source, candidate = next((f, c) for f, c in base.faces if c["id"] == "b/face/side.x_min")
    outputs = [f for f, _ in shell.faces]
    if ambiguity == "duplicate_source":
        # Two source descriptors claim the same native face, even if one is unresolved.
        other = copy.deepcopy(candidate)
        other["id"] = "snapshot:b:face:99"
        other["provenance"]["semantic_status"] = "unknown"
        base.faces.append((source, other))
    elif ambiguity == "duplicate_identity":
        other_face = next(f for f, c in base.faces if c["id"] == "b/face/side.x_max")
        base.faces.append((other_face, copy.deepcopy(candidate)))
    else:
        outputs.append(source)
    assignments = kernel._open_shell_topology(shell, outputs, "s")
    assert candidate["id"] not in {c["id"] for _, c in assignments}
