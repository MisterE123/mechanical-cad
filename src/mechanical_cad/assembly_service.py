"""Fresh canonical-part replay and bounded exact assembly verification.

No native shape or prior verification is accepted from a client. Source updates
are preflighted as complete candidates; the caller publishes a candidate only in
its own atomic UI transaction. This module writes no files.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from itertools import combinations

from . import __version__
from .assembly_kinematics import EVALUATOR_VERSION, effective_coordinate_map, evaluate
from .assembly_model import AssemblyDocument, Frame, replace_source
from .assembly_policy import (
    POLICY_VERSION,
    CheckPolicy,
    aggregate_evidence,
    clearance_requirements,
    fingerprint,
    intended_contact_acceptance,
    request_snapshot,
    sample_request,
    typed_request_fingerprint,
)
from .engine import regenerate, validate_result_version
from .errors import CADException
from .outputs import require_solid
from .part_snapshot import validate_snapshot_source

ASSEMBLY_ACTIONS = frozenset({"assembly_replay", "assembly_check", "assembly_sample"})
BACKEND_CAPABILITIES = frozenset({"mcad.assembly-result/3", "mcad.assembly-step-export/1"})


@dataclass(frozen=True)
class _CheckedAssemblyNative:
    """Private, same-invocation native state; never serialized or accepted as input."""

    kernel: object
    shapes: dict
    transforms: dict


def _verification_context(assembly, action, preset_id, requirements, policy):
    """Resolve explicit authored intent without inventing a clearance policy."""
    basis = {"kind": "not_requested", "preset_id": None, "preset": None, "configured": False}
    if preset_id is not None and (type(preset_id) is not str or not preset_id):
        raise CADException("invalid_preset", "Verification preset must be an explicit ID.")
    if action == "assembly_replay":
        if preset_id is not None:
            raise CADException("invalid_request", "Replay does not evaluate a verification preset.")
        supplied = CheckPolicy.from_dict({} if policy is None else policy)
        if assembly.replay_tolerance_mm is not None and (
            policy is None or "linear_tolerance_mm" not in policy
        ):
            supplied = CheckPolicy.from_dict(
                {**supplied.to_dict(), "linear_tolerance_mm": assembly.replay_tolerance_mm}
            )
        return supplied, {}, basis
    selected = (
        preset_id
        if preset_id is not None
        else getattr(assembly, "active_verification_preset", None)
    )
    if selected:
        preset = next((p for p in assembly.verification_presets if p.id == selected), None)
        if preset is None:
            raise CADException("missing_preset", "The selected verification preset does not exist.")
        if requirements is not None or policy is not None:
            raise CADException(
                "conflicting_policy",
                "A saved preset cannot be silently mixed with ad-hoc overrides.",
            )
        clearances = clearance_requirements(
            assembly,
            [
                {"instances": list(row.instances), "minimum_mm": row.minimum_mm}
                for row in preset.requirements
            ],
        )
        basis.update(
            kind=preset.kind, preset_id=preset.id, preset=preset.to_dict(), configured=True
        )
        return CheckPolicy.from_dict(preset.policy.to_dict()), clearances, basis
    configured = requirements is not None
    basis.update(
        kind=("ad_hoc_clearance" if requirements else "ad_hoc_interference_only")
        if configured
        else "unconfigured",
        configured=configured,
    )
    return (
        CheckPolicy.from_dict({} if policy is None else policy),
        clearance_requirements(assembly, requirements),
        basis,
    )


def runtime_versions():
    """Distribution versions remain available even for rejected pre-kernel input."""
    result = {"mechanical_cad": __version__, "evaluator": EVALUATOR_VERSION}
    for name in ("cadquery-ocp-novtk", "cadquery-ocp-proxy", "slvs"):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = "unavailable"
    return result


def _diagnostic(exc, subject=None):
    result = (
        exc.to_dict()
        if isinstance(exc, CADException)
        else {"code": "assembly_kernel_error", "message": f"{type(exc).__name__}: {exc}"}
    )
    return {**result, "subject": subject}


def _build_parts(assembly, kernel, policy, result, result_version):
    """Replay each source once, then validate each explicit output once."""
    replays, outputs, shapes, payloads = {}, {}, {}, []
    resolved_frames = {}
    for source in assembly.part_sources:
        replay = regenerate(
            source.document,
            kernel,
            linear_deflection=policy.linear_deflection_mm,
            result_version=result_version,
        )
        result["source_replays"].append(
            {
                "source_document_id": source.id,
                "source_digest": source.source_digest,
                "status": replay.result["status"],
                "features": [
                    {
                        key: row.get(key)
                        for key in ("id", "status", "error", "stats")
                        + (("output",) if result_version in (2, 3) else ())
                    }
                    for row in replay.result["features"]
                ],
                **({"replay": replay.result} if result_version == 3 else {}),
            }
        )
        if not replay.ok:
            raise CADException("source_replay_failed", f"Part source {source.id} failed replay.")
        replays[source.id] = replay
    for part in assembly.parts:
        key = (part.source_document_id, part.source_digest, part.output_feature_id)
        if key not in outputs:
            replay = replays[part.source_document_id]
            shape = require_solid(replay.outputs[part.output_feature_id], part.output_feature_id)
            checks = kernel.manufacturing_check(shape, policy.linear_deflection_mm)
            row = next(f for f in replay.result["features"] if f["id"] == part.output_feature_id)
            outputs[key] = (shape, checks, row)
        shape, checks, row = outputs[key]
        shapes[part.id] = shape
        resolved = {}
        for frame in part.mate_frames:
            placement = frame.placement
            if frame.support_face is not None:
                try:
                    origin, quaternion = kernel.supported_workplane(shape, frame.support_face)
                    placement = Frame(origin, quaternion).then(frame.placement)
                except Exception as exc:
                    raise CADException(
                        "unresolved_mate_face",
                        f"Mate frame {part.name} / {frame.name}: support face is missing, split, "
                        f"ambiguous, or nonplanar. Repair its named face reference. {exc}",
                    ) from exc
            resolved_frames[(part.id, frame.id)] = placement
            resolved[frame.id] = placement.to_dict()
        associative = any(frame.support_face is not None for frame in part.mate_frames)
        payloads.append(
            {
                "id": part.id,
                "name": part.name,
                "source_document_id": part.source_document_id,
                "source_digest": part.source_digest,
                "output_feature_id": part.output_feature_id,
                "geometry_check": checks,
                "mesh": row["mesh"],
                "topology": row["topology"],
                "mate_frames": [frame.to_dict() for frame in part.mate_frames],
                "datum_policy": "stable_planar_face_or_literal"
                if associative
                else "literal_part_local_coordinates",
                **({"resolved_mate_frames": resolved} if associative else {}),
            }
        )
    result["parts"] = payloads
    return shapes, resolved_frames


def _unknown_pair(pair, required, message):
    return {
        "instances": list(pair),
        "relation": "unknown",
        "common_volume_mm3": None,
        "minimum_distance_mm": None,
        "minimum_required_mm": required,
        "clearance_verdict": "indeterminate",
        "witness_points_mm": None,
        "complete": False,
        "known_interference": False,
        "known_clearance_violation": False,
        "diagnostics": [{"code": "missing_current_placement", "message": message}],
    }


def _at_pose(
    assembly,
    coordinates,
    shapes,
    kernel,
    policy,
    requirements,
    *,
    check,
    configured,
    resolved_frames=None,
):
    pose = evaluate(assembly, coordinates, resolved_frames=resolved_frames)
    report = {
        "pose": pose.to_dict(),
        "pairs": [],
        "diagnostics": [d.to_dict() for d in pose.diagnostics],
        "scope": "static_exact_brep_at_requested_pose" if check else "validated_rigid_placement",
    }
    if pose.status != "evaluated":
        report.update(aggregate_evidence((), complete=False))
        report["status"] = "blocked"
        return report
    world = {}
    for instance in assembly.instances:
        try:
            world[instance.id] = kernel.transformed(
                shapes[instance.part_id],
                pose.transforms[instance.id],
                linear_tolerance_mm=policy.linear_tolerance_mm,
            )
        except Exception as exc:
            report["diagnostics"].append(_diagnostic(exc, instance.id))
    if check:
        for pair in combinations(sorted(i.id for i in assembly.instances), 2):
            required = requirements.get(pair, 0.0)
            if any(instance not in world for instance in pair):
                row = _unknown_pair(
                    pair, required, "An instance has no validated current placement."
                )
            else:
                try:
                    row = kernel.pair_check(
                        *(world[instance] for instance in pair),
                        minimum_required_mm=required,
                        linear_tolerance_mm=policy.linear_tolerance_mm,
                        volume_tolerance_mm3=policy.volume_tolerance_mm3,
                    )
                    row = {**row, "instances": list(pair)}
                except Exception as exc:
                    row = _unknown_pair(pair, required, str(exc))
                    row["diagnostics"] = [_diagnostic(exc)]
            if not configured and row["clearance_verdict"] == "pass_at_pose":
                row = {**row, "clearance_verdict": "measurement_only"}
            report["pairs"].append(row)
    report.update(aggregate_evidence(report["pairs"], complete=not report["diagnostics"]))
    if not check and report["complete"]:
        report["status"] = "replayed"
        report["passed"] = False  # A display replay is never a clearance verification.
    if not configured:
        report["passed"] = False
    return report


def run_assembly_action(
    assembly: AssemblyDocument,
    action="assembly_replay",
    *,
    coordinates=None,
    requirements=None,
    policy=None,
    samples=None,
    preset_id=None,
    result_version=1,
    kernel=None,
):
    """Return fresh display data plus evidence bound to every requested input.

    `ok` means the requested operation completed, not that a mechanism is safe.
    Use report.passed/complete/known_* and retain the entire report. Motion accepts
    an explicit FULL base coordinate map; every listed pose keeps the other joints.
    Embedded sketch schema 2 requires explicit result_version=2. Supported
    sector sources require result_version=3, with full source replay evidence.
    Versions 1 and 2 retain their original response shapes and identities.
    """
    response, _ = _run_assembly_action_with_native(
        assembly,
        action,
        coordinates=coordinates,
        requirements=requirements,
        policy=policy,
        samples=samples,
        preset_id=preset_id,
        result_version=result_version,
        kernel=kernel,
    )
    return response


def _run_assembly_action_with_native(
    assembly: AssemblyDocument,
    action="assembly_replay",
    *,
    coordinates=None,
    requirements=None,
    policy=None,
    samples=None,
    preset_id=None,
    result_version=1,
    kernel=None,
):
    """Run the unchanged service, retaining a fresh successful current check only."""
    if type(assembly) is not AssemblyDocument:
        raise CADException("invalid_assembly", "Expected an AssemblyDocument snapshot.")
    # Own the accepted Mapping view before hashing/evaluation/native work. In
    # particular PoseResult.effective_coordinates is an immutable mappingproxy.
    if isinstance(coordinates, Mapping):
        coordinates = dict(coordinates)
    # Version 1, including an explicit 1, retains the original service identity.
    # Every other value participates in both forensic and type-tagged identity,
    # even when validation below rejects it before native work.
    version_arguments = (
        {}
        if type(result_version) is int and result_version == 1
        else {"result_version": result_version}
    )
    request = {
        **{key: request_snapshot(value) for key, value in version_arguments.items()},
        "assembly_digest": assembly.content_hash,
        "source_hashes": dict(assembly.source_hashes),
        "action": request_snapshot(action),
        "requested_coordinates": request_snapshot(coordinates),
        "requirements": request_snapshot(requirements),
        "policy": request_snapshot(policy),
        "samples": request_snapshot(samples),
        "preset_id": request_snapshot(preset_id),
        "argument_types_fingerprint": typed_request_fingerprint(
            {
                "action": action,
                "coordinates": coordinates,
                "requirements": requirements,
                "policy": policy,
                "samples": samples,
                "preset_id": preset_id,
                **version_arguments,
            }
        ),
        "policy_version": POLICY_VERSION,
        "runtime_versions": runtime_versions(),
    }
    response = {
        **(
            {"result_version": result_version}
            if type(result_version) is int and result_version in (2, 3)
            else {}
        ),
        "ok": False,
        "action": action if isinstance(action, str) else None,
        "request": request,
        "request_fingerprint": fingerprint(request),
        "result": {
            "canonical_assembly": assembly.to_dict(),
            "assembly_digest": assembly.content_hash,
            "source_hashes": dict(assembly.source_hashes),
            "source_replays": [],
            "parts": [],
            "instances": [instance.to_dict() for instance in assembly.instances],
        },
        "report": {**aggregate_evidence((), complete=False), "status": "blocked", "poses": []},
        "error": None,
    }
    report = response["report"]
    try:
        if result_version != 3 and any(
            frame.support_face is not None for part in assembly.parts for frame in part.mate_frames
        ):
            raise CADException(
                "unsupported_result_version", "Associative mate frames require result_version 3."
            )
        # Validate every source before constructing a native kernel or replaying
        # an earlier legacy source in a mixed assembly.
        for source in assembly.part_sources:
            if result_version != 3 and any(
                feature.support_face is not None
                or feature.end_face is not None
                or feature.projections
                for feature in source.document.features
            ):
                raise CADException(
                    "unsupported_result_version",
                    "Associative face references require result_version 3 with full source replay evidence.",
                )
            if type(result_version) is int and result_version == 3:
                from .result_policy_v3 import validate_replay_v3

                validate_snapshot_source(source.document)
                validate_replay_v3(source.document, result_version)
            else:
                validate_result_version(source.document, result_version)
        if type(action) is not str or action not in ASSEMBLY_ACTIONS:
            raise CADException("invalid_action", "Unsupported assembly action.")
        checked_policy, clearances, basis = _verification_context(
            assembly, action, preset_id, requirements, policy
        )
        report["verification_basis"] = basis
        report["effective_policy"] = checked_policy.to_dict()
        if action == "assembly_replay" and requirements not in (None, []):
            raise CADException(
                "invalid_request", "Replay does not evaluate clearance requirements."
            )
        if action != "assembly_sample" and samples is not None:
            raise CADException("invalid_request", "Only sampling accepts an explicit sample list.")
        associative = any(f.support_face is not None for p in assembly.parts for f in p.mate_frames)
        if not associative:
            base_pose = evaluate(assembly, coordinates)
            report["base_pose"] = base_pose.to_dict()
            if base_pose.status != "evaluated":
                raise CADException(
                    "invalid_pose", "The requested pose is blocked; see pose diagnostics."
                )
        else:
            effective_coordinate_map(assembly, coordinates)
        if action == "assembly_sample":
            joint_id, values = sample_request(assembly, samples, coordinates)
            # Revalidate and copy the full effective base once. No saved-value fallback.
            base = effective_coordinate_map(assembly, coordinates)
            driven = {r.driven_joint for r in assembly.gear_relations}
            base = {key: value for key, value in base.items() if key not in driven}
            pose_requests = [{**base, joint_id: value} for value in values]
        else:
            pose_requests = [coordinates]
        if kernel is None:
            from .kernel_ocp import OCPKernel

            kernel = OCPKernel()
        report["native_runtime_versions"] = kernel.runtime_versions()
        shapes, resolved_frames = _build_parts(
            assembly, kernel, checked_policy, response["result"], result_version
        )
        base_pose = evaluate(assembly, coordinates, resolved_frames=resolved_frames)
        report["base_pose"] = base_pose.to_dict()
        if base_pose.status != "evaluated":
            raise CADException(
                "invalid_pose", "The requested pose is blocked; see pose diagnostics."
            )
        report["poses"] = [
            _at_pose(
                assembly,
                pose_request,
                shapes,
                kernel,
                checked_policy,
                clearances,
                check=action != "assembly_replay",
                configured=basis["configured"],
                resolved_frames=resolved_frames,
            )
            for pose_request in pose_requests
        ]
        report.update(aggregate_evidence(report["poses"]))
        if action == "assembly_replay" and report["complete"]:
            report.update(status="replayed", passed=False)
        if not basis["configured"]:
            report["passed"] = False
        response["ok"] = report["complete"]
    except Exception as exc:
        response["error"] = _diagnostic(exc)
    acceptance = intended_contact_acceptance(report, [i.id for i in assembly.instances])
    if acceptance is not None:
        report["policy_accepted"] = acceptance
    report["scope"] = (
        "only_listed_discrete_poses" if action == "assembly_sample" else "single_requested_pose"
    )
    report["continuous_collision_guarantee"] = False
    report["manufacturing_or_load_certification"] = False
    report["request_fingerprint"] = response["request_fingerprint"]
    response["report_fingerprint"] = fingerprint(
        {
            "request": request,
            "report": report,
            "error": response["error"],
            "source_replays": response["result"]["source_replays"],
        }
    )
    checked_native = None
    if (
        type(action) is str
        and action == "assembly_check"
        and response["ok"] is True
        and response["error"] is None
        and report["complete"] is True
        and (report["passed"] is True or report.get("policy_accepted") is True)
        and coordinates is None
        and requirements is None
        and policy is None
        and samples is None
        and assembly.active_verification_preset is not None
        and preset_id in (None, assembly.active_verification_preset)
        and report["verification_basis"]["configured"] is True
        and report["verification_basis"]["preset_id"] == assembly.active_verification_preset
        and len(report["poses"]) == 1
        and report["poses"][0]["pose"]["status"] == "evaluated"
        and report["poses"][0]["pose"] == report["base_pose"]
    ):
        checked_native = _CheckedAssemblyNative(
            kernel, shapes, report["poses"][0]["pose"]["transforms"]
        )
    return response, checked_native


def preflight_source_update(
    assembly, source_document_id, document, *, kernel=None, policy=None, result_version=1
):
    """Freshly replay an all-instance update, leaving the accepted assembly untouched."""
    candidate = replace_source(assembly, source_document_id, document)
    response = run_assembly_action(
        candidate, policy=policy, kernel=kernel, result_version=result_version
    )
    affected_parts = {p.id for p in assembly.parts if p.source_document_id == source_document_id}
    response["update"] = {
        "previous_assembly_digest": assembly.content_hash,
        "candidate_assembly_digest": candidate.content_hash,
        "affected_instances": [i.id for i in assembly.instances if i.part_id in affected_parts],
        "literal_frames_unchanged": True,
        "candidate": candidate.to_dict() if response["ok"] else None,
        "publication_required": True,
    }
    return response
