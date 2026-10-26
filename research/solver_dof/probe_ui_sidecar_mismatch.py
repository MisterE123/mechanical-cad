"""Prove a new add-on bridge does not detect an old, unguarded sidecar.

This is an intentionally failing capability pairing, not an acceptance test.
SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from probe_dof_regression import ROOT, source_identity
from probe_native_dof import runtime_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-source", type=Path, required=True)
    parser.add_argument("--old-revision", default="1a27e74")
    parser.add_argument("--addon-source", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    old_source, addon_source = args.old_source.resolve(), args.addon_source.resolve()
    identity = source_identity(old_source, args.old_revision)
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("probe_dof_regression.py")),
            "--source",
            str(old_source),
            "--addon-source",
            str(addon_source),
            "--ui-witness",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    witness = json.loads(result.stdout)
    after = witness["after_cycle"]
    checks = {
        "old_source_matches_release": identity["source_tree_matches_reference"],
        "separate_addon_and_sidecar_roots": old_source != addon_source,
        "restored_without_current_solution": witness["resume_starts_without_current_solution"],
        "unique_third_line_pick": witness["pick"]["status"] == "unique",
        "old_core_false_dof": after["response"]["result"]["sketch"]["remaining_dof"] == 3,
        "new_bridge_accepts_old_false_dof": after["bridge_accepted"] is True,
        "false_solve_becomes_current": witness["current_solution_after"] is True,
    }
    evidence = {
        "scope": "UI data-path witness only; no Blender GUI or installed ZIP claim",
        "limitation": "The add-on bridge does not negotiate the cyclic-equality guard capability; an old sidecar remains unsafe even with the new add-on",
        "runtime": runtime_identity(),
        "old_source": identity,
        "addon_source": source_identity(addon_source),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "witness": witness,
        "checks": checks,
        "known_mismatch_reproduced": all(checks.values()),
    }
    args.output.write_text(json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False) + "\n")
    print("known_mismatch_reproduced=", evidence["known_mismatch_reproduced"])
    if not evidence["known_mismatch_reproduced"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
