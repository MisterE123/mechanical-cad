"""Check recorded research claims without rerunning native code or importing CAD.

A pass verifies reproduction/containment evidence only, not broad solver accuracy.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from probe_dof_regression import verify

HERE = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def read(name):
    return json.loads((HERE / name).read_text())


def script_matches(name, observed):
    require(
        hashlib.sha256((HERE / name).read_bytes()).hexdigest() == observed,
        f"Stale script identity: {name}",
    )


def main():
    native = read("native_dof_evidence.json")
    require(native["runtime"]["slvs_version"] == "3.2", "Wrong native version")
    script_matches("probe_native_dof.py", native["runtime"]["script_sha256"])
    require(len(native["cases"]) == 16, "Expected 16 direct native observations")
    for name, value in native["cases"].items():
        spec = value["input"]
        require(
            value["native"]["result"] == spec["expected_native_status"]
            and value["native"]["dof"] == spec["expected_native_dof"]
            and value["max_coordinate_residual"] == 0.0,
            name,
        )
    baseline = read("released_adapter_evidence.json")
    guarded = read("guarded_adapter_evidence.json")
    require(baseline["source"]["source_tree_matches_reference"], "Release source mismatch")
    require(baseline["source"]["compared_files"] == 623, "Incomplete release source match")
    for expectation, evidence in (("baseline", baseline), ("guarded", guarded)):
        script_matches("probe_dof_regression.py", evidence["script_sha256"])
        require(evidence["slvs_version"] == "3.2", "Wrong adapter solver version")
        require(len(evidence["cases"]) == 62, "Expected 62 adapter observations")
        checks = verify(evidence, expectation)
        require(all(checks.values()), f"{expectation}: failed checks: {checks}")
    require(set(baseline["cases"]) == set(guarded["cases"]), "Fixture matrix changed")
    for name in baseline["cases"]:
        old, new = baseline["cases"][name], guarded["cases"][name]
        require(old["fixture"] == new["fixture"], f"Authored fixture changed: {name}")
        if old["successful_wrong_dof"]:
            require(old["scalar_equality_cycles"], f"Uncontained known defect: {name}")
        if not old["scalar_equality_cycles"]:
            require(
                old["native"] == new["native"] and old["report"] == new["report"],
                f"Control observation changed: {name}",
            )
    require(read("ui_witness_release.json") == baseline["ui_witness"], "Stale UI extract")
    budget = read("equation_budget_evidence.json")
    script_matches("probe_equation_budget.py", budget["script_sha256"])
    require(
        budget["slvs_version"] == "3.2" and len(budget["cases"]) == 15,
        "Wrong budget matrix/version",
    )
    require(all(budget["checks"].values()), "Budget reproduction failed")
    for name in ("cap_plus_one_1025", "cap_plus_256_1280"):
        require(budget["cases"][name]["native_called"] is False, "Budget did not reject")
    require(
        budget["cases"]["cap_distinct_coincidence_cycles_1024"]["native"]["dof"] == 0,
        "Budget known defect not reproduced",
    )
    mismatch = read("old_sidecar_new_addon_witness.json")
    script_matches("probe_ui_sidecar_mismatch.py", mismatch["script_sha256"])
    require(all(mismatch["checks"].values()), "Old-sidecar mismatch not reproduced")
    require(
        mismatch["old_source"]["reference_revision"] == baseline["source"]["reference_revision"],
        "Mismatch baseline differs",
    )
    witness = mismatch["witness"]
    require(
        witness["after_cycle"]["bridge_accepted"] is True
        and witness["after_cycle"]["response"]["result"]["sketch"]["remaining_dof"] == 3,
        "Bridge mismatch witness differs",
    )
    require(
        witness["loaded_modules_sha256"] == guarded["ui_witness"]["loaded_modules_sha256"]
        or all(
            value == guarded["ui_witness"]["loaded_modules_sha256"].get(name)
            for name, value in witness["loaded_modules_sha256"].items()
            if name.startswith("dof_ui_witness.")
        ),
        "New add-on hashes differ",
    )
    print("Verified: 16 raw-native observations, 62 released + 62 guarded adapter observations,")
    print("15 historical budget cases, released UI path, and old-sidecar/new-add-on mismatch.")
    print("This verifies bounded recorded evidence; it is not general solver qualification.")


if __name__ == "__main__":
    main()
