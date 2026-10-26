"""Native boolean ancestry must not confuse copied semantic names with identity."""

import pytest

from mechanical_cad.kernel_ocp import KernelError, OCPKernel


def box(kernel, name, x=0, width=10, height=10, length=10):
    profile = kernel.rectangle(width, height, x=x)
    kernel.topology(profile, name + "_profile", "sketch_rectangle", {})
    solid = kernel.extrude(profile, length)
    kernel.topology(solid, name, "extrude", {})
    return solid


@pytest.mark.parametrize("kind", ["union", "intersection"])
def test_boolean_retains_only_proven_unique_operand_faces(kind):
    kernel = OCPKernel()
    a, b = box(kernel, "a"), box(kernel, "b", x=5)
    shape = getattr(kernel, kind)(a, b)
    topology = kernel.topology(shape, "boolean", kind, {})
    stable = {
        face["id"]: face for face in topology if face["provenance"]["semantic_status"] == "stable"
    }
    expected = (
        {"a/face/side.x_min", "b/face/side.x_max"}
        if kind == "union"
        else {"b/face/side.x_min", "a/face/side.x_max"}
    )
    assert expected <= stable.keys()
    for identifier in expected:
        assert stable[identifier]["provenance"]["operation"] == kind
        profile = kernel.face_circle(shape, identifier, 1)
        assert kernel.inspect(kernel.extrude(profile, 1))["volume"] == pytest.approx(
            3.141592653589793
        )
    # Simplifying coplanar overlapping faces does not give either source sole ownership.
    assert any(face["provenance"]["semantic_status"] == "merged" for face in topology)
    assert "a/face/cap.end" not in stable and "b/face/cap.end" not in stable


@pytest.mark.parametrize("width", [10, 15])
@pytest.mark.parametrize("kind", ["union", "intersection"])
def test_transformed_copy_duplicate_semantic_ids_never_become_stable(kind, width):
    kernel = OCPKernel()
    original = box(kernel, "original", width=width)
    copied = kernel.transform(original, x=5)
    kernel.topology(copied, "copy", "transform", {})
    shape = getattr(kernel, kind)(original, copied)
    topology = kernel.topology(shape, "boolean", kind, {})
    assert not any(face["provenance"]["semantic_status"] == "stable" for face in topology)
    assert all(face["id"].startswith("snapshot:boolean:") for face in topology)
    with pytest.raises(KernelError, match="ambiguous"):
        kernel.face_circle(shape, "original/face/cap.end", 1)


def test_same_physical_operand_twice_does_not_create_false_ambiguity():
    kernel = OCPKernel()
    base = box(kernel, "base")
    shape = kernel.union(base, base)
    faces = kernel.topology(shape, "union", "union", {})
    assert len(faces) == 6
    assert all(face["provenance"]["semantic_status"] == "stable" for face in faces)
    assert len({face["id"] for face in faces}) == 6


@pytest.mark.parametrize("angle", [180, 360])
def test_revolve_construction_history_has_only_real_caps_and_boundary_faces(angle):
    kernel = OCPKernel()
    profile = kernel.rectangle(2, 5, x=3)
    kernel.topology(profile, "section", "sketch_rectangle", {})
    solid = kernel.revolve(profile, angle, axis_y=1, axis_z=0)
    faces = kernel.topology(solid, "turned", "revolve", {})
    stable = {
        face["role"]: face for face in faces if face["provenance"]["semantic_status"] == "stable"
    }
    assert {"side.x_min", "side.x_max", "side.y_min", "side.y_max"} <= stable.keys()
    if angle == 180:
        assert {"cap.start", "cap.end"} <= stable.keys()
    else:
        assert not {"cap.start", "cap.end"} & stable.keys()
    end = stable["side.y_max"]
    assert end["signature"]["surface"] == "plane"
    face_profile = kernel.face_circle(solid, end["id"], 0.25, x=4)
    assert kernel.inspect(kernel.extrude(face_profile, 1))["volume"] == pytest.approx(
        3.141592653589793 * 0.25**2
    )
