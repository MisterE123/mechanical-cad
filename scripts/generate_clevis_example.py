"""Check the canonical clevis example; optionally capture fresh external evidence.

The default only compares generated canonical bytes with checked-in examples.
Use --evidence-dir NEW_DIRECTORY outside this checkout to run native checks.
Set PYTHONPATH to this checkout's src directory; imports are verified explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import mechanical_cad
from mechanical_cad.assembly_model import (
    AssemblyDocument,
    Frame,
    Instance,
    Joint,
    MateFrame,
    PartDefinition,
    PartSource,
)
from mechanical_cad.assembly_requirements import (
    ClearanceRequirement,
    NumericalPolicy,
    VerificationPreset,
)
from mechanical_cad.model import Document

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
EXAMPLES = ROOT / "examples" / "clevis_hinge"
POLICY = NumericalPolicy(1e-6, 1e-9, 0.05)
POSE_SAMPLES = (
    ("negative_stop", -60),
    ("negative_forty", -40),
    ("negative_twenty", -20),
    ("neutral", 0),
    ("positive_twenty", 20),
    ("positive_forty", 40),
    ("positive_stop", 60),
)
BASE_COORDINATES = {"hinge": 0.0, "pin_fixed": 0.0}


def feature(id, kind, label, params=None, inputs=None):
    return {
        "id": id,
        "kind": kind,
        "label": label,
        "params": params or {},
        "inputs": inputs or {},
    }


def constrained_rectangle(width, depth, origin):
    """Four shared corners with fixed anchor, H/V edges, and two dimensions."""
    points = ((0, 0), (width, 0), (width, depth), (0, depth))
    result = feature("profile", "sketch_constrained", "Dimensioned rectangular stock")
    result["sketch"] = {
        "schema_version": 1,
        "id": "stock_profile_geometry",
        "units": "mm",
        "plane": {"id": "stock_xy", "origin": list(origin), "quaternion": [1, 0, 0, 0]},
        "points": [{"id": f"p{i}", "u": p[0], "v": p[1]} for i, p in enumerate(points)],
        "lines": [{"id": f"l{i}", "start": f"p{i}", "end": f"p{(i + 1) % 4}"} for i in range(4)],
        "constraints": [
            {"id": "anchor", "kind": "fixed", "refs": ["p0"], "target": [0, 0]},
            *[
                {
                    "id": f"axis{i}",
                    "kind": "horizontal" if i % 2 == 0 else "vertical",
                    "refs": [f"l{i}"],
                }
                for i in range(4)
            ],
            {"id": "width", "kind": "distance", "refs": ["p0", "p1"], "value": "width"},
            {"id": "depth", "kind": "distance", "refs": ["p1", "p2"], "value": "depth"},
        ],
    }
    return result


def part_documents(*, radial_gap=0.2):
    """Author canonical features only; negative radial_gap is a deliberate fault."""
    common = {"schema_version": 2, "units": "mm", "active_feature": "body"}
    base = Document.from_dict(
        {
            **common,
            "id": "mechanism-clevis",
            "name": "Clevis base: slotted and bored",
            "parameters": {
                "width": 12,
                "depth": 20,
                "height": 18,
                "bore_radius": 2.5,
                "slot_width": 14,
                "slot_depth": 16,
                "slot_opening": 10,
                "slot_x": -7,
                "slot_y": -7,
                "slot_z": -5,
                "bore_z": -10,
                "bore_tool_length": 20,
            },
            "features": [
                constrained_rectangle(12, 20, (-6, -12, -9)),
                feature(
                    "pad",
                    "extrude",
                    "Extrude 18 mm stock",
                    {"length": "height"},
                    {"profile": "profile"},
                ),
                feature(
                    "slot_profile",
                    "sketch_rectangle",
                    "Overshooting open slot cutter",
                    {
                        "width": "slot_width",
                        "height": "slot_depth",
                        "x": "slot_x",
                        "y": "slot_y",
                        "z": "slot_z",
                    },
                ),
                feature(
                    "slot_tool",
                    "extrude",
                    "Slot cutter solid",
                    {"length": "slot_opening"},
                    {"profile": "slot_profile"},
                ),
                feature(
                    "slotted",
                    "cut",
                    "Cut 10 mm fork opening",
                    inputs={
                        "base": "pad",
                        "tool": "slot_tool",
                    },
                ),
                feature(
                    "bore_profile",
                    "sketch_circle",
                    "Concentric 5 mm bore",
                    {
                        "radius": "bore_radius",
                        "z": "bore_z",
                    },
                ),
                feature(
                    "bore_tool",
                    "extrude",
                    "Through-bore cutter",
                    {
                        "length": "bore_tool_length",
                    },
                    {"profile": "bore_profile"},
                ),
                feature(
                    "body",
                    "cut",
                    "Finished clevis",
                    inputs={
                        "base": "slotted",
                        "tool": "bore_tool",
                    },
                ),
            ],
        }
    )
    leaf = Document.from_dict(
        {
            **common,
            "id": "mechanism-leaf",
            "name": "Moving leaf: dimensioned stock and bore",
            "parameters": {
                "width": 8,
                "depth": 20,
                "slot_opening": 10,
                "side_gap": 0.25,
                "thickness": "slot_opening - 2 * side_gap",
                "bore_radius": 2.5,
            },
            "features": [
                constrained_rectangle(8, 20, (-4, -4, 0)),
                feature(
                    "pad",
                    "extrude",
                    "Extrude leaf thickness",
                    {"length": "thickness"},
                    {"profile": "profile"},
                ),
                feature(
                    "bore_profile",
                    "sketch_circle",
                    "Concentric 5 mm bore",
                    {
                        "radius": "bore_radius",
                    },
                ),
                feature(
                    "bore_tool",
                    "extrude",
                    "Through-bore cutter",
                    {"length": "thickness"},
                    {"profile": "bore_profile"},
                ),
                feature(
                    "body",
                    "cut",
                    "Finished leaf",
                    inputs={
                        "base": "pad",
                        "tool": "bore_tool",
                    },
                ),
            ],
        }
    )
    pin = Document.from_dict(
        {
            **common,
            "id": "mechanism-pin",
            "name": "Plain fixed pin: parameter-driven diameter",
            "parameters": {
                "bore_radius": 2.5,
                "radial_gap": radial_gap,
                "pin_radius": "bore_radius - radial_gap",
                "length": 20,
                "start_z": -10,
            },
            "features": [
                feature(
                    "profile",
                    "sketch_circle",
                    "Pin cross-section",
                    {
                        "radius": "pin_radius",
                        "z": "start_z",
                    },
                ),
                feature(
                    "body",
                    "extrude",
                    "Extrude plain pin",
                    {"length": "length"},
                    {"profile": "profile"},
                ),
            ],
        }
    )
    return {"base": base, "leaf": leaf, "pin": pin}


def make_assembly(documents=None):
    documents = part_documents() if documents is None else documents
    sources = tuple(PartSource.from_document(document) for document in documents.values())
    # Explicit authored literal frames, not inferred faces or dependent formulas.
    frames = {
        "base": MateFrame("bore_axis", Frame(), "Bore axis at fork midplane"),
        "leaf": MateFrame("bore_midplane", Frame((0, 0, 4.75)), "Bore axis at literal z=4.75 mm"),
        "pin": MateFrame("pin_midplane", Frame(), "Pin axis at pin midplane"),
    }
    parts = tuple(
        PartDefinition(name, doc.content_hash, doc.id, "body", (frames[name],), doc.name)
        for name, doc in documents.items()
    )
    preset = VerificationPreset(
        "nominal_running_clearance",
        "Illustrative running-clearance requirements",
        (
            ClearanceRequirement(
                "fork_leaf_gap", "Fork-to-leaf minimum surface gap", ("base", "leaf"), 0.20
            ),
            ClearanceRequirement(
                "fork_pin_gap", "Fork-to-pin minimum radial gap", ("base", "pin"), 0.15
            ),
            ClearanceRequirement(
                "leaf_pin_gap", "Leaf-to-pin minimum radial gap", ("leaf", "pin"), 0.15
            ),
        ),
        POLICY,
    )
    return AssemblyDocument(
        "clevis-hinge-benchmark",
        "Three-part clevis hinge benchmark",
        sources,
        parts,
        (
            Instance("base", "base", "Grounded clevis"),
            Instance("leaf", "leaf", "Revolute moving leaf"),
            Instance("pin", "pin", "Fixed plain pin"),
        ),
        (
            Joint(
                "hinge",
                "revolute",
                "base",
                "leaf",
                "bore_axis",
                "bore_midplane",
                0,
                (-math.pi / 3, math.pi / 3),
                "Leaf rotation about +Z",
            ),
            Joint(
                "pin_fixed",
                "fixed",
                "base",
                "pin",
                "bore_axis",
                "pin_midplane",
                name="Pin fixed to clevis by explicit idealization",
            ),
        ),
        "base",
        verification_presets=(preset,),
        active_verification_preset=preset.id,
    )


def boundary_control(kind):
    """Deliberate non-pass controls; nominal saved Part files are unchanged."""
    if kind == "engineering-threshold-equality":
        assembly = make_assembly()
        nominal = assembly.verification_presets[0]
        preset = replace(
            nominal,
            id="engineering_threshold_equality",
            name="Nominal gaps exactly equal engineering minima",
            requirements=tuple(
                replace(row, minimum_mm=0.25 if row.instances == ("base", "leaf") else 0.20)
                for row in nominal.requirements
            ),
        )
    elif kind in {"near-numerical-contact", "exact-fit-contact"}:
        gap = 5e-7 if kind == "near-numerical-contact" else 0.0
        assembly = make_assembly(part_documents(radial_gap=gap))
        preset = VerificationPreset(
            "contact_observation",
            "Contact boundary: explicit interference-only observation",
            (),
            POLICY,
            "interference_only",
        )
    else:
        raise ValueError(f"Unknown boundary control: {kind}")
    return replace(assembly, verification_presets=(preset,), active_verification_preset=preset.id)


def analytical_volumes(radial_gap=0.2):
    return {
        "base": 12 * 20 * 18 - 12 * 15 * 10 - math.pi * 2.5**2 * 8,
        "leaf": (8 * 20 - math.pi * 2.5**2) * 9.5,
        "pin": math.pi * (2.5 - radial_gap) ** 2 * 20,
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


def run_sidecar(request, *, timeout=120):
    env = sidecar_environment()
    process = subprocess.run(
        [sys.executable, "-B", "-m", "mechanical_cad.sidecar"],
        input=json.dumps(request, allow_nan=False),
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=env,
        timeout=timeout,
        check=False,
    )
    result = json.loads(process.stdout)
    assert process.returncode == (0 if result["ok"] else 1), process.stderr
    return result, {
        "returncode": process.returncode,
        "stderr": process.stderr,
        "timeout_s": timeout,
    }


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n")


def near(actual, expected, tolerance=1e-7):
    assert math.isclose(actual, expected, rel_tol=1e-10, abs_tol=tolerance), (actual, expected)


def pairs(report, index=0):
    return {tuple(row["instances"]): row for row in report["poses"][index]["pairs"]}


def assert_nominal(result, *, sampled=False):
    assert result["ok"] and result["report"]["complete"] and result["report"]["passed"]
    assert not result["report"]["known_interference"]
    assert not result["report"]["continuous_collision_guarantee"]
    assert result["report"]["verification_basis"]["preset_id"] == "nominal_running_clearance"
    for part in result["result"]["parts"]:
        near(part["geometry_check"]["brep"]["volume"], analytical_volumes()[part["id"]])
    rows = result["report"]["poses"]
    assert len(rows) == (len(POSE_SAMPLES) if sampled else 1)
    for index, pose in enumerate(rows):
        assert pose["pose"]["structural_dof"] == 1
        assert pose["pose"]["dof_method"] == "rooted_tree_joint_count"
        for pair, expected_gap in {
            ("base", "leaf"): 0.25,
            ("base", "pin"): 0.2,
            ("leaf", "pin"): 0.2,
        }.items():
            row = pairs(result["report"], index)[pair]
            near(row["common_volume_mm3"], 0)
            near(row["minimum_distance_mm"], expected_gap)
            assert row["clearance_verdict"] == "pass_at_pose"


def sidecar_environment():
    # Replace inherited search paths: an editable install may point elsewhere.
    return {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(SOURCE)}


def git_output(*args):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *args],
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )


def collect_provenance(*, require_clean=False, require_commit=None):
    expected_package = (SOURCE / "mechanical_cad").resolve()
    imported_package = Path(mechanical_cad.__file__).resolve().parent
    if imported_package != expected_package:
        raise ValueError(f"Imported {imported_package}; expected {expected_package}")
    # Check every already imported package module, not only __init__.py.
    for name, module in tuple(sys.modules.items()):
        if name.startswith("mechanical_cad.") and getattr(module, "__file__", None):
            if not Path(module.__file__).resolve().is_relative_to(expected_package):
                raise ValueError(f"Imported module outside this checkout: {name}")
    child_origin = subprocess.check_output(
        [
            sys.executable,
            "-B",
            "-c",
            "import mechanical_cad; from pathlib import Path; "
            "print(Path(mechanical_cad.__file__).resolve().parent)",
        ],
        cwd=ROOT,
        env=sidecar_environment(),
        text=True,
        timeout=10,
    ).strip()
    if Path(child_origin) != expected_package:
        raise ValueError(f"Sidecar would import {child_origin}; expected {expected_package}")
    commit = git_output("rev-parse", "HEAD").decode().strip()
    tracked_diff = git_output("diff", "--binary", "HEAD", "--")
    tracked_changes = git_output("diff", "--name-only", "-z", "HEAD", "--").decode().split("\0")
    untracked = git_output("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")
    tracked_changes = sorted(filter(None, tracked_changes))
    untracked = sorted(filter(None, untracked))
    clean = not tracked_changes and not untracked
    if require_commit is not None and commit != require_commit:
        raise ValueError(f"Required commit {require_commit}; current HEAD is {commit}")
    if require_clean and not clean:
        raise ValueError("--require-clean needs no tracked changes or nonignored untracked files")
    paths = git_output("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    source_files = {}
    for relative in sorted(set(filter(None, paths.decode().split("\0")))):
        path = ROOT / relative
        source_files[relative] = (
            {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "mode": path.stat().st_mode}
            if path.is_file()
            else {"missing": True}
        )
    source_tree = json.dumps(source_files, sort_keys=True, separators=(",", ":")).encode()
    distributions = {}
    for name in ("cadquery-ocp-novtk", "slvs"):
        try:
            distributions[name] = version(name)
        except PackageNotFoundError:
            distributions[name] = None
    return {
        "code_commit": commit,
        "tracked_worktree_clean": not tracked_changes,
        "worktree_clean": clean,
        "source_qualification": "clean_committed_tree" if clean else "dirty_unqualified",
        "tracked_changes": tracked_changes,
        "nonignored_untracked_files": untracked,
        "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
        "source_tree_sha256": hashlib.sha256(source_tree).hexdigest(),
        "source_file_hashes": source_files,
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "imported_package_directory": str(imported_package),
        "sidecar_imported_package_directory": child_origin,
        "interpreter": sys.executable,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "distribution_versions": distributions,
    }


def check_examples(documents, assembly):
    expected = {
        **{f"{name}.mcad.json": doc.to_json().encode("utf-8") for name, doc in documents.items()},
        "assembly.mcad-assembly.json": assembly.to_json().encode("utf-8"),
    }
    for name, content in expected.items():
        path = EXAMPLES / name
        if not path.is_file() or path.read_bytes() != content:
            raise ValueError(f"Canonical example bytes differ: {path}")
    return {name: hashlib.sha256(content).hexdigest() for name, content in expected.items()}


def generate(output, *, provenance, documents, assembly, model_hashes):
    output = Path(output).resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("Evidence directory must be outside this checkout")
    # Never overwrite an earlier run, including historical evidence elsewhere.
    output.mkdir(parents=True, exist_ok=False)
    summary = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_provenance": provenance,
        "canonical_model_sha256": model_hashes,
        "assembly_hash": assembly.content_hash,
        "source_hashes": dict(assembly.source_hashes),
        "analytical_volumes_mm3": analytical_volumes(),
        "engineering_fit_allowances_mm": {
            "nominal_radial_gap": 0.2,
            "nominal_diametral_gap": 0.4,
            "nominal_each_side_gap": 0.25,
            "required_fork_leaf_minimum": 0.20,
            "required_bore_pin_minimum": 0.15,
        },
        "numerical_policy": POLICY.to_dict(),
        "joint_limits": {"hinge_radians": [-math.pi / 3, math.pi / 3], "hinge_degrees": [-60, 60]},
        "named_pose_samples": [
            {
                "name": name,
                "degrees": angle,
                "radians": math.radians(angle),
                "coordinates": {**BASE_COORDINATES, "hinge": math.radians(angle)},
            }
            for name, angle in POSE_SAMPLES
        ],
        "cases": {},
        "part_replays": {},
        "limits": {
            "continuous_collision_guarantee": False,
            "manufacturing_or_load_certification": False,
            "gui_authoring_tested": False,
            "closed_loop_solver": False,
            "literal_frames_follow_part_edits": False,
            "motion_sampling": "Only the seven explicitly listed discrete poses are checked.",
        },
    }

    def record(name, request):
        result, process = run_sidecar(request)
        write_json(output / "evidence" / f"{name}.request.json", request)
        write_json(output / "evidence" / f"{name}.response.json", result)
        write_json(output / "evidence" / f"{name}.process.json", process)
        if "report" in result:
            summary["cases"][name] = {
                "ok": result["ok"],
                "complete": result["report"]["complete"],
                "passed": result["report"]["passed"],
                "status": result["report"]["status"],
                "request_fingerprint": result["request_fingerprint"],
                "report_fingerprint": result["report_fingerprint"],
                "poses": result["report"]["poses"],
                "error": result["error"],
            }
        return result

    for name, document in documents.items():
        request = {
            "protocol_version": 1,
            "action": "canonical_snapshot",
            "document": document.to_dict(),
        }
        receipt = record(f"{name}-snapshot", request)["result"]
        assert receipt["content_hash"] == document.content_hash
        assert receipt["canonical_json"] == document.to_json()
        (output / f"{name}.mcad.json").write_text(receipt["canonical_json"])
        replay = record(
            f"{name}-replay",
            {
                "protocol_version": 1,
                "document": receipt["canonical_document"],
                "options": {"linear_deflection": POLICY.linear_deflection_mm},
            },
        )
        assert replay["ok"] and replay["result"]["document_hash"] == receipt["content_hash"]
        feature_rows = replay["result"]["features"]
        assert all(row["status"] == "ok" for row in feature_rows)
        body = next(row for row in feature_rows if row["id"] == "body")
        near(body["stats"]["volume"], analytical_volumes()[name])
        sketches = {row["id"]: row["sketch"] for row in feature_rows if "sketch" in row}
        for sketch in sketches.values():
            assert sketch["status"] == "okay" and sketch["remaining_dof"] == 0
        summary["part_replays"][name] = {
            "status": replay["result"]["status"],
            "body_stats": body["stats"],
            "parameters": replay["result"]["parameters"],
            "sketches": sketches,
        }

    (output / "assembly.mcad-assembly.json").write_text(assembly.to_json())
    reopened = AssemblyDocument.from_json((output / "assembly.mcad-assembly.json").read_text())
    assert reopened.content_hash == assembly.content_hash
    replay = record("assembly-replay", assembly_request(assembly, "assembly_replay"))
    assert replay["ok"] and not replay["report"]["passed"]
    nominal = record("neutral-check", assembly_request(assembly))
    assert_nominal(nominal)
    summary["native_runtime_versions"] = nominal["report"]["native_runtime_versions"]
    summary["service_runtime_versions"] = nominal["request"]["runtime_versions"]
    sampled = record(
        "seven-pose-sample",
        assembly_request(
            assembly,
            "assembly_sample",
            samples={"joint_id": "hinge", "values": [math.radians(a) for _, a in POSE_SAMPLES]},
        ),
    )
    assert_nominal(sampled, sampled=True)
    for row, (_, angle) in zip(sampled["report"]["poses"], POSE_SAMPLES, strict=True):
        assert row["pose"]["effective_coordinates"] == {
            **BASE_COORDINATES,
            "hinge": math.radians(angle),
        }

    oversized = make_assembly(part_documents(radial_gap=-0.1))
    bad = record("oversized-pin-interference", assembly_request(oversized))
    assert bad["ok"] and bad["report"]["complete"] and bad["report"]["known_interference"]
    assert not bad["report"]["passed"]
    for pair, bore_length in {("base", "pin"): 8, ("leaf", "pin"): 9.5}.items():
        row = pairs(bad["report"])[pair]
        near(row["common_volume_mm3"], math.pi * (2.6**2 - 2.5**2) * bore_length)
        assert row["known_interference"]

    narrow = make_assembly(part_documents(radial_gap=0.1))
    tight = record("insufficient-radial-clearance", assembly_request(narrow))
    assert tight["ok"] and not tight["report"]["passed"]
    assert tight["report"]["known_clearance_violation"]
    assert not tight["report"]["known_interference"]
    for pair in (("base", "pin"), ("leaf", "pin")):
        near(pairs(tight["report"])[pair]["minimum_distance_mm"], 0.1)

    for kind in (
        "engineering-threshold-equality",
        "near-numerical-contact",
        "exact-fit-contact",
    ):
        boundary = record(kind, assembly_request(boundary_control(kind)))
        report = boundary["report"]
        assert boundary["ok"] and report["complete"]
        assert report["status"] == "checked_with_threshold_contacts"
        assert report["has_threshold_contacts"] and not report["passed"]
        assert not report["known_interference"] and not report["known_clearance_violation"]
        for pair, row in pairs(report).items():
            if kind == "engineering-threshold-equality":
                near(row["minimum_distance_mm"], row["minimum_required_mm"])
                assert row["relation"] == "separated"
                assert row["clearance_verdict"] == "at_threshold"
            elif "pin" in pair:
                near(row["minimum_distance_mm"], 5e-7 if kind == "near-numerical-contact" else 0)
                assert row["relation"] == "contact_or_near"
                assert row["clearance_verdict"] == "at_threshold"
                assert row["minimum_required_mm"] == 0

    unconfigured = replace(assembly, active_verification_preset=None)
    measured = record("no-selected-preset", assembly_request(unconfigured))
    assert measured["ok"] and measured["report"]["complete"]
    assert not measured["report"]["passed"]
    assert all(
        row["clearance_verdict"] == "measurement_only"
        for row in measured["report"]["poses"][0]["pairs"]
    )

    blocked = record(
        "outside-motion-limit",
        assembly_request(
            assembly,
            coordinates={**BASE_COORDINATES, "hinge": math.radians(61)},
        ),
    )
    assert not blocked["ok"] and not blocked["report"]["passed"]
    assert blocked["report"]["base_pose"]["effective_coordinates"] == {}
    assert not blocked["result"]["source_replays"]
    assert blocked["report"]["base_pose"]["diagnostics"][0]["code"] == "limit_violation"

    final_provenance = collect_provenance()
    for key in ("code_commit", "source_tree_sha256", "tracked_diff_sha256"):
        if final_provenance[key] != provenance[key]:
            raise ValueError(f"Source changed during evidence capture: {key}")
    summary["source_stability_verified"] = True
    write_json(output / "evidence" / "summary.json", summary)
    files = sorted(
        path for path in output.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    )
    (output / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output)}\n"
            for path in files
        )
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-dir", type=Path, help="new directory outside this checkout for native evidence"
    )
    parser.add_argument("--require-clean", action="store_true", help="reject an uncommitted tree")
    parser.add_argument("--require-commit", help="require this exact full commit ID")
    args = parser.parse_args()
    try:
        provenance = collect_provenance(
            require_clean=args.require_clean, require_commit=args.require_commit
        )
        documents = part_documents()
        assembly = make_assembly(documents)
        model_hashes = check_examples(documents, assembly)
        result = {
            "mode": "check_only",
            "canonical_model_sha256": model_hashes,
            "source_provenance": {
                key: value for key, value in provenance.items() if key != "source_file_hashes"
            },
            "numerical_policy": POLICY.to_dict(),
        }
        if args.evidence_dir is not None:
            summary = generate(
                args.evidence_dir,
                provenance=provenance,
                documents=documents,
                assembly=assembly,
                model_hashes=model_hashes,
            )
            result.update(
                mode="native_evidence",
                evidence_directory=str(args.evidence_dir.resolve()),
                case_statuses={key: row["status"] for key, row in summary["cases"].items()},
            )
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
