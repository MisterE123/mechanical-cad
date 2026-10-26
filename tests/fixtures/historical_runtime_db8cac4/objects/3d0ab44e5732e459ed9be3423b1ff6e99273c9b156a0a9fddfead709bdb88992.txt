import json
import math
import os
import random
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from mechanical_cad.assembly_kinematics import (
    DOF_METHOD,
    EVALUATOR_VERSION,
    effective_coordinate_map,
    evaluate,
)
from mechanical_cad.assembly_model import (
    AssemblyDocument,
    Frame,
    Instance,
    Joint,
    MateFrame,
    PartDefinition,
    PartSource,
)
from mechanical_cad.errors import CADException
from mechanical_cad.model import Document, Feature


def simple(kind="revolute"):
    doc = Document.from_dict(
        Document(
            "doc",
            "Plate",
            {"width": 10},
            (
                Feature(
                    "profile", "sketch_rectangle", "Rectangle", {"width": "width", "height": 4}
                ),
                Feature("solid", "extrude", "Extrusion", {"length": 2}, {"profile": "profile"}),
            ),
            "solid",
        ).to_dict()
    )
    part = PartDefinition("p", doc.content_hash, doc.id, "solid", (MateFrame("axis"),))
    return AssemblyDocument(
        "assembly",
        "Mechanism",
        (PartSource.from_document(doc),),
        (part,),
        (Instance("base", "p"), Instance("child", "p")),
        (Joint("j", kind, "base", "child", "axis", "axis"),),
        "base",
    )


def test_frame_composition_inverse_and_matrix():
    f = Frame((3, 4, 5)).then(Frame.rz(math.pi / 2))
    assert f.point((2, 0, 0)) == pytest.approx((3, 6, 5))
    assert f.inverse().point(f.point((2, 7, -3))) == pytest.approx((2, 7, -3))
    assert f.then(f.inverse()).point((2, 7, -3)) == pytest.approx((2, 7, -3))
    m = f.matrix34()
    assert tuple(
        sum(m[r * 4 + c] * (2, 0, 0, 1)[c] for c in range(4)) for r in range(3)
    ) == pytest.approx((3, 6, 5))


def test_nonzero_mate_offsets_arbitrary_axis_and_fixed_descendant():
    a = simple()
    rx = Frame(wxyz=(math.sqrt(0.5), 0, math.sqrt(0.5), 0))
    p = replace(a.parts[0], mate_frames=(MateFrame("axis", Frame((10, 20, 30)).then(rx)),))
    child = replace(a.parts[0], id="q", mate_frames=(MateFrame("axis", Frame((0, 2, 0))),))
    a = replace(
        a,
        parts=(p, child),
        instances=(Instance("base", "p"), Instance("link", "q"), Instance("tip", "q")),
        joints=(
            Joint("hinge", "revolute", "base", "link", "axis", "axis"),
            Joint("weld", "fixed", "link", "tip", "axis", "axis"),
        ),
        ground=Frame((100, 0, 0)),
    )
    r = evaluate(a, {"hinge": math.pi / 2})
    assert r.status == "evaluated" and r.structural_dof == 1
    assert r.transforms["link"].point((0, 2, 0)) == pytest.approx((110, 20, 30))
    assert r.transforms["link"].point((0, 3, 0)) == pytest.approx((110, 20, 31))
    assert r.transforms["tip"].point((0, 3, 0)) == pytest.approx((110, 20, 31))
    assert r.effective_coordinates == {"hinge": math.pi / 2, "weld": 0}


@pytest.mark.parametrize(
    "kind,q,expected,dof",
    [
        ("fixed", 0, (1, 0, 0), 0),
        ("revolute", math.pi / 2, (0, 1, 0), 1),
        ("slider", 3, (1, 0, 3), 1),
    ],
)
def test_joint_kinds_and_structural_dof(kind, q, expected, dof):
    r = evaluate(simple(kind), {"j": q})
    assert r.status == "evaluated"
    assert r.transforms["child"].point((1, 0, 0)) == pytest.approx(expected)
    assert r.structural_dof == dof
    assert r.dof_method == DOF_METHOD
    assert r.evaluator_version == EVALUATOR_VERSION


def test_full_effective_base_map_preserves_other_joint_overrides_when_sampling():
    a = simple("slider")
    a = replace(
        a,
        instances=(*a.instances, Instance("tip", "p")),
        joints=(
            replace(a.joints[0], coordinate=100),
            Joint("s", "slider", "child", "tip", "axis", "axis", 10),
        ),
    )
    requested = {"j": 200, "s": 30}
    base = effective_coordinate_map(a, requested)
    for q in (0, 5, 20):
        coordinates = {**base, "s": q}
        r = evaluate(a, coordinates)
        assert r.structural_dof == 2
        assert r.transforms["tip"].xyz_mm == pytest.approx((0, 0, 200 + q))
        assert r.effective_coordinates == {"j": 200, "s": q}
    assert base == requested == {"j": 200, "s": 30}
    assert a.joints[0].coordinate == 100 and a.joints[1].coordinate == 10


def test_limits_endpoints_and_no_fallback_for_invalid_coordinate():
    a = simple()
    a = replace(a, joints=(replace(a.joints[0], limits=(-1, 1)),))
    for q in (-1, 1):
        r = evaluate(a, {"j": q})
        assert r.status == "evaluated" and r.structural_dof == 1
    r = evaluate(a, {"j": 1.000000001})
    assert r.status == "blocked" and not r.transforms
    assert r.structural_dof == 1
    assert r.diagnostics[0].code == "limit_violation"
    assert r.requested_coordinates == {"j": 1.000000001}
    assert r.effective_coordinates == r.coordinates == {}
    with pytest.raises(CADException):
        effective_coordinate_map(a, {"j": 1.000000001})


@pytest.mark.parametrize(
    "value", [math.nan, math.inf, -math.inf, True, "1", None, [1], {}, 10**1000]
)
def test_bad_coordinate_types_fail_closed_with_json_safe_fingerprints(value):
    a = simple()
    r = evaluate(a, {"j": value})
    assert r.status == "blocked" and not r.transforms and not r.effective_coordinates
    assert r.assembly_digest == a.content_hash
    assert r.source_hashes == a.source_hashes
    assert len(r.pose_digest) == 64
    json.dumps(r.to_dict(), allow_nan=False)
    assert evaluate(a, {"j": value}).pose_digest == r.pose_digest


@pytest.mark.parametrize("requested", [False, [], "j", {1: 0}, {"typo": 1}])
def test_invalid_coordinate_maps_never_become_empty_valid_defaults(requested):
    result = evaluate(simple(), requested)
    assert result.status == "blocked"
    assert result.transforms == {} and result.effective_coordinates == {}
    assert result.requested_coordinates
    with pytest.raises(CADException):
        effective_coordinate_map(simple(), requested)


def test_unknown_coordinate_and_fixed_move_rejected():
    assert evaluate(simple(), {"typo": 1}).diagnostics[0].code == "unknown_coordinate"
    assert evaluate(simple("fixed"), {"j": 1}).diagnostics[0].code == "invalid_coordinate"


@pytest.mark.parametrize("requested", [{"j": 0}, {"j": 2}, {"j": True}, {"typo": 1}])
def test_every_outcome_fingerprint_binds_assembly_and_source_hashes(requested):
    a = simple()
    a = replace(a, joints=(replace(a.joints[0], limits=(-1, 1)),))
    first = evaluate(a, requested)
    renamed = evaluate(replace(a, id="different"), requested)
    updated = a.replace_source("doc", a.part_sources[0].document.with_parameter("width", 20))
    latest = evaluate(updated, requested)
    assert len({first.pose_digest, renamed.pose_digest, latest.pose_digest}) == 3
    assert first.source_hashes != latest.source_hashes
    assert first.assembly_digest != renamed.assembly_digest != latest.assembly_digest
    assert first.requested_coordinates == renamed.requested_coordinates


def test_implicit_default_and_explicit_request_are_distinguished_in_hash():
    a = simple()
    implicit, explicit = evaluate(a), evaluate(a, {"j": 0})
    assert implicit.effective_coordinates == explicit.effective_coordinates
    assert implicit.pose_digest != explicit.pose_digest
    assert evaluate(a, {"j": False}).pose_digest != explicit.pose_digest


def test_pose_output_is_deeply_immutable_and_does_not_alias_request():
    a, requested = simple(), {"j": 0.3}
    r = evaluate(a, requested)
    requested["j"] = 0.7
    assert r.requested_coordinates == {"j": 0.3}
    for mapping in (
        r.requested_coordinates,
        r.effective_coordinates,
        r.transforms,
        r.source_hashes,
    ):
        with pytest.raises(TypeError):
            mapping["new"] = 1
    invalid = evaluate(a, {"j": math.nan})
    with pytest.raises(TypeError):
        invalid.requested_coordinates["j"]["value"] = "0"
    data = r.to_dict()
    data["transforms"]["base"]["xyz_mm"][0] = 99
    assert r.transforms["base"].xyz_mm == (0, 0, 0)


def test_authored_nearly_unit_quaternion_never_normalized_in_snapshot():
    q = (math.sqrt(1 + 5e-10), 0, 0, 0)
    frame = Frame((2, 3, 4), q)
    a = replace(simple(), ground=frame)
    old_json, old_hash = a.to_json(), a.content_hash
    result = evaluate(a, {"j": math.pi / 2})
    assert result.status == "evaluated"
    assert result.transforms["child"].point((1, 0, 0)) == pytest.approx((2, 4, 4), abs=1e-12)
    assert a.ground.wxyz == q
    assert a.to_json() == old_json and a.content_hash == old_hash
    assert AssemblyDocument.from_json(a.to_json()).ground.wxyz == q


def test_repeatable_random_frames_match_inverse_and_point_composition():
    rng = random.Random(731)
    for _ in range(200):
        q = [rng.uniform(-1, 1) for _ in range(4)]
        length = math.sqrt(sum(v * v for v in q))
        f = Frame(tuple(rng.uniform(-100, 100) for _ in range(3)), tuple(v / length for v in q))
        g = Frame(tuple(rng.uniform(-100, 100) for _ in range(3))).then(
            Frame.rz(rng.uniform(-3, 3))
        )
        point = tuple(rng.uniform(-10, 10) for _ in range(3))
        assert f.inverse().point(f.point(point)) == pytest.approx(point, abs=1e-10)
        assert f.then(g).point(point) == pytest.approx(f.point(g.point(point)), abs=1e-10)


def test_max_tree_length_uses_parent_first_traversal_independent_of_joint_list_order():
    a = simple("slider")
    a = replace(
        a,
        instances=tuple(Instance(f"i{i}", "p") for i in range(16)),
        joints=tuple(
            Joint(f"j{i}", "slider", f"i{i}", f"i{i + 1}", "axis", "axis", 1)
            for i in reversed(range(15))
        ),
        grounded_instance="i0",
    )
    r = evaluate(a)
    assert r.status == "evaluated" and r.structural_dof == 15
    assert r.transforms["i15"].xyz_mm == (0, 0, 15)


def test_out_of_domain_composed_pose_is_blocked_not_partially_published():
    a = replace(simple("slider"), ground=Frame((0, 0, 1e6)))
    r = evaluate(a, {"j": 1})
    assert r.status == "blocked" and r.transforms == {}
    assert r.effective_coordinates == {"j": 1}
    assert r.diagnostics[0].code == "invalid_number"


def test_pure_modules_import_without_ocp_blender_or_solver():
    code = """
import sys
import mechanical_cad.assembly_model
import mechanical_cad.assembly_kinematics
assert not any(m == 'OCP' or m.startswith('OCP.') or m in ('bpy', 'slvs') for m in sys.modules)
"""
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
    )


@pytest.mark.parametrize(
    "ground,mate",
    [
        (Frame(), Frame((1e6, 1e6, 0), Frame.rz(math.pi / 4).wxyz)),
        (Frame((900000, 0, 0)), Frame((200000, 0, 0))),
    ],
)
def test_large_mate_intermediates_may_cancel_within_valid_final_world_domain(ground, mate):
    original = simple("fixed")
    part = replace(original.parts[0], mate_frames=(MateFrame("axis", mate),))
    assembly = replace(original, ground=ground, parts=(part,))
    result = evaluate(assembly)
    assert result.status == "evaluated"
    assert result.transforms["child"].xyz_mm == pytest.approx(ground.xyz_mm)
    assert result.transforms["child"].point((1, 2, 3)) == pytest.approx(ground.point((1, 2, 3)))
