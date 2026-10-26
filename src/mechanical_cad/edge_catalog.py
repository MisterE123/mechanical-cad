"""Opt-in transient native edge display; never a persistent edge naming scheme."""

from .errors import CADException
from .model import Document
from .sketch_protocol import validate_request_budget

BACKEND_CAPABILITIES = frozenset({"mcad.edge-catalog/1", "mcad.solid-arc-projection/1"})


def process_edge_catalog(request):
    fingerprint = validate_request_budget(request)
    if set(request) != {"protocol_version", "result_version", "action", "document", "options"}:
        raise CADException("invalid_request", "Edge catalog requires its exact explicit fields.")
    if (
        type(request["protocol_version"]) is not int
        or request["protocol_version"] != 1
        or request["action"] != "edge_catalog"
    ):
        raise CADException("invalid_request", "Unsupported edge catalog envelope.")
    version = request["result_version"]
    if type(version) is not int or version not in (2, 3):
        raise CADException("unsupported_result_version", "Edge catalog requires typed replay.")
    options = request["options"]
    if (type(options) is not dict or set(options) - {"projection_arcs"} != {"linear_deflection"}
            or ("projection_arcs" in options and type(options["projection_arcs"]) is not bool)):
        raise CADException("invalid_request", "Edge catalog requires explicit deflection.")
    document = Document.from_dict(request["document"])
    from .engine import regenerate
    from .kernel_ocp import OCPKernel

    kernel = OCPKernel()
    replay = regenerate(
        document, kernel, linear_deflection=options["linear_deflection"], result_version=version
    )
    if not replay.ok:
        raise CADException("invalid_geometry", "Rebuild the complete Part before picking an edge.")
    catalogs = {}
    for feature in replay.result["features"]:
        if (feature.get("output") or {}).get("kind") == "solid":
            catalogs[feature["id"]] = kernel.edge_display_catalog(
                replay.shapes[feature["id"]], options["linear_deflection"],
                projection_arcs=options.get("projection_arcs", False)
            )
    return {
        "protocol_version": 1,
        "result_version": version,
        "action": "edge_catalog",
        "input_fingerprint": fingerprint,
        "ok": True,
        "error": None,
        "result": {"replay": replay.result, "catalogs": catalogs},
    }
