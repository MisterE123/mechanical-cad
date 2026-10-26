"""Read-only evidence that retained old sidecars reject the proposed extension.

This is not an implementation of capability negotiation or a native CAD test.
Each source root is loaded in its own process with bytecode writes disabled.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

CHILD = r"""
import json
import sys

from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.errors import CADException
from mechanical_cad.model import Document
from mechanical_cad.sidecar import process_request

calls = []

def forbidden(*args, **kwargs):
    calls.append("model_parse")
    raise AssertionError("Operation model parsing was reached")

Document.from_dict = forbidden
AssemblyDocument.from_dict = forbidden
contract = {
    "version": 1,
    "request_id": "0" * 32,
    "required_capabilities": [
        "mcad.backend-contract/1", "mcad.solver-dof-cycle-guard/1"
    ],
}
requests = []
for action in ("replay", "canonical_snapshot", "check_geometry", "export_step", "export_stl"):
    requirements = dict(contract)
    if action == "canonical_snapshot":
        requirements["required_capabilities"] = ["mcad.backend-contract/1"]
    requests.append({
        "protocol_version": 1, "action": action,
        "document": None, "backend_contract": requirements,
    })
requests.append({
    "protocol_version": 1, "action": "solve_sketch", "result_version": 2,
    "document": None, "feature_id": "profile", "backend_contract": contract,
})
for action in ("assembly_replay", "assembly_check", "assembly_sample"):
    requests.append({
        "protocol_version": 1, "kind": "assembly", "assembly_protocol_version": 1,
        "assembly": None, "action": action, "backend_contract": contract,
    })
rows = []
for request in requests:
    try:
        response = process_request(request)
    except CADException as error:
        response = {"ok": False, "error": error.to_dict()}
    rows.append({
        "action": request["action"], "ok": response["ok"],
        "error": response.get("error"),
    })
assert not calls, calls
assert all(row["ok"] is False and row["error"]["code"] == "invalid_request" for row in rows)
assert not any(name == "slvs" or name == "OCP" or name.startswith("OCP.") for name in sys.modules)
print(json.dumps({"rows": rows, "model_parse_calls": calls, "native_modules_loaded": False}))
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-source", type=Path, required=True)
    parser.add_argument("--hotfix-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = {}
    for label, supplied_root in (("0.5", arguments.old_source), ("0.5.1", arguments.hotfix_source)):
        root = supplied_root.resolve(strict=True)
        environment = {
            **os.environ,
            "PYTHONPATH": str(root / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
        environment.pop("PYTHONHOME", None)
        process = subprocess.run(
            [sys.executable, "-c", CHILD],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        result[label] = {"root": str(root), **json.loads(process.stdout)}
    arguments.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("LEGACY_CAPABILITY_REJECTION_OK: 18 cases, no model parsing or native imports")


if __name__ == "__main__":
    main()
