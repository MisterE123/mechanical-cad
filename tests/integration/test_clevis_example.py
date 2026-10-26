"""Production service/sidecar checks, with independently derived geometry values."""

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

import mechanical_cad
from mechanical_cad.assembly_kinematics import evaluate
from mechanical_cad.assembly_model import AssemblyDocument, PartSource
from mechanical_cad.assembly_requirements import VerificationPreset
from mechanical_cad.assembly_service import preflight_source_update, run_assembly_action
from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples" / "clevis_hinge"
BASE_COORDINATES = {"hinge": 0.0, "pin_fixed": 0.0}
POSE_SAMPLES = (
    ("negative_stop", -60),
    ("negative_forty", -40),
    ("negative_twenty", -20),
    ("neutral", 0),
    ("positive_twenty", 20),
    ("positive_forty", 40),
    ("positive_stop", 60),
)
EXPECTED_HASHES = {
    "base.mcad.json": "db46fce5c0221ae395129b06cd05dc4d9433c6d68058678a49cdd198c74fe785",
    "leaf.mcad.json": "5d8a0b005a6ab9eaddadf4dd52f122afd71883011aa76eae72259317a63bf96d",
    "pin.mcad.json": "8571b305aa4763e0ee50d19917b32e2d0e172dc6f5f4e9f77ca553f2bc0f56e9",
    "assembly.mcad-assembly.json": "8a59929cbe9b6f810641f24baa981a50dccdb88b874780e79472e1ccde2370a7",
}


@pytest.fixture(scope="session", autouse=True)
def verify_import_origin():
    assert Path(mechanical_cad.__file__).resolve().parent == ROOT / "src" / "mechanical_cad"


@pytest.fixture(scope="session")
def native():
    pytest.importorskip("OCP")
    pytest.importorskip("slvs")


@pytest.fixture(scope="session")
def documents():
    return {
        name: Document.from_json((EXAMPLES / f"{name}.mcad.json").read_text())
        for name in ("base", "leaf", "pin")
    }


@pytest.fixture(scope="session")
def model():
    return AssemblyDocument.from_json((EXAMPLES / "assembly.mcad-assembly.json").read_text())


def analytical_volumes():
    # Independently derived from the documented stock/cutter dimensions.
    cheek_thickness = 18 - 10
    slot_intersection = 12 * (8 - (-7)) * 10
    leaf_thickness = 10 - 2 * 0.25
    return {
        "base": 12 * 20 * 18 - slot_intersection - math.pi * 2.5**2 * cheek_thickness,
        "leaf": (8 * 20 - math.pi * 2.5**2) * leaf_thickness,
        "pin": math.pi * (2.5 - 0.2) ** 2 * 20,
    }


def assembly_request(assembly, action="assembly_check", **kwargs):
    return {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "assembly": assembly.to_dict(),
        "action": action,
        "coordinates": dict(BASE_COORDINATES),
        **kwargs,
    }


def run_sidecar(request):
    process = subprocess.run(
        [sys.executable, "-B", "-m", "mechanical_cad.sidecar"],
        input=json.dumps(request, allow_nan=False),
        text=True,
        capture_output=True,
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "src")},
        timeout=120,
        check=False,
    )
    result = json.loads(process.stdout)
    assert process.returncode == (0 if result["ok"] else 1), process.stderr
    assert process.stderr == ""
    return result, {"returncode": process.returncode}


def pairs(report, index=0):
    return {tuple(row["instances"]): row for row in report["poses"][index]["pairs"]}


def with_pin_gap(model, documents, gap):
    # Edit the checked-in canonical Part, then explicitly accept a typed source revision.
    document = documents["pin"].with_parameter("radial_gap", gap)
    source = PartSource.from_document(document)
    return replace(
        model,
        part_sources=tuple(source if row.id == document.id else row for row in model.part_sources),
        parts=tuple(
            replace(row, source_digest=document.content_hash)
            if row.source_document_id == document.id
            else row
            for row in model.parts
        ),
    )


def boundary_control(model, documents, kind):
    if kind == "engineering-threshold-equality":
        nominal = model.verification_presets[0]
        preset = replace(
            nominal,
            id="engineering_threshold_equality",
            requirements=tuple(
                replace(
                    row,
                    minimum_mm=(10 - 9.5) / 2 if row.instances == ("base", "leaf") else 2.5 - 2.3,
                )
                for row in nominal.requirements
            ),
        )
    else:
        model = with_pin_gap(model, documents, 5e-7 if kind == "near-numerical-contact" else 0.0)
        preset = VerificationPreset(
            "contact_observation",
            "Explicit interference-only contact observation",
            (),
            model.verification_presets[0].policy,
            "interference_only",
        )
    return replace(model, verification_presets=(preset,), active_verification_preset=preset.id)


@pytest.fixture(scope="session")
def sampled(model, native):
    result, process = run_sidecar(
        assembly_request(
            model,
            "assembly_sample",
            samples={
                "joint_id": "hinge",
                "values": [math.radians(a) for _, a in POSE_SAMPLES],
            },
        )
    )
    assert process["returncode"] == 0
    return result


def test_three_canonical_parts_and_embedded_sources_have_exact_same_identity(model, documents):
    assert {d.schema_version for d in documents.values()} == {2}
    assert AssemblyDocument.from_json(model.to_json()).to_json() == model.to_json()
    for part_name, document in documents.items():
        part_bytes = (EXAMPLES / f"{part_name}.mcad.json").read_bytes()
        assert part_bytes == document.to_json().encode("utf-8")
        source = next(source for source in model.part_sources if source.id == document.id)
        assert hashlib.sha256(part_bytes).hexdigest() == source.source_digest
        assert source.document.to_json() == part_bytes.decode("utf-8")
        receipt, _ = run_sidecar(
            {"protocol_version": 1, "action": "canonical_snapshot", "document": document.to_dict()}
        )
        assert receipt["result"]["canonical_json"].encode("utf-8") == part_bytes
        assert receipt["result"]["content_hash"] == source.source_digest


@pytest.mark.kernel
@pytest.mark.parametrize("name", ["base", "leaf", "pin"])
def test_real_canonical_feature_replay_volumes_and_solver_dof(name, documents, native):
    document = documents[name]
    replay = regenerate(document, OCPKernel(), linear_deflection=0.05)
    assert replay.ok
    assert all(row["status"] == "ok" for row in replay.result["features"])
    body = next(row for row in replay.result["features"] if row["id"] == "body")
    assert body["stats"]["volume"] == pytest.approx(analytical_volumes()[name], rel=1e-10, abs=1e-7)
    sketches = [row["sketch"] for row in replay.result["features"] if "sketch" in row]
    assert len(sketches) == (0 if name == "pin" else 1)
    for sketch in sketches:
        assert sketch["solver"] == "libslvs"
        assert sketch["remaining_dof"] == 0
        assert sketch["status"] == "okay"
        assert sketch["max_residual_mm"] < 1e-8


def test_literal_frames_ground_fixed_pin_and_tree_rotation(model):
    angle = math.radians(40)
    pose = evaluate(model, {**BASE_COORDINATES, "hinge": angle})
    assert pose.status == "evaluated"
    assert pose.structural_dof == 1
    assert pose.transforms["base"].xyz_mm == (0, 0, 0)
    assert pose.transforms["pin"].xyz_mm == (0, 0, 0)
    assert pose.transforms["leaf"].xyz_mm == pytest.approx((0, 0, -4.75), abs=1e-12)
    # A point on the leaf's authored literal midplane stays on the world hinge axis.
    assert pose.transforms["leaf"].point((0, 0, 4.75)) == pytest.approx((0, 0, 0))
    assert pose.transforms["leaf"].point((0, 16, 4.75)) == pytest.approx(
        (-16 * math.sin(angle), 16 * math.cos(angle), 0)
    )
    assert len(model.joints) == len(model.instances) - 1
    assert model.grounded_instance == "base"


@pytest.mark.kernel
def test_seven_named_samples_exact_gaps_and_analytical_volumes(sampled):
    report = sampled["report"]
    assert sampled["ok"] and report["complete"] and report["passed"]
    assert not report["known_interference"] and not report["known_clearance_violation"]
    assert not report["continuous_collision_guarantee"]
    assert report["verification_basis"]["preset_id"] == "nominal_running_clearance"
    assert len(report["poses"]) == 7
    for part in sampled["result"]["parts"]:
        assert part["geometry_check"]["brep"]["volume"] == pytest.approx(
            analytical_volumes()[part["id"]], rel=1e-10, abs=1e-7
        )
    gaps = {
        ("base", "leaf"): (10 - 9.5) / 2,
        ("base", "pin"): 2.5 - 2.3,
        ("leaf", "pin"): 2.5 - 2.3,
    }
    for index, pose in enumerate(report["poses"]):
        assert pose["pose"]["structural_dof"] == 1
        assert pose["pose"]["dof_method"] == "rooted_tree_joint_count"
        assert set(pairs(report, index)) == set(gaps)
        for pair, expected_gap in gaps.items():
            row = pairs(report, index)[pair]
            assert row["common_volume_mm3"] == pytest.approx(0, rel=1e-10, abs=1e-7)
            assert row["minimum_distance_mm"] == pytest.approx(expected_gap, rel=1e-10, abs=1e-7)
            assert row["clearance_verdict"] == "pass_at_pose"
    assert sampled["report"]["scope"] == "only_listed_discrete_poses"
    for row, (_, angle) in zip(sampled["report"]["poses"], POSE_SAMPLES, strict=True):
        assert row["pose"]["effective_coordinates"] == {
            **BASE_COORDINATES,
            "hinge": math.radians(angle),
        }
    # Seven explicitly checked poses, three unordered pairs at every pose.
    assert sum(len(row["pairs"]) for row in sampled["report"]["poses"]) == 21


@pytest.mark.kernel
def test_oversized_pin_reports_analytical_annular_interference(model, documents, native):
    model = with_pin_gap(model, documents, -0.1)
    result = run_assembly_action(model, "assembly_check", coordinates=BASE_COORDINATES)
    assert result["ok"] and result["report"]["complete"]
    assert result["report"]["known_interference"] and not result["report"]["passed"]
    for pair, length in {("base", "pin"): 8, ("leaf", "pin"): 9.5}.items():
        row = pairs(result["report"])[pair]
        assert row["relation"] == "interference"
        assert row["common_volume_mm3"] == pytest.approx(
            math.pi * (2.6**2 - 2.5**2) * length, abs=1e-7
        )
        assert row["clearance_verdict"] == "fail_interference"


@pytest.mark.kernel
def test_positive_gap_can_still_violate_engineering_requirement(model, documents, native):
    model = with_pin_gap(model, documents, 0.1)
    result = run_assembly_action(model, "assembly_check", coordinates=BASE_COORDINATES)
    assert result["ok"] and result["report"]["known_clearance_violation"]
    assert not result["report"]["known_interference"]
    assert not result["report"]["passed"]
    for pair in (("base", "pin"), ("leaf", "pin")):
        row = pairs(result["report"])[pair]
        assert row["minimum_distance_mm"] == pytest.approx(0.1, rel=1e-10, abs=1e-7)
        assert row["minimum_required_mm"] == 0.15
    assert result["report"]["effective_policy"]["linear_tolerance_mm"] == 1e-6


@pytest.mark.kernel
def test_saved_but_unselected_preset_does_not_invent_a_pass(model, native):
    model = replace(model, active_verification_preset=None)
    result = run_assembly_action(model, "assembly_check", coordinates=BASE_COORDINATES)
    assert result["ok"] and result["report"]["complete"]
    assert not result["report"]["passed"]
    assert not result["report"]["verification_basis"]["configured"]
    assert all(
        row["clearance_verdict"] == "measurement_only"
        for row in result["report"]["poses"][0]["pairs"]
    )


def test_motion_limit_is_inclusive_and_outside_pose_fails_before_native_replay(model):
    for degrees in (-60, 60):
        assert evaluate(model, {"hinge": math.radians(degrees)}).status == "evaluated"
    request = assembly_request(model, coordinates={**BASE_COORDINATES, "hinge": math.radians(61)})
    result, process = run_sidecar(request)
    assert process["returncode"] == 1
    assert not result["ok"] and result["error"]["code"] == "invalid_pose"
    assert result["report"]["base_pose"]["effective_coordinates"] == {}
    assert result["report"]["base_pose"]["requested_coordinates"]["hinge"] == math.radians(61)
    assert not result["result"]["source_replays"]


@pytest.mark.kernel
def test_canonical_parameter_edit_preflight_preserves_literal_frames_and_old_source(
    model, documents, native
):
    original = model.to_json()
    leaf = documents["leaf"]
    raw = leaf.to_dict()
    raw["parameters"]["side_gap"] = 0.5  # Thickness becomes 9 mm, frame stays at z=4.75.
    changed_leaf = Document.from_dict(raw)
    preflight = preflight_source_update(model, leaf.id, changed_leaf)
    assert preflight["ok"] and preflight["update"]["affected_instances"] == ["leaf"]
    assert preflight["update"]["publication_required"]
    changed = AssemblyDocument.from_dict(preflight["update"]["candidate"])
    assert model.to_json() == original
    assert changed.content_hash != model.content_hash
    assert changed.joints == model.joints
    assert changed.parts[1].mate_frames == model.parts[1].mate_frames
    assert changed.source_hashes[leaf.id] == changed_leaf.content_hash
    assert changed.verification_presets == model.verification_presets
    checked = run_assembly_action(changed, "assembly_check", coordinates=BASE_COORDINATES)
    leaf_part = next(row for row in checked["result"]["parts"] if row["id"] == "leaf")
    assert leaf_part["geometry_check"]["brep"]["volume"] == pytest.approx(
        (8 * 20 - math.pi * 2.5**2) * 9, abs=1e-7
    )
    # The lower side gap stays 0.25 mm, rather than both sides becoming 0.5 mm.
    assert pairs(checked["report"])[("base", "leaf")]["minimum_distance_mm"] == pytest.approx(0.25)
    assert checked["report"]["base_pose"]["transforms"]["leaf"]["xyz_mm"] == [0, 0, -4.75]


def test_checked_in_canonical_round_trip_and_no_hidden_geometry_sources(model, documents):
    assert {path.name for path in EXAMPLES.iterdir()} == set(EXPECTED_HASHES)
    for name, expected in EXPECTED_HASHES.items():
        content = (EXAMPLES / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == expected
        cls = AssemblyDocument if name.endswith("mcad-assembly.json") else Document
        reopened = cls.from_json(content.decode("utf-8"))
        assert reopened.to_json().encode("utf-8") == content
        assert cls.from_dict(reopened.to_dict()) == reopened
    assert len(model.part_sources) == len(model.parts) == len(model.instances) == 3
    assert dict(model.source_hashes) == {doc.id: doc.content_hash for doc in documents.values()}
    assert {part.output_feature_id for part in model.parts} == {"body"}
    for part in model.parts:
        document = documents[part.id]
        assert part.source_document_id == document.id
        assert part.source_digest == document.content_hash
        assert document.active_feature == part.output_feature_id
    assert (
        model.to_json().encode("utf-8") == (EXAMPLES / "assembly.mcad-assembly.json").read_bytes()
    )


@pytest.mark.kernel
@pytest.mark.parametrize(
    "kind",
    [
        "engineering-threshold-equality",
        "near-numerical-contact",
        "exact-fit-contact",
    ],
)
def test_thresholds_and_contact_never_claim_exact_fit_safety(kind, model, documents, native):
    model = boundary_control(model, documents, kind)
    result, process = run_sidecar(assembly_request(model))
    assert process["returncode"] == 0
    report = result["report"]
    assert report["complete"] and report["has_threshold_contacts"]
    assert report["status"] == "checked_with_threshold_contacts"
    assert not report["passed"]
    assert not report["known_interference"] and not report["known_clearance_violation"]
    for pair, row in pairs(report).items():
        if kind == "engineering-threshold-equality":
            assert row["minimum_distance_mm"] == pytest.approx(
                row["minimum_required_mm"], abs=1e-10
            )
            assert row["relation"] == "separated"
            assert row["clearance_verdict"] == "at_threshold"
        elif "pin" in pair:
            expected = 5e-7 if kind == "near-numerical-contact" else 0.0
            assert row["minimum_distance_mm"] == pytest.approx(expected, abs=1e-10)
            assert row["relation"] == "contact_or_near"
            assert row["clearance_verdict"] == "at_threshold"
            assert row["minimum_required_mm"] == 0.0
            assert row["common_volume_mm3"] == 0.0


@pytest.fixture
def generator_checkout(tmp_path):
    """A disposable independent Git tree; never stage or commit in the real checkout."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    shutil.copytree(ROOT / "src", checkout / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(EXAMPLES, checkout / "examples" / "clevis_hinge")
    (checkout / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts/generate_clevis_example.py", checkout / "scripts")
    for command in (
        ("init", "-q"),
        ("add", "."),
        (
            "-c",
            "user.name=Example test",
            "-c",
            "user.email=example-test@invalid",
            "commit",
            "-qm",
            "Fixture source",
        ),
    ):
        subprocess.run(["git", "-C", str(checkout), *command], check=True, capture_output=True)
    return checkout


def run_generator(checkout, *arguments, source=None):
    # -S proves default checks and provenance need no native/site packages.
    return subprocess.run(
        [
            sys.executable,
            "-S",
            "-B",
            str(checkout / "scripts/generate_clevis_example.py"),
            *arguments,
        ],
        text=True,
        capture_output=True,
        cwd=checkout.parent,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(source or checkout / "src"),
        },
        timeout=30,
        check=False,
    )


def test_generator_defaults_to_read_only_check_with_current_committed_provenance(
    generator_checkout,
):
    checkout = generator_checkout
    before = {
        str(path.relative_to(checkout)): path.read_bytes()
        for path in checkout.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    head = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    result = run_generator(checkout, "--require-clean", "--require-commit", head)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["mode"] == "check_only"
    assert summary["canonical_model_sha256"] == EXPECTED_HASHES
    assert summary["numerical_policy"]["linear_tolerance_mm"] == 1e-6
    provenance = summary["source_provenance"]
    assert provenance["code_commit"] == head
    assert provenance["source_qualification"] == "clean_committed_tree"
    assert provenance["tracked_worktree_clean"] and provenance["worktree_clean"]
    assert provenance["tracked_changes"] == provenance["nonignored_untracked_files"] == []
    assert provenance["imported_package_directory"] == str(checkout / "src/mechanical_cad")
    assert provenance["sidecar_imported_package_directory"] == str(checkout / "src/mechanical_cad")
    assert (
        provenance["generator_sha256"]
        == hashlib.sha256(
            (checkout / "scripts/generate_clevis_example.py").read_bytes()
        ).hexdigest()
    )
    after = {
        str(path.relative_to(checkout)): path.read_bytes()
        for path in checkout.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    assert after == before
    assert set(checkout.parent.iterdir()) == {checkout}


@pytest.mark.parametrize(
    "fault",
    [
        "foreign_import",
        "wrong_commit",
        "dirty_tracked",
        "dirty_untracked",
        "canonical_drift",
        "in_checkout_evidence",
        "existing_evidence",
    ],
)
def test_generator_rejects_unqualified_or_destructive_requests(generator_checkout, fault):
    checkout = generator_checkout
    evidence = checkout.parent / "evidence"
    arguments = ["--evidence-dir", str(evidence)]
    source = None
    expected = ""
    if fault == "foreign_import":
        source = ROOT / "src"
        expected = "Imported"
    elif fault == "wrong_commit":
        arguments += ["--require-commit", "0" * 40]
        expected = "Required commit"
    elif fault == "dirty_tracked":
        (checkout / "src/mechanical_cad/__init__.py").write_text("# Modified test source\n")
        arguments += ["--require-clean"]
        expected = "--require-clean"
    elif fault == "dirty_untracked":
        (checkout / "untracked.txt").write_text("uncommitted source\n")
        arguments += ["--require-clean"]
        expected = "--require-clean"
    elif fault == "canonical_drift":
        path = checkout / "examples/clevis_hinge/pin.mcad.json"
        path.write_bytes(path.read_bytes() + b"\n")
        expected = "Canonical example bytes differ"
    elif fault == "in_checkout_evidence":
        evidence = checkout / "new-evidence"
        arguments = ["--evidence-dir", str(evidence)]
        expected = "outside this checkout"
    elif fault == "existing_evidence":
        evidence.mkdir()
        (evidence / "sentinel.txt").write_text("Preserve old evidence\n")
        expected = "File exists"
    result = run_generator(checkout, *arguments, source=source)
    assert result.returncode == 2, result.stderr
    assert expected in result.stderr
    if fault == "existing_evidence":
        assert {path.name for path in evidence.iterdir()} == {"sentinel.txt"}
        assert (evidence / "sentinel.txt").read_text() == "Preserve old evidence\n"
    else:
        assert not evidence.exists()


def test_generator_labels_dirty_source_and_records_changed_tree_digest(generator_checkout):
    checkout = generator_checkout
    before = run_generator(checkout)
    assert before.returncode == 0, before.stderr
    source_file = checkout / "src/mechanical_cad/__init__.py"
    source_file.write_bytes(source_file.read_bytes() + b"\n# Test-only change\n")
    after = run_generator(checkout)
    assert after.returncode == 0, after.stderr
    original = json.loads(before.stdout)["source_provenance"]
    changed = json.loads(after.stdout)["source_provenance"]
    assert changed["code_commit"] == original["code_commit"]
    assert changed["source_qualification"] == "dirty_unqualified"
    assert not changed["tracked_worktree_clean"] and not changed["worktree_clean"]
    assert changed["tracked_changes"] == ["src/mechanical_cad/__init__.py"]
    assert changed["source_tree_sha256"] != original["source_tree_sha256"]
    assert changed["tracked_diff_sha256"] != original["tracked_diff_sha256"]
    assert json.loads(after.stdout)["canonical_model_sha256"] == EXPECTED_HASHES
