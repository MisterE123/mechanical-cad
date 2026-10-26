"""Strict geometry report contracts without trusting flags or unknown fields."""

import copy
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "blender_addon/mechanical_cad_blender/geometry_evidence.py"
SPEC = importlib.util.spec_from_file_location("mcad_geometry_evidence_test", MODULE)
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


def stats():
    return {"valid": True, "volume": 1.0, "area": 6.0, "solids": 1, "faces": 6}


def mesh_report():
    return {
        "watertight": True,
        "consistently_oriented": True,
        "vertex_manifold": True,
        "vertices": 8,
        "triangles": 12,
        "signed_volume": 1.0,
        "weld_tolerance": 1e-7,
    }


def checks(*, encoded=False):
    result = {"brep": stats(), "mesh": mesh_report(), "linear_deflection_mm": 0.1}
    if encoded:
        result["encoded_mesh"] = mesh_report()
        result["encoding"] = {
            "maximum_vertex_error_mm": 0.0,
            "allowed_vertex_error_mm": 1e-5,
            "independent_precision_ceiling_mm": 1e-5,
        }
    return result


def mesh():
    vertices = [
        [0, 0, 0],
        [1, 0, 0],
        [1, 1, 0],
        [0, 1, 0],
        [0, 0, 1],
        [1, 0, 1],
        [1, 1, 1],
        [0, 1, 1],
    ]
    triangles = [
        [0, 2, 1],
        [0, 3, 2],
        [4, 5, 6],
        [4, 6, 7],
        [0, 1, 5],
        [0, 5, 4],
        [1, 2, 6],
        [1, 6, 5],
        [2, 3, 7],
        [2, 7, 6],
        [3, 0, 4],
        [3, 4, 7],
    ]
    return {
        "vertices": vertices * 3,
        "triangles": triangles,
        "triangle_face_ids": ["face"] * 12,
    }


@pytest.mark.parametrize("encoded", [False, True])
def test_complete_evidence_binds_counts_without_equating_welded_vertices(encoded):
    actual = checks(encoded=encoded)
    original = copy.deepcopy(actual)
    evidence.validate_geometry_check(
        actual, linear_deflection=0.1, stats=stats(), mesh=mesh(), encoded=encoded
    )
    assert actual == original
    assert actual["mesh"]["vertices"] < len(mesh()["vertices"])


@pytest.mark.parametrize("field", ["volume", "area"])
@pytest.mark.parametrize("value", [False, "1", -100, 0, float("nan"), float("inf"), 1e101])
def test_stats_require_finite_positive_measures(field, value):
    actual = stats()
    actual[field] = value
    with pytest.raises(ValueError):
        evidence.validate_stats(actual)


@pytest.mark.parametrize(
    "field,value",
    [
        ("valid", 1),
        ("valid", False),
        ("solids", True),
        ("solids", 0),
        ("solids", 2),
        ("faces", True),
        ("faces", 0),
        ("faces", 1.0),
        ("faces", 200_001),
    ],
)
def test_stats_require_exact_validity_and_bounded_integer_counts(field, value):
    actual = stats()
    actual[field] = value
    with pytest.raises(ValueError):
        evidence.validate_stats(actual)


def test_huge_integer_measure_is_a_value_error():
    actual = stats()
    actual["volume"] = 1 << 20_000
    with pytest.raises(ValueError):
        evidence.validate_stats(actual)


@pytest.mark.parametrize("path", [(), ("brep",), ("mesh",), ("encoded_mesh",), ("encoding",)])
@pytest.mark.parametrize("mutation", ["unknown", "missing"])
def test_every_report_level_has_an_exact_schema(path, mutation):
    actual = checks(encoded=True)
    target = actual
    for key in path:
        target = target[key]
    if mutation == "unknown":
        target["unknown_future_field"] = True
    else:
        del target[next(iter(target))]
    with pytest.raises(ValueError):
        evidence.validate_geometry_check(actual, linear_deflection=0.1, encoded=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("vertices", True),
        ("vertices", 3),
        ("vertices", 100_001),
        ("vertices", 8.0),
        ("triangles", "text"),
        ("triangles", 3),
        ("triangles", 13),
        ("triangles", 200_002),
        ("signed_volume", 0),
        ("signed_volume", False),
        ("signed_volume", 1e-22),
        ("signed_volume", float("nan")),
        ("weld_tolerance", 1e-5),
        ("weld_tolerance", "1e-7"),
        ("weld_tolerance", False),
    ],
)
def test_mesh_measure_and_count_corruptions_are_rejected(field, value):
    actual = mesh_report()
    actual[field] = value
    with pytest.raises(ValueError):
        evidence.validate_mesh_report(actual)


@pytest.mark.parametrize("field", ["watertight", "consistently_oriented", "vertex_manifold"])
@pytest.mark.parametrize("value", [False, 1, "true", None])
def test_all_mesh_success_flags_are_literal_true(field, value):
    actual = mesh_report()
    actual[field] = value
    with pytest.raises(ValueError):
        evidence.validate_mesh_report(actual)


def test_triangle_uniqueness_limits_count_for_a_fixed_vertex_set():
    actual = mesh_report()
    actual["vertices"] = 4
    with pytest.raises(ValueError, match="counts"):
        evidence.validate_mesh_report(actual)


@pytest.mark.parametrize("value", [None, [], True, {}, {"brep": stats()}])
def test_missing_or_incomplete_geometry_checks_fail(value):
    with pytest.raises(ValueError):
        evidence.validate_geometry_check(value, linear_deflection=0.1)


@pytest.mark.parametrize("value", [True, "0.1", 0, 0.0001, 11, float("nan"), float("inf")])
def test_requested_and_checked_deflection_are_strict(value):
    with pytest.raises(ValueError):
        evidence.validate_geometry_check(checks(), linear_deflection=value)
    actual = checks()
    actual["linear_deflection_mm"] = value
    with pytest.raises(ValueError):
        evidence.validate_geometry_check(actual, linear_deflection=0.1)


def test_requested_deflection_must_match_actual_check():
    with pytest.raises(ValueError, match="tolerance"):
        evidence.validate_geometry_check(checks(), linear_deflection=0.2)


@pytest.mark.parametrize("field", ["volume", "area", "faces"])
def test_checked_brep_is_bound_to_fresh_replay_stats(field):
    actual = checks()
    actual["brep"][field] += 1
    with pytest.raises(ValueError):
        evidence.validate_geometry_check(actual, linear_deflection=0.1, stats=stats())


def test_face_count_cannot_exceed_checked_triangle_count():
    actual = checks()
    actual["brep"]["faces"] = 13
    with pytest.raises(ValueError, match="faces"):
        evidence.validate_geometry_check(actual, linear_deflection=0.1)


@pytest.mark.parametrize("field,value", [("triangles", 14), ("vertices", 25)])
def test_report_counts_are_bound_to_supplied_tessellation(field, value):
    actual = mesh_report()
    actual[field] = value
    with pytest.raises(ValueError):
        evidence.validate_mesh_report(actual, mesh=mesh())


def test_stl_requires_complete_encoding_evidence_unless_failure_is_explicit():
    with pytest.raises(ValueError):
        evidence.validate_geometry_check(checks(), linear_deflection=0.1, encoded=True)
    evidence.validate_geometry_check(
        checks(), linear_deflection=0.1, encoded=True, allow_partial_encoded=True
    )
    evidence.validate_geometry_check(
        checks(encoded=True), linear_deflection=0.1, encoded=True, allow_partial_encoded=True
    )
    with pytest.raises(ValueError):
        evidence.validate_geometry_check(
            checks(), linear_deflection=0.1, allow_partial_encoded=True
        )


@pytest.mark.parametrize("missing", ["encoding", "encoded_mesh"])
def test_partial_stl_mode_never_accepts_half_present_encoding(missing):
    actual = checks(encoded=True)
    del actual[missing]
    with pytest.raises(ValueError):
        evidence.validate_geometry_check(
            actual, linear_deflection=0.1, encoded=True, allow_partial_encoded=True
        )


def test_non_stl_mode_rejects_unrequested_encoding_claims():
    with pytest.raises(ValueError):
        evidence.validate_geometry_check(checks(encoded=True), linear_deflection=0.1)


@pytest.mark.parametrize(
    "field,value",
    [
        ("maximum_vertex_error_mm", -1),
        ("maximum_vertex_error_mm", 1.1e-5),
        ("maximum_vertex_error_mm", True),
        ("maximum_vertex_error_mm", float("nan")),
        ("allowed_vertex_error_mm", 0),
        ("allowed_vertex_error_mm", 0.1),
        ("allowed_vertex_error_mm", 1e-6),
        ("independent_precision_ceiling_mm", 1e-4),
        ("independent_precision_ceiling_mm", "0.00001"),
    ],
)
def test_stl_encoding_obeys_the_exact_independent_precision_policy(field, value):
    actual = checks(encoded=True)
    actual["encoding"][field] = value
    with pytest.raises(ValueError):
        evidence.validate_geometry_check(actual, linear_deflection=0.1, encoded=True)


def test_encoded_triangles_match_source_but_mesh_volume_need_not_equal_brep():
    actual = checks(encoded=True)
    actual["mesh"]["signed_volume"] = 0.99
    actual["encoded_mesh"]["signed_volume"] = 0.989999
    evidence.validate_geometry_check(actual, linear_deflection=0.1, encoded=True)
    actual["encoded_mesh"]["triangles"] = 14
    with pytest.raises(ValueError, match="encoded triangle"):
        evidence.validate_geometry_check(actual, linear_deflection=0.1, encoded=True)


def test_leaf_loads_with_native_and_transport_imports_forbidden():
    code = f"""
import builtins, importlib.util
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {{'bpy', 'OCP', 'slvs', 'mechanical_cad', 'subprocess'}}:
        raise AssertionError('forbidden dependency: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
spec = importlib.util.spec_from_file_location('native_free_geometry', {str(MODULE)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert callable(module.validate_geometry_check)
"""
    process = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert process.returncode == 0, process.stderr


def _document(*, circle=False, translated=False):
    from mechanical_cad.model import Document

    params = {"radius": 4.1234} if circle else {"width": 0.1, "height": 0.1}
    if translated:
        params.update(x=1e6, y=1e6, z=1e6)
    return Document.from_dict(
        {
            "schema_version": 1,
            "id": "checked-part",
            "name": "Checked Part",
            "units": "mm",
            "parameters": {},
            "active_feature": "pad",
            "features": [
                {
                    "id": "profile",
                    "kind": "sketch_circle" if circle else "sketch_rectangle",
                    "params": params,
                },
                {
                    "id": "pad",
                    "kind": "extrude",
                    "params": {"length": 0.1},
                    "inputs": {"profile": "profile"},
                },
            ],
        }
    )


@pytest.mark.kernel
@pytest.mark.parametrize("action", ["check_geometry", "export_step", "export_stl"])
@pytest.mark.parametrize("circle", [False, True])
def test_actual_native_reports_satisfy_exact_contract(tmp_path, action, circle):
    from mechanical_cad.actions import run_geometry_action

    destination = None if action == "check_geometry" else tmp_path / "checked-part.export"
    response = run_geometry_action(
        _document(circle=circle), action, destination=destination, result_version=2
    )
    assert response["ok"], response["error"]
    active = response["result"]["features"][-1]
    evidence.validate_geometry_check(
        response["geometry_check"],
        linear_deflection=0.1,
        stats=active["stats"],
        mesh=active["mesh"],
        encoded=action == "export_stl",
    )


@pytest.mark.kernel
def test_actual_stl_precision_failure_retains_only_valid_base_checks(tmp_path):
    from mechanical_cad.actions import run_geometry_action

    destination = tmp_path / "preserved.stl"
    destination.write_bytes(b"previous")
    response = run_geometry_action(
        _document(translated=True),
        "export_stl",
        destination=destination,
        linear_deflection=0.001,
        result_version=2,
    )
    assert not response["ok"] and "coordinate error" in response["error"]["message"]
    assert response["export"] is None and destination.read_bytes() == b"previous"
    active = response["result"]["features"][-1]
    evidence.validate_geometry_check(
        response["geometry_check"],
        linear_deflection=0.001,
        stats=active["stats"],
        mesh=active["mesh"],
        encoded=True,
        allow_partial_encoded=True,
    )
    with pytest.raises(ValueError):
        evidence.validate_geometry_check(
            response["geometry_check"], linear_deflection=0.001, encoded=True
        )


@pytest.mark.parametrize("keyword", ["encoded", "allow_partial_encoded"])
@pytest.mark.parametrize("value", [1, "true", None])
def test_mode_flags_require_actual_booleans(keyword, value):
    with pytest.raises(ValueError):
        evidence.validate_geometry_check(checks(), linear_deflection=0.1, **{keyword: value})
