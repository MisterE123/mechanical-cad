"""Explicit assembly protocol-v1 envelope, separate from legacy Part requests."""

from .assembly_export import ASSEMBLY_STEP_ACTION, run_assembly_step_export
from .assembly_model import AssemblyDocument
from .assembly_policy import fingerprint
from .assembly_service import ASSEMBLY_ACTIONS, run_assembly_action
from .errors import CADException

ASSEMBLY_PROTOCOL_VERSION = 1
BACKEND_CAPABILITIES = frozenset({"mcad.assembly-result/3", "mcad.assembly-step-export/1"})


def process_assembly_request(request):
    if (
        type(request) is dict
        and type(request.get("action")) is str
        and request["action"] == ASSEMBLY_STEP_ACTION
    ):
        return run_assembly_step_export(request)
    fields = {
        "protocol_version",
        "kind",
        "assembly_protocol_version",
        "assembly",
        "action",
        "coordinates",
        "requirements",
        "policy",
        "samples",
        "preset_id",
        "result_version",
    }
    if type(request) is not dict or set(request) - fields:
        raise CADException("invalid_request", "Unknown assembly request fields.")
    if (
        type(request.get("protocol_version")) is not int
        or request["protocol_version"] != 1
        or request.get("kind") != "assembly"
        or type(request.get("assembly_protocol_version")) is not int
        or request["assembly_protocol_version"] != ASSEMBLY_PROTOCOL_VERSION
    ):
        raise CADException("unsupported_protocol", "Only assembly protocol 1 is supported.")
    action = request.get("action")
    if type(action) is not str or action not in ASSEMBLY_ACTIONS:
        raise CADException("invalid_action", "Select an explicit supported assembly action.")
    assembly = AssemblyDocument.from_dict(request.get("assembly"))
    return {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": ASSEMBLY_PROTOCOL_VERSION,
        "input_fingerprint": fingerprint(request),
        **run_assembly_action(
            assembly,
            action,
            coordinates=request.get("coordinates"),
            requirements=request.get("requirements"),
            policy=request.get("policy"),
            samples=request.get("samples"),
            preset_id=request.get("preset_id"),
            result_version=request.get("result_version", 1),
        ),
    }
