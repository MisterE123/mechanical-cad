"""Strict assembly transport and accepted-response lifecycle.

Hashes reject stale/mismatched replies; geometry authority stays in the isolated
sidecar. Schema and evidence validators remain native-free, acyclic modules."""

from __future__ import annotations

import copy
from itertools import combinations

from . import bridge, part_contracts, part_snapshot_bridge, request_contracts, sidecar_job
from .assembly_validation_common import (
    ACTIONS,
    ASSEMBLY_PROTOCOL_VERSION,
    EVALUATOR_VERSION,
    FLAGS,
    MAX_PAIR_QUERIES,
    MAX_SAMPLES,
    POLICY_VERSION,
    _diagnostics,
    _finite_tree,
    _hash,
    _keys,
    _number,
    _require,
    _versions,
    fingerprint,
)
from .assembly_validation_common import DEFAULT_POLICY as DEFAULT_POLICY
from .assembly_validation_common import canonical_digest as canonical_digest
from .assembly_validation_evidence import (
    _aggregate,
    _contact_acceptance,
    _effective,
    _pair,
    _pose,
)
from .assembly_validation_model import (
    _canonical,
    _parts,
    _policy,
    _verification_basis,
)
from .assembly_validation_model import validate_mesh as validate_mesh

_RESULT_VERSION_HELP = (
    "Assembly result version 2 requires a matching add-on and sidecar. "
    "Upgrade both and explicitly request result_version 2; no legacy fallback is supported."
)


def _result_version_help(version):
    return (
        _RESULT_VERSION_HELP
        if version == 2
        else (
            "Assembly result version 3 requires a matching add-on and sidecar. "
            "Upgrade both and explicitly request result_version 3; no legacy fallback is supported."
        )
    )


def _result_version(value):
    if type(value) is not int or value not in (1, 2, 3):
        raise bridge.BridgeError("Only assembly result versions 1, 2 and 3 are supported.")
    return value


def _uses_sketch_v2(assembly):
    """Detect explicit new payload intent without introducing a second normalizer."""
    if type(assembly) is not dict or type(assembly.get("part_sources")) is not list:
        return False
    for source in assembly["part_sources"]:
        if type(source) is not dict or type(source.get("document")) is not dict:
            continue
        features = source["document"].get("features")
        if type(features) is not list:
            continue
        for feature in features:
            if type(feature) is dict and type(feature.get("sketch")) is dict:
                if feature["sketch"].get("schema_version") == 2:
                    return True
    return False


class AssemblyResponse(dict):
    """Legacy validated projection; production authority stays in guarded evidence."""

    def __init__(self, response, request):
        super().__init__(copy.deepcopy(response))
        self._request = copy.deepcopy(request)
        self._validated_fingerprint = fingerprint(self)

    def request_snapshot(self):
        """Return detached exact input JSON for persistence and later revalidation."""
        self.assert_unchanged()
        return copy.deepcopy(self._request)

    def assert_unchanged(self):
        try:
            unchanged = fingerprint(self) == self._validated_fingerprint
        except (TypeError, ValueError, OverflowError, RecursionError):
            unchanged = False
        if not unchanged:
            raise bridge.BridgeError(
                "Validated assembly response was changed; replay it before display."
            )
        return self


def validate_response(request, response):
    """Validate all report identities/evidence before accepting any display state."""
    try:
        if (
            type(request) is dict
            and type(request.get("result_version")) is int
            and request["result_version"] in (2, 3)
        ):
            # Bound expanded direct-Python containers before any nonmemoized
            # traversal or copying; JSON byte limits alone do not bound DAGs.
            request = request_contracts.snapshot_request(request)
            part_contracts._bounded_response(response)
        _finite_tree(request)
        _finite_tree(response)
        _require(
            type(request) is dict and type(response) is dict, "expected request/response objects"
        )
        result_version = _result_version(request.get("result_version", 1))
        if result_version in (2, 3):
            _require(
                type(response.get("result_version")) is int
                and response["result_version"] == result_version,
                _result_version_help(result_version),
            )
        fields = {
            "protocol_version",
            "kind",
            "assembly_protocol_version",
            "input_fingerprint",
            "ok",
            "action",
            "request",
            "request_fingerprint",
            "result",
            "report",
            "report_fingerprint",
            "error",
        }
        _keys(response, fields | ({"result_version"} if result_version in (2, 3) else set()))
        _require(
            type(response["protocol_version"]) is int
            and response["protocol_version"] == 1
            and response["kind"] == "assembly"
            and type(response["assembly_protocol_version"]) is int
            and response["assembly_protocol_version"] == ASSEMBLY_PROTOCOL_VERSION,
            "assembly protocol mismatch",
        )
        _require(type(response["ok"]) is bool, "invalid success flag")
        _require(
            response["input_fingerprint"] == fingerprint(request),
            "stale or different raw request fingerprint",
        )
        _require(
            response["action"] == request["action"] and response["action"] in ACTIONS,
            "action mismatch",
        )
        result = response["result"]
        _keys(
            result,
            {
                "assembly_digest",
                "source_hashes",
                "canonical_assembly",
                "source_replays",
                "parts",
                "instances",
            },
        )
        canonical_request = request
        if result_version in (2, 3):
            # Embedded Part serializers may reorder stable-ID sketch records.
            # Validate that normalization first, then keep the legacy assembly
            # comparison strict everywhere outside those already-bound sources.
            canonical_request = copy.deepcopy(request)
            canonical_sources = {
                source["source_document_id"]: source["document"]
                for source in result["canonical_assembly"]["part_sources"]
            }
            for source in canonical_request["assembly"]["part_sources"]:
                canonical_source = canonical_sources[source["source_document_id"]]
                _require(
                    (
                        result_version == 3
                        or not part_snapshot_bridge._uses_schema3(source["document"])
                    )
                    and part_snapshot_bridge.canonical_equivalent(
                        source["document"], canonical_source
                    ),
                    "canonical Part source differs from the supported serializer",
                )
                source["document"] = copy.deepcopy(canonical_source)
        canonical, definitions, instances, joints = _canonical(canonical_request, result)
        if result_version == 1 and _uses_sketch_v2(canonical):
            _require(
                response["ok"] is False
                and type(response["error"]) is dict
                and response["error"].get("code") == "unsupported_result_version"
                and not result["source_replays"]
                and not result["parts"],
                _RESULT_VERSION_HELP,
            )
        _require(result["instances"] == canonical["instances"], "instance identities differ")
        echo = response["request"]
        _keys(
            echo,
            {
                "assembly_digest",
                "source_hashes",
                "action",
                "requested_coordinates",
                "requirements",
                "policy",
                "samples",
                "policy_version",
                "runtime_versions",
                "argument_types_fingerprint",
                "preset_id",
            }
            | ({"result_version"} if result_version in (2, 3) else set()),
        )
        if result_version in (2, 3):
            _require(
                type(echo["result_version"]) is int and echo["result_version"] == result_version,
                "service request echo changed result_version",
            )
        for key in ("assembly_digest", "source_hashes"):
            _require(echo[key] == result[key], "request revision mismatch")
        for key in ("action", "requirements", "policy", "samples", "preset_id"):
            _require(
                fingerprint(echo[key]) == fingerprint(request.get(key)),
                "service request echo changed " + key,
            )
        _require(
            fingerprint(echo["requested_coordinates"]) == fingerprint(request.get("coordinates")),
            "service request echo changed coordinates",
        )
        _require(echo["policy_version"] == POLICY_VERSION, "unsupported check policy")
        _versions(echo["runtime_versions"])
        _hash(echo["argument_types_fingerprint"])
        _require(
            echo["runtime_versions"].get("evaluator") == EVALUATOR_VERSION,
            "evaluator version mismatch",
        )
        _require(
            response["request_fingerprint"] == fingerprint(echo), "request fingerprint mismatch"
        )
        report = response["report"]
        _keys(
            report,
            FLAGS
            | {
                "status",
                "poses",
                "scope",
                "continuous_collision_guarantee",
                "manufacturing_or_load_certification",
                "request_fingerprint",
            },
            {
                "base_pose",
                "effective_policy",
                "native_runtime_versions",
                "verification_basis",
                "policy_accepted",
            },
        )
        _require(
            report["request_fingerprint"] == response["request_fingerprint"],
            "report belongs to another request",
        )
        _require(
            response["report_fingerprint"]
            == fingerprint(
                {
                    "request": echo,
                    "report": report,
                    "error": response["error"],
                    "source_replays": result["source_replays"],
                }
            ),
            "report fingerprint mismatch",
        )
        _require(
            report["continuous_collision_guarantee"] is False
            and report["manufacturing_or_load_certification"] is False,
            "unsupported verification guarantee",
        )
        action = request["action"]
        _require(
            report["scope"]
            == (
                "only_listed_discrete_poses"
                if action == "assembly_sample"
                else "single_requested_pose"
            ),
            "report scope mismatch",
        )
        if response["error"] is not None:
            _diagnostics([response["error"]])
        _require(
            not response["ok"] or response["error"] is None, "successful response also has an error"
        )
        _require(
            type(report["poses"]) is list and len(report["poses"]) <= MAX_SAMPLES,
            "pose count exceeds limit",
        )
        _require(
            report["poses"] or response["error"] is not None,
            "blocked result has no error diagnostics",
        )
        _parts(
            result,
            canonical,
            definitions,
            response["ok"],
            strict=result_version == 2,
            strict_v3=result_version == 3,
        )
        if "base_pose" in report:
            _pose(report["base_pose"], request.get("coordinates"), result, joints, instances)
        configured, resolved_requirements, resolved_policy = _verification_basis(
            request, canonical, report
        )
        policy = report.get("effective_policy")
        if policy is not None:
            _policy(policy)
            _require(
                policy == resolved_policy,
                "effective tolerances differ from selected verification basis",
            )
            for part in result["parts"]:
                _require(
                    part["geometry_check"]["linear_deflection_mm"]
                    == policy["linear_deflection_mm"],
                    "part mesh used a different deflection policy",
                )
        if "native_runtime_versions" in report:
            _versions(report["native_runtime_versions"])
        if report["poses"]:
            _require(
                policy is not None
                and "native_runtime_versions" in report
                and report["base_pose"]["status"] == "evaluated",
                "poses have no validated base/policy/runtime",
            )
            _parts(
                result,
                canonical,
                definitions,
                True,
                strict=result_version == 2,
                strict_v3=result_version == 3,
            )
            relations = canonical.get("gear_relations", [])
            base = _effective(joints, request.get("coordinates"), relations)
            driven = {row["driven_joint"] for row in relations}
            if base is not None:
                base = {key: value for key, value in base.items() if key not in driven}
            requests = [request.get("coordinates")]
            if action == "assembly_sample":
                samples = request.get("samples")
                _keys(samples, {"joint_id", "values"})
                _require(
                    type(request.get("coordinates")) is dict
                    and set(request["coordinates"]) == set(base),
                    "samples omit full base coordinates",
                )
                _require(
                    samples["joint_id"] in base
                    and (
                        ":" in samples["joint_id"]
                        or joints[samples["joint_id"]]["kind"]
                        not in {"fixed", "planar", "spherical"}
                    ),
                    "invalid sampled joint",
                )
                _require(
                    type(samples["values"]) is list and 1 <= len(samples["values"]) <= MAX_SAMPLES,
                    "invalid explicit samples",
                )
                requests = [{**base, samples["joint_id"]: value} for value in samples["values"]]
            _require(len(report["poses"]) == len(requests), "sample list truncated or extended")
            pairs = list(combinations(sorted(instances), 2))
            _require(len(pairs) * len(requests) <= MAX_PAIR_QUERIES, "pair query budget exceeded")
            requirements = {}
            for row in resolved_requirements:
                _keys(row, {"instances", "minimum_mm"})
                pair = tuple(sorted(row["instances"]))
                _require(pair in pairs and pair not in requirements, "invalid pair requirement")
                _number(row["minimum_mm"], bound=1e6, minimum=0)
                requirements[pair] = row["minimum_mm"]
            for row, pose_request in zip(report["poses"], requests, strict=True):
                _keys(row, FLAGS | {"pose", "pairs", "diagnostics", "scope", "status"})
                _pose(row["pose"], pose_request, result, joints, instances)
                _diagnostics(row["diagnostics"])
                replay, blocked = action == "assembly_replay", row["pose"]["status"] == "blocked"
                _require(
                    row["scope"]
                    == (
                        "validated_rigid_placement"
                        if replay
                        else "static_exact_brep_at_requested_pose"
                    ),
                    "pose scope mismatch",
                )
                expected_pairs = [] if replay or blocked else pairs
                _require(
                    type(row["pairs"]) is list and len(row["pairs"]) == len(expected_pairs),
                    "pair list incomplete or unexpected",
                )
                for pair_row, pair in zip(row["pairs"], expected_pairs, strict=True):
                    _pair(
                        pair_row, pair, requirements.get(pair, 0.0), policy, configured=configured
                    )
                _aggregate(
                    row,
                    row["pairs"],
                    complete=not row["diagnostics"] and not blocked,
                    replay=replay,
                    blocked=blocked,
                    configured=configured,
                )
        _aggregate(
            report,
            report["poses"],
            complete=bool(report["poses"]),
            replay=action == "assembly_replay",
            blocked=not report["poses"],
            configured=configured,
        )
        _contact_acceptance(report)
        _require(response["ok"] == report["complete"], "success flag contradicts completeness")
        return AssemblyResponse(response, request)
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise bridge.BridgeError(f"Malformed assembly response: {exc}") from exc


def build_request(
    assembly,
    action="assembly_replay",
    *,
    coordinates=None,
    requirements=None,
    policy=None,
    samples=None,
    preset_id=None,
    result_version=1,
):
    """Build detached finite JSON shared by synchronous and cancellable transport."""
    result_version = _result_version(result_version)
    if type(action) is not str or action not in ACTIONS:
        raise bridge.BridgeError("Select an explicit supported assembly action.")
    request = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": ASSEMBLY_PROTOCOL_VERSION,
        "assembly": assembly,
        "action": action,
        "coordinates": coordinates,
        "requirements": requirements,
        "policy": policy,
        "samples": samples,
        "preset_id": preset_id,
        **({"result_version": result_version} if result_version in (2, 3) else {}),
    }
    try:
        # Bound expanded JSON size/work before traversing or copying a Python
        # container graph. The sync and async transports share this exact guard.
        request = sidecar_job.snapshot_request(request)
        _finite_tree(request)
        if result_version == 3:
            for source in request["assembly"]["part_sources"]:
                part_snapshot_bridge._expected_document(source["document"])
        if result_version == 1 and _uses_sketch_v2(request["assembly"]):
            raise bridge.BridgeError(_RESULT_VERSION_HELP)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise bridge.BridgeError(f"Assembly request requires finite JSON: {exc}") from exc
    return request


def accept_response(request, response):
    """Accept a response only against the exact detached raw request sent."""
    if type(response) is dict and response.get("result") is None and response.get("ok") is False:
        error = response.get("error")
        if (
            type(error) is dict
            and type(error.get("code")) is str
            and type(error.get("message")) is str
        ):
            message = f"{error['code']}: {error['message']}"
            version = request.get("result_version")
            if version in (2, 3) and (
                type(response.get("result_version")) is not int
                or response["result_version"] != version
            ):
                message = _result_version_help(version) + " " + message
            raise bridge.BridgeError(message)
    return validate_response(request, response)


def assembly_action(
    assembly,
    action="assembly_replay",
    *,
    coordinates=None,
    requirements=None,
    policy=None,
    samples=None,
    preset_id=None,
    result_version=1,
    project_root="",
    python_executable="",
    timeout=60.0,
):
    """Freshly replay/check/sample canonical JSON; never use cached native shapes."""
    request = build_request(
        assembly,
        action,
        coordinates=coordinates,
        requirements=requirements,
        policy=policy,
        samples=samples,
        preset_id=preset_id,
        result_version=result_version,
    )
    response = bridge._exchange_raw(
        request, project_root=project_root, python_executable=python_executable, timeout=timeout
    )
    return accept_response(request, response)
