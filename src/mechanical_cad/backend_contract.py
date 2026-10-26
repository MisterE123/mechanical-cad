"""Pure per-operation admission for the optional backend capability boundary.

This module never imports a native adapter. The legacy path imports only the
pure solver guard owner; exact result-3 solve/replay also checks the accepted
pure service marker owners. Imports follow bounded request policy. Capabilities
describe implementations, not dependency availability, versions, or authentication.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import FunctionType

from .errors import CADException

CONTRACT_CAPABILITY = "mcad.backend-contract/1"
SOLVER_CAPABILITY = "mcad.solver-dof-cycle-guard/1"
MAX_OPERATION_BYTES = 2 * 1024 * 1024
MAX_CONTRACT_BYTES = 4 * 1024
MAX_GUARDED_BYTES = MAX_OPERATION_BYTES + MAX_CONTRACT_BYTES
MAX_CONTRACT_NODES = 36
MAX_OPERATION_NODES = 1_000_000
MAX_RECEIPT_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
ACTIONS = frozenset(
    {
        "replay",
        "edge_catalog",
        "canonical_snapshot",
        "solve_sketch",
        "check_geometry",
        "export_step",
        "export_stl",
        "assembly_replay",
        "assembly_check",
        "assembly_sample",
        "assembly_export_step",
    }
)
_NAME = re.compile(r"[a-z0-9][a-z0-9._/-]{0,95}\Z", re.ASCII)
_NONCE = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)


def _invalid(message):
    raise CADException("backend_contract_invalid", message)


def snapshot_json(value, *, max_bytes, max_nodes, max_depth):
    """Detach exact finite JSON with default-JSON byte and expanded-node limits.

    Keys cost bytes, not nodes. Memoized sizes still charge each occurrence of a
    shared container; cycles and exponentially expanded DAGs fail before dumps.
    Depth counts the root as zero and includes scalar values, as existing input
    guards do. This accounting deliberately differs from compact fingerprints.
    """
    memo, active = {}, set()

    def check(size, nodes):
        if size > max_bytes or nodes > max_nodes:
            raise CADException("document_too_large", "JSON exceeds its byte or node budget.")

    def string_size(item):
        check(len(item) + 2, 1)
        size = 2
        for char in item:
            code = ord(char)
            if char in '\\"\b\f\n\r\t':
                size += 2
            elif 0x20 <= code <= 0x7E:
                size += 1
            else:
                size += 6 if code <= 0xFFFF else 12
            check(size, 1)
        return size

    def visit(item, depth):
        if depth > max_depth:
            raise CADException("invalid_json", "JSON nesting exceeds its limit.")
        kind = type(item)
        if kind not in (dict, list):
            if kind is str:
                size = string_size(item)
            elif kind is int:
                if item.bit_length() > 16_384:
                    raise CADException("invalid_json", "Integer exceeds JSON numeric limit.")
                size = len(str(item))
            elif kind is float and math.isfinite(item):
                size = len(repr(item))
            elif kind in (bool, type(None)):
                size = 5 if item is False else 4
            else:
                raise CADException("invalid_json", "Input must contain only finite JSON data.")
            check(size, 1)
            return item, size, 1, 0
        identity = id(item)
        if identity in active:
            raise CADException("invalid_json", "Input contains cyclic JSON containers.")
        if identity in memo:
            result = memo[identity]
            if depth + result[3] > max_depth:
                raise CADException("invalid_json", "JSON nesting exceeds its limit.")
            return result
        minimum_bytes = 2 + max(0, len(item) - 1) * 2 + len(item) * (5 if kind is dict else 1)
        check(minimum_bytes, len(item) + 1)
        active.add(identity)
        copied = {} if kind is dict else []
        size, nodes, height = 2, 1, 0
        try:
            entries = item.items() if kind is dict else enumerate(item)
            for index, (key, child) in enumerate(entries):
                size += 2 * bool(index)
                if kind is dict:
                    if type(key) is not str:
                        raise CADException("invalid_json", "JSON object keys must be strings.")
                    size += string_size(key) + 2
                child_copy, child_size, child_nodes, child_height = visit(child, depth + 1)
                size += child_size
                nodes += child_nodes
                height = max(height, child_height + 1)
                check(size, nodes)
                if kind is dict:
                    copied[key] = child_copy
                else:
                    copied.append(child_copy)
        finally:
            active.remove(identity)
        memo[identity] = copied, size, nodes, height
        return memo[identity]

    try:
        return visit(value, 0)[0]
    except CADException:
        raise
    except (ValueError, TypeError, OverflowError, RecursionError, RuntimeError) as exc:
        raise CADException("invalid_json", "Input cannot be encoded as finite JSON.") from exc


def fingerprint(value):
    """Hash an already bounded exact JSON tree, without filling any defaults."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_contract(value):
    if type(value) is not dict or set(value) != {"version", "request_id", "required_capabilities"}:
        _invalid("Backend contract requires exactly version, request_id and capabilities.")
    if type(value["version"]) is not int or value["version"] != 1:
        _invalid("Only backend contract version 1 is supported.")
    if type(value["request_id"]) is not str or not _NONCE.fullmatch(value["request_id"]):
        _invalid("Backend request_id must be 32 lowercase hexadecimal characters.")
    names = value["required_capabilities"]
    if (
        type(names) is not list
        or not 1 <= len(names) <= 32
        or any(type(name) is not str or not _NAME.fullmatch(name) for name in names)
        or names != sorted(set(names))
    ):
        _invalid("Capabilities must be sorted, unique, bounded lowercase ASCII names.")


def _reject_nested_contract(value):
    pending, seen = [value], set()
    while pending:
        item = pending.pop()
        if type(item) not in (dict, list) or id(item) in seen:
            continue
        seen.add(id(item))
        if type(item) is dict:
            if "backend_contract" in item:
                _invalid("Backend contracts belong only on the operation envelope.")
            pending.extend(item.values())
        else:
            pending.extend(item)


def _has_arc_projection(operation):
    options = operation.get("options")
    if type(options) is dict and options.get("projection_arcs") is True:
        return True
    documents = [operation.get("document")]
    assembly = operation.get("assembly")
    if type(assembly) is dict and type(assembly.get("part_sources")) is list:
        documents.extend(source.get("document") for source in assembly["part_sources"]
                         if type(source) is dict)
    return any(type(row) is dict and row.get("kind") == "arc"
               for document in documents if type(document) is dict
               and type(document.get("features")) is list
               for feature in document["features"] if type(feature) is dict
               and type(feature.get("projections")) is list
               for row in feature["projections"])


def minimum_capabilities(operation):
    """Derive requirements from a bounded O, independently of client policy."""
    _reject_nested_contract(operation)
    action = operation.get("action", "replay")
    if type(action) is not str or action not in ACTIONS:
        _invalid("Guarded requests require a supported action.")
    if action.startswith("assembly_"):
        if operation.get("kind") != "assembly":
            _invalid("Guarded assembly actions require the assembly envelope.")
    elif "kind" in operation:
        _invalid("Only guarded assembly actions accept an envelope kind.")
    snapshot = action == "canonical_snapshot"
    minimum = {CONTRACT_CAPABILITY}
    if action == "edge_catalog":
        minimum.add("mcad.edge-catalog/1")
    if _has_arc_projection(operation):
        minimum.add("mcad.solid-arc-projection/1")
    if action == "assembly_export_step":
        minimum.add("mcad.assembly-step-export/1")
    if snapshot:
        if "result_version" in operation:
            _invalid("Canonical snapshots have no result-version argument.")
    else:
        minimum.add(SOLVER_CAPABILITY)
        if type(operation.get("result_version")) is not int or operation["result_version"] not in (
            2,
            3,
        ):
            _invalid("Guarded solving requests require explicit result version 2 or 3.")

    documents = [operation.get("document")]
    assembly = operation.get("assembly")
    if type(assembly) is dict and "assembly_schema_version" in assembly:
        if (
            type(assembly["assembly_schema_version"]) is not int
            or assembly["assembly_schema_version"] != 1
        ):
            _invalid("Unsupported assembly schema in guarded request.")
    if type(assembly) is dict and type(assembly.get("part_sources")) is list:
        documents.extend(
            source.get("document") for source in assembly["part_sources"] if type(source) is dict
        )
    schema_three = False
    for document in documents:
        if type(document) is dict and "schema_version" in document:
            if type(document["schema_version"]) is not int or document["schema_version"] not in (
                1,
                2,
            ):
                _invalid("Unsupported Part document schema in guarded request.")
        if type(document) is not dict or type(document.get("features")) is not list:
            continue  # Malformed operation data belongs to its ordinary validator.
        for feature in document["features"]:
            sketch = feature.get("sketch") if type(feature) is dict else None
            if type(sketch) is dict and "schema_version" in sketch:
                version = sketch["schema_version"]
                if type(version) is not int or version not in (1, 2, 3):
                    _invalid("Unsupported embedded sketch schema in guarded request.")
                schema_three |= version == 3
    if snapshot:
        if schema_three:
            minimum.add("mcad.snapshot-sketch3/1")
    elif schema_three or operation["result_version"] == 3:
        if operation["result_version"] != 3:
            _invalid("Sketch schema 3 requires explicit result version 3.")
        minimum.add("mcad.sketch-arcs/1")
        if action == "solve_sketch":
            minimum.add("mcad.solve-result/3")
        else:
            minimum.add("mcad.part-result/3")
            if action in {"check_geometry", "export_step", "export_stl"}:
                minimum.add("mcad.geometry-result/3")
            elif action.startswith("assembly_"):
                minimum.add("mcad.assembly-result/3")
    return frozenset(minimum)


@dataclass(frozen=True)
class PreparedRequest:
    operation: dict
    contract: dict
    request_fingerprint: str


def prepare_request(request):
    """Bound O and C independently before policy scans or implementation imports."""
    if type(request) is not dict or "backend_contract" not in request:
        _invalid("A guarded request must contain backend_contract.")
    # Bound the projected root before allocating it. Even an empty quoted key,
    # a one-byte scalar and default separators cost seven bytes per entry.
    entries = len(request) - 1
    if entries * 7 > MAX_OPERATION_BYTES or entries + 1 > MAX_OPERATION_NODES:
        raise CADException("document_too_large", "Operation exceeds its byte or node budget.")
    operation = snapshot_json(
        {key: value for key, value in request.items() if key != "backend_contract"},
        max_bytes=MAX_OPERATION_BYTES,
        max_nodes=MAX_OPERATION_NODES,
        max_depth=64,
    )
    # Preserve the existing compact Part/solve/snapshot budget independently.
    # Assembly retains its own model and service budgets in ordinary dispatch.
    if "kind" not in operation:
        from .part_snapshot import input_fingerprint

        input_fingerprint(operation)
    try:
        contract = snapshot_json(
            request["backend_contract"],
            max_bytes=MAX_CONTRACT_BYTES,
            max_nodes=MAX_CONTRACT_NODES,
            max_depth=2,
        )
        _validate_contract(contract)
        snapshot_json(
            {"backend_contract": contract},
            max_bytes=MAX_CONTRACT_BYTES,
            max_nodes=MAX_CONTRACT_NODES + 1,
            max_depth=3,
        )
    except CADException as exc:
        _invalid(str(exc))
    minimum = minimum_capabilities(operation)
    if not minimum.issubset(contract["required_capabilities"]):
        _invalid("Supplied capabilities omit the action's minimum requirements.")
    guarded = {**operation, "backend_contract": contract}
    return PreparedRequest(operation, contract, fingerprint(guarded))


def _path(value, *, resolve=True):
    if type(value) is not str or not value or "\0" in value or len(value) > 4096:
        raise CADException("backend_identity_mismatch", "Backend identity path is unavailable.")
    if not os.path.isabs(value):
        raise CADException("backend_identity_mismatch", "Backend identity must be absolute.")
    result = str(Path(value).resolve(strict=True)) if resolve else os.path.abspath(value)
    if len(result) > 4096:
        raise CADException("backend_identity_mismatch", "Backend identity path is too long.")
    return result


def _observe_geometry_v3(core):
    """Observe actual geometry implementations and companions without admission.

    A marker on an importing/re-exporting module cannot
    relabel an older implementation, and geometry is never confirmed in isolation.
    """
    supported, modules, mismatch = set(), {}, False
    companions = (
        ("sketch_solver", SOLVER_CAPABILITY),
        ("profile_adapter_v3", "mcad.sketch-arcs/1"),
        ("sketch_protocol_v3", "mcad.part-result/3"),
    )
    geometry = "mcad.geometry-result/3"
    for name, capability in (
        *companions,
        ("actions", geometry),
        ("geometry_protocol_v3", geometry),
    ):
        try:
            module = importlib.import_module(f".{name}", __package__)
            origin = Path(_path(getattr(module, "__file__", None)))
        except Exception:
            continue
        if origin != core / f"{name}.py":
            mismatch = True
            continue
        marker = getattr(module, "BACKEND_CAPABILITIES", None)
        if type(marker) is frozenset and capability in marker:
            modules[name] = module
            if capability != geometry:
                supported.add(capability)
    if len(modules) != len(companions) + 2:
        return frozenset(supported), mismatch
    actions, protocol = modules["actions"], modules["geometry_protocol_v3"]
    entrypoints = (
        (actions, "run_geometry_action"),
        (protocol, "process_geometry_request_v3"),
    )
    for module, name in entrypoints:
        function = getattr(module, name, None)
        if (
            type(function) is not FunctionType
            or function.__module__ != module.__name__
            or function.__globals__ is not vars(module)
        ):
            return frozenset(supported), mismatch
        try:
            origin = Path(_path(function.__code__.co_filename))
        except Exception:
            return frozenset(supported), mismatch
        if origin != Path(module.__file__).resolve():
            return frozenset(supported), True
    if protocol.run_geometry_action is not actions.run_geometry_action:
        return frozenset(supported), mismatch
    supported.add(geometry)
    return frozenset(supported), mismatch


def _observe_owned_module(core, name, capability, entrypoints):
    """Observe new snapshot/Assembly owners, never a re-exported implementation."""
    try:
        module = importlib.import_module(f".{name}", __package__)
        origin = Path(_path(getattr(module, "__file__", None)))
    except Exception:
        return None, False
    if origin != core / f"{name}.py":
        return None, True
    marker = getattr(module, "BACKEND_CAPABILITIES", None)
    if capability is not None and not (type(marker) is frozenset and capability in marker):
        return None, False
    for name in entrypoints:
        function = getattr(module, name, None)
        if (
            type(function) is not FunctionType
            or function.__module__ != module.__name__
            or function.__globals__ is not vars(module)
        ):
            return None, False
        try:
            function_origin = Path(_path(function.__code__.co_filename))
        except Exception:
            return None, False
        if function_origin != origin:
            return None, True
    return module, False


def _observe_snapshot_v3(core):
    # No solver, replay, profile classifier or native import belongs to capture.
    return _observe_owned_module(
        core,
        "part_snapshot",
        "mcad.snapshot-sketch3/1",
        ("canonical_snapshot", "validate_snapshot_source"),
    )


def _observe_assembly_v3(core):
    """Require both actual Assembly owners and their actual replay companions."""
    supported, modules, mismatch = set(), {}, False
    owners = (
        ("sketch_solver", SOLVER_CAPABILITY, ()),
        ("profile_adapter_v3", "mcad.sketch-arcs/1", ("sketch_output_v3",)),
        ("sketch_protocol_v3", "mcad.part-result/3", ("process_replay_request_v3",)),
        ("part_snapshot", "mcad.snapshot-sketch3/1", ("validate_snapshot_source",)),
        ("engine", None, ("regenerate",)),
        (
            "assembly_service",
            "mcad.assembly-result/3",
            ("run_assembly_action", "_run_assembly_action_with_native", "_build_parts"),
        ),
        ("assembly_protocol", "mcad.assembly-result/3", ("process_assembly_request",)),
    )
    for name, capability, entrypoints in owners:
        module, foreign = _observe_owned_module(core, name, capability, entrypoints)
        mismatch |= foreign
        if module is not None:
            modules[name] = module
            if capability is not None and capability != "mcad.assembly-result/3":
                supported.add(capability)
    if len(modules) == len(owners):
        service, protocol = modules["assembly_service"], modules["assembly_protocol"]
        if (
            protocol.run_assembly_action is service.run_assembly_action
            and service.regenerate is modules["engine"].regenerate
            and service.validate_snapshot_source
            is modules["part_snapshot"].validate_snapshot_source
        ):
            supported.add("mcad.assembly-result/3")
    return frozenset(supported), mismatch


def _observe_assembly_step_export(core):
    """Observe pure export, protocol and same-run check owners, never native code."""
    capability = "mcad.assembly-step-export/1"
    modules, mismatch = {}, False
    owners = (
        ("engine", None, ("regenerate",)),
        ("part_snapshot", None, ("validate_snapshot_source",)),
        (
            "assembly_service",
            capability,
            ("run_assembly_action", "_run_assembly_action_with_native", "_build_parts"),
        ),
        ("assembly_export", capability, ("run_assembly_step_export",)),
        ("assembly_protocol", capability, ("process_assembly_request",)),
    )
    for name, marker, entrypoints in owners:
        module, foreign = _observe_owned_module(core, name, marker, entrypoints)
        mismatch |= foreign
        if module is not None:
            modules[name] = module
    if len(modules) != len(owners):
        return frozenset(), mismatch
    service, export, protocol = (
        modules["assembly_service"],
        modules["assembly_export"],
        modules["assembly_protocol"],
    )
    linked = (
        getattr(protocol, "run_assembly_step_export", None) is export.run_assembly_step_export
        and getattr(protocol, "run_assembly_action", None) is service.run_assembly_action
        and getattr(export, "_run_assembly_action_with_native", None)
        is service._run_assembly_action_with_native
        and getattr(service, "regenerate", None) is modules["engine"].regenerate
        and getattr(service, "validate_snapshot_source", None)
        is modules["part_snapshot"].validate_snapshot_source
    )
    return (frozenset({capability}) if linked else frozenset()), mismatch


def observe_backend(operation):
    """Capture actual imports and interpreter before ordinary dispatch.

    Missing adapters are representable, with a null origin, as an unsupported
    guard capability. A copied older adapter never acquires this module's marker.
    """
    package = sys.modules[__package__]
    try:
        core = Path(_path(package.__file__)).parent
        root = Path(_path(os.getcwd()))
        version = package.__version__
        if type(version) is not str or not 1 <= len(version) <= 64:
            raise CADException("backend_identity_mismatch", "Core version is unavailable.")
        identity = {
            "core_version": version,
            "project_root": str(root),
            "core_origin": str(core),
            "solver_origin": None,
            "python_executable": _path(sys.executable, resolve=False),
            "python_executable_target": _path(sys.executable),
            "python_prefix": _path(sys.prefix),
            "python_base_prefix": _path(sys.base_prefix),
            "python_version": list(sys.version_info[:3]),
        }
    except (AttributeError, OSError, RuntimeError) as exc:
        raise CADException("backend_identity_mismatch", "Cannot resolve backend identity.") from exc
    supported = {CONTRACT_CAPABILITY}
    try:
        expected_core = (root / "src" / "mechanical_cad").resolve(strict=True)
    except (OSError, RuntimeError):
        mismatch = True
    else:
        mismatch = core != expected_core
    if operation.get(
        "action"
    ) == "canonical_snapshot" and "mcad.snapshot-sketch3/1" in minimum_capabilities(operation):
        snapshot, snapshot_mismatch = _observe_snapshot_v3(core)
        mismatch |= snapshot_mismatch
        if snapshot is not None:
            supported.add("mcad.snapshot-sketch3/1")
    if operation.get("action", "replay") != "canonical_snapshot":
        try:
            solver = importlib.import_module(".sketch_solver", __package__)
            origin = Path(_path(getattr(solver, "__file__", None)))
        except Exception:
            solver = None
        else:
            identity["solver_origin"] = str(origin)
            mismatch |= not origin.is_relative_to(core)
            marker = getattr(solver, "BACKEND_CAPABILITIES", None)
            if type(marker) is frozenset and SOLVER_CAPABILITY in marker:
                supported.add(SOLVER_CAPABILITY)
    if (
        type(operation.get("result_version")) is int
        and operation["result_version"] == 3
        and operation.get("action", "replay") in {"solve_sketch", "replay", "edge_catalog"}
    ):
        for name, capability in (
            ("profile_adapter_v3", "mcad.sketch-arcs/1"),
            ("sketch_service_v3", "mcad.solve-result/3"),
            ("sketch_protocol_v3", "mcad.part-result/3"),
        ):
            try:
                module = importlib.import_module(f".{name}", __package__)
                origin = Path(_path(getattr(module, "__file__", None)))
            except Exception:
                continue
            if origin != core / f"{name}.py":
                mismatch = True
                continue
            marker = getattr(module, "BACKEND_CAPABILITIES", None)
            if type(marker) is frozenset and capability in marker:
                supported.add(capability)
    if (
        type(operation.get("result_version")) is int
        and operation["result_version"] == 3
        and operation.get("action") in {"check_geometry", "export_step", "export_stl"}
    ):
        geometry_supported, geometry_mismatch = _observe_geometry_v3(core)
        supported.update(geometry_supported)
        mismatch |= geometry_mismatch
    if (
        type(operation.get("result_version")) is int
        and operation["result_version"] == 3
        and operation.get("action")
        in {"assembly_replay", "assembly_check", "assembly_sample", "assembly_export_step"}
    ):
        assembly_supported, assembly_mismatch = _observe_assembly_v3(core)
        supported.update(assembly_supported)
        mismatch |= assembly_mismatch
    if operation.get("action") == "assembly_export_step":
        export_supported, export_mismatch = _observe_assembly_step_export(core)
        supported.update(export_supported)
        mismatch |= export_mismatch
    if operation.get("action") == "edge_catalog":
        module, foreign = _observe_owned_module(
            core, "edge_catalog", "mcad.edge-catalog/1", ("process_edge_catalog",)
        )
        mismatch |= foreign
        if module is not None:
            supported.add("mcad.edge-catalog/1")
    if "mcad.solid-arc-projection/1" in minimum_capabilities(operation):
        module, foreign = _observe_owned_module(
            core, "edge_catalog", "mcad.solid-arc-projection/1", ("process_edge_catalog",)
        )
        mismatch |= foreign
        if module is not None:
            supported.add("mcad.solid-arc-projection/1")
    return identity, frozenset(supported), mismatch


def make_receipt(prepared, identity, supported, *, dispatched):
    required = prepared.contract["required_capabilities"]
    receipt = {
        "version": 1,
        "request_id": prepared.contract["request_id"],
        "request_fingerprint": prepared.request_fingerprint,
        "required_capabilities": list(required),
        "confirmed_capabilities": [name for name in required if name in supported],
        "missing_capabilities": [name for name in required if name not in supported],
        "phase": "dispatched" if dispatched else "rejected_before_dispatch",
        "backend": identity,
    }
    snapshot_json(
        {"backend_receipt": receipt},
        max_bytes=MAX_RECEIPT_BYTES,
        max_nodes=MAX_OPERATION_NODES,
        max_depth=64,
    )
    return receipt


def failure(exc, operation=None):
    """Match main() common failure, retaining exact explicit v2/v3 stamps."""
    error = (
        exc.to_dict()
        if isinstance(exc, CADException)
        else {"code": "sidecar_error", "message": f"{type(exc).__name__}: {exc}"}
    )
    response = {"protocol_version": 1, "ok": False, "result": None, "error": error}
    if operation is not None and type(operation.get("result_version")) is int:
        if operation["result_version"] in (2, 3):
            response["result_version"] = operation["result_version"]
    return response


def process_guarded_request(request, dispatch):
    """Admit once, call unchanged dispatch once, and attach same-process evidence."""
    try:
        prepared = prepare_request(request)
        identity, supported, mismatch = observe_backend(prepared.operation)
        missing = set(prepared.contract["required_capabilities"]) - supported
        dispatched = not mismatch and not missing
        receipt = make_receipt(prepared, identity, supported, dispatched=dispatched)
        if not dispatched:
            code = "backend_identity_mismatch" if mismatch else "backend_capability_missing"
            message = (
                "Imported backend does not match the launch project root."
                if mismatch
                else "Backend does not implement every requested capability."
            )
            return {**failure(CADException(code, message)), "backend_receipt": receipt}
    except CADException as exc:
        return failure(exc)
    try:
        response = dispatch(prepared.operation)
        # Mirror main's old stamping even for action services returning errors.
        if prepared.operation.get("result_version") == 2:
            response["result_version"] = 2
        elif (
            type(prepared.operation.get("result_version")) is int
            and prepared.operation["result_version"] == 3
        ):
            response["result_version"] = 3
        return snapshot_json(
            {**response, "backend_receipt": receipt},
            max_bytes=MAX_RESPONSE_BYTES,
            max_nodes=4_000_000,
            max_depth=32,
        )
    except Exception as exc:
        # Once admission has occurred, even a dispatcher/serialization defect
        # must retain the truthful phase rather than losing the receipt in main.
        return {**failure(exc, prepared.operation), "backend_receipt": receipt}
