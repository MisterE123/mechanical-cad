"""Actual canonical Part → reused instances → exact pose evidence regressions."""

from dataclasses import replace

import pytest

from mechanical_cad.assembly_model import (
    AssemblyDocument,
    Frame,
    Instance,
    Joint,
    MateFrame,
    PartDefinition,
    PartSource,
)
from mechanical_cad.assembly_service import preflight_source_update, run_assembly_action
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document

pytestmark = pytest.mark.kernel


def part_document(width=10):
    return Document.from_dict(
        {
            "schema_version": 1,
            "id": "user_part",
            "name": "User-authored block",
            "units": "mm",
            "parameters": {"width": width},
            "features": [
                {
                    "id": "profile",
                    "kind": "sketch_rectangle",
                    "label": "Profile",
                    "params": {"width": "width", "height": 10, "x": 0, "y": 0, "z": 0},
                    "inputs": {},
                },
                {
                    "id": "pad",
                    "kind": "extrude",
                    "label": "Block",
                    "params": {"length": 10},
                    "inputs": {"profile": "profile"},
                },
            ],
            "active_feature": "pad",
        }
    )


def assembly():
    source = PartSource.from_document(part_document())
    definition = PartDefinition(
        "block",
        source.source_digest,
        source.id,
        "pad",
        (MateFrame("origin"), MateFrame("offset", Frame((30, 0, 0)))),
        name="Block",
    )
    return AssemblyDocument(
        "assembly",
        "Three user blocks",
        (source,),
        (definition,),
        (Instance("root", "block"), Instance("a", "block"), Instance("b", "block")),
        (
            Joint("slide_a", "slider", "root", "a", "origin", "origin", 100, (0, 300)),
            Joint("slide_b", "slider", "root", "b", "offset", "origin", 100, (0, 300)),
        ),
        "root",
    )


def test_replay_embedded_user_part_once_with_reused_instances():
    class CountKernel(OCPKernel):
        def __init__(self):
            super().__init__()
            self.extrusions = 0

        def extrude(self, *args, **kwargs):
            self.extrusions += 1
            return super().extrude(*args, **kwargs)

    kernel = CountKernel()
    result = run_assembly_action(assembly(), kernel=kernel)
    assert result["ok"] and result["report"]["status"] == "replayed"
    assert not result["report"]["passed"]
    assert kernel.extrusions == 1
    assert len(result["result"]["parts"]) == 1
    assert len(result["result"]["instances"]) == 3
    assert result["result"]["parts"][0]["geometry_check"]["brep"]["volume"] == pytest.approx(1000)


def test_exact_check_and_clearance_requirements():
    result = run_assembly_action(
        assembly(),
        "assembly_check",
        coordinates={"slide_a": 20, "slide_b": 0},
        requirements=[{"instances": ["root", "a"], "minimum_mm": 11}],
    )
    assert result["ok"]
    report = result["report"]
    assert report["complete"] and report["known_clearance_violation"]
    assert not report["passed"]
    pair = next(p for p in report["poses"][0]["pairs"] if p["instances"] == ["a", "root"])
    assert pair["minimum_distance_mm"] == pytest.approx(10)
    assert pair["minimum_required_mm"] == 11


def test_sampling_keeps_full_current_base_including_other_joint_override():
    result = run_assembly_action(
        assembly(),
        "assembly_sample",
        coordinates={"slide_a": 100, "slide_b": 200},
        samples={"joint_id": "slide_a", "values": [50, 60]},
    )
    assert result["ok"]
    assert result["report"]["scope"] == "only_listed_discrete_poses"
    assert not result["report"]["continuous_collision_guarantee"]
    for row, expected in zip(result["report"]["poses"], (50, 60), strict=True):
        assert row["pose"]["effective_coordinates"] == {"slide_a": expected, "slide_b": 200}
        assert row["pose"]["transforms"]["b"]["xyz_mm"] == [30, 0, 200]


def test_sampling_requires_explicit_full_base_before_native_calls():
    result = run_assembly_action(
        assembly(),
        "assembly_sample",
        coordinates={"slide_a": 100},
        samples={"joint_id": "slide_a", "values": [50]},
        kernel=object(),
    )
    assert not result["ok"]
    assert result["error"]["code"] == "incomplete_base_pose"
    assert not result["result"]["source_replays"]


def test_proven_interference_survives_another_unknown_pair():
    class OneUnknown(OCPKernel):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def pair_check(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("injected native query failure")
            return super().pair_check(*args, **kwargs)

    result = run_assembly_action(
        assembly(),
        "assembly_check",
        coordinates={"slide_a": 5, "slide_b": 100},
        kernel=OneUnknown(),
    )
    assert not result["ok"]
    assert result["report"]["status"] == "violations_found"
    assert result["report"]["known_interference"]
    assert not result["report"]["complete"]
    assert len(result["report"]["poses"][0]["pairs"]) == 3


def test_motion_known_violation_survives_blocked_limit_sample():
    result = run_assembly_action(
        assembly(),
        "assembly_sample",
        coordinates={"slide_a": 100, "slide_b": 100},
        samples={"joint_id": "slide_a", "values": [5, 301]},
    )
    assert not result["ok"]
    report = result["report"]
    assert report["status"] == "violations_found" and report["known_interference"]
    assert not report["complete"]
    blocked = report["poses"][1]["pose"]
    assert blocked["requested_coordinates"]["slide_a"] == 301
    assert blocked["effective_coordinates"] == {}


def test_endpoint_samples_do_not_claim_unchecked_midpoint_clear():
    candidate = replace(
        assembly(), joints=(replace(assembly().joints[0], limits=(-100, 100)), assembly().joints[1])
    )
    result = run_assembly_action(
        candidate,
        "assembly_sample",
        coordinates={"slide_a": -30, "slide_b": 100},
        samples={"joint_id": "slide_a", "values": [-30, 30]},
        requirements=[],
    )
    assert result["report"]["passed"]
    midpoint = run_assembly_action(candidate, "assembly_check", coordinates={"slide_a": 0})
    assert midpoint["report"]["known_interference"]
    assert not result["report"]["continuous_collision_guarantee"]


def test_blocked_request_fingerprints_assembly_requested_coordinates_and_policy():
    base = assembly()
    first = run_assembly_action(base, coordinates={"slide_a": 999}, kernel=object())
    assert first["report"]["base_pose"]["effective_coordinates"] == {}
    assert first["request"]["requested_coordinates"] == {"slide_a": 999}
    variations = [
        run_assembly_action(replace(base, name="Another assembly"), coordinates={"slide_a": 999}),
        run_assembly_action(base, coordinates={"slide_a": 998}),
        run_assembly_action(
            base, coordinates={"slide_a": 999}, policy={"linear_tolerance_mm": 1e-5}
        ),
    ]
    assert all(row["request_fingerprint"] != first["request_fingerprint"] for row in variations)
    assert all(row["report_fingerprint"] != first["report_fingerprint"] for row in variations)
    assert first["request"]["source_hashes"] == dict(base.source_hashes)
    assert first["request"]["policy_version"] and first["request"]["runtime_versions"]


def test_update_all_reused_instances_preflight_preserves_ids_and_literal_frames():
    original = assembly()
    old_json = original.to_json()
    result = preflight_source_update(original, "user_part", part_document(20))
    assert result["ok"]
    update = result["update"]
    assert update["affected_instances"] == ["root", "a", "b"]
    candidate = AssemblyDocument.from_dict(update["candidate"])
    assert candidate.instances == original.instances and candidate.joints == original.joints
    assert candidate.parts[0].mate_frames == original.parts[0].mate_frames
    assert candidate.parts[0].source_digest != original.parts[0].source_digest
    assert original.to_json() == old_json
    assert result["result"]["parts"][0]["geometry_check"]["brep"]["volume"] == pytest.approx(2000)


def test_failed_source_update_cannot_publish_candidate_or_mutate_accepted_snapshot():
    original = assembly()
    old_json = original.to_json()
    result = preflight_source_update(original, "user_part", part_document(-1))
    assert not result["ok"] and result["update"]["candidate"] is None
    assert result["error"]["code"] == "source_replay_failed"
    assert original.to_json() == old_json


def test_mappingproxy_pose_request_values_are_bound_to_request_fingerprint():
    from types import MappingProxyType

    results = [
        run_assembly_action(
            assembly(),
            "assembly_check",
            coordinates=MappingProxyType({"slide_a": value, "slide_b": 300}),
            requirements=[],
        )
        for value in (100, 200)
    ]
    assert all(result["report"]["passed"] for result in results)
    assert results[0]["request_fingerprint"] != results[1]["request_fingerprint"]
    assert results[0]["request"]["requested_coordinates"] == {"slide_a": 100, "slide_b": 300}


def test_invalid_large_request_contents_are_not_replaced_by_length_only_identity():
    results = [run_assembly_action(assembly(), requirements=[v] * 4097) for v in (0, 1)]
    assert all(not result["ok"] for result in results)
    assert results[0]["request_fingerprint"] != results[1]["request_fingerprint"]
    assert results[0]["report_fingerprint"] != results[1]["report_fingerprint"]


def test_oversized_direct_integer_returns_bound_blocked_report_not_decimal_conversion_error():
    value = 10**5000
    result = run_assembly_action(assembly(), coordinates={"slide_a": value})
    assert not result["ok"]
    assert result["request"]["requested_coordinates"]["slide_a"] == {
        "invalid_integer_hex": hex(value)
    }
    assert result["report"]["base_pose"]["effective_coordinates"] == {}


def test_direct_embedded_oversized_numeric_token_cannot_create_unloadable_snapshot():
    from mechanical_cad.errors import CADException

    oversized = part_document()
    raw = oversized.to_dict()
    raw["features"][1]["params"]["length"] = 10**128
    oversized = Document.from_dict(raw)
    with pytest.raises(CADException, match="numeric token"):
        PartSource.from_document(oversized)
    with pytest.raises(CADException, match="numeric token"):
        assembly().replace_source("user_part", oversized)


def test_failed_native_replay_diagnostic_is_part_of_observed_report_identity():
    class FailedKernel(OCPKernel):
        def __init__(self, reason):
            super().__init__()
            self.reason = reason

        def extrude(self, *args, **kwargs):
            raise RuntimeError(self.reason)

    results = [
        run_assembly_action(assembly(), kernel=FailedKernel(reason)) for reason in ("A", "B")
    ]
    assert results[0]["request_fingerprint"] == results[1]["request_fingerprint"]
    assert results[0]["report_fingerprint"] != results[1]["report_fingerprint"]


@pytest.mark.parametrize(
    "a,b",
    [
        ((), {"invalid_type": "tuple", "items": []}),
        (float("nan"), {"invalid_numeric_value": "nan"}),
    ],
)
def test_literal_dictionary_cannot_forge_invalid_input_type_identity(a, b):
    results = [run_assembly_action(assembly(), requirements=value) for value in (a, b)]
    assert all(not result["ok"] for result in results)
    assert results[0]["request_fingerprint"] != results[1]["request_fingerprint"]
    assert results[0]["report_fingerprint"] != results[1]["report_fingerprint"]
