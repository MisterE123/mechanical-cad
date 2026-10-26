"""Bounded native-free timing of the nine two-selection palette relation probes.

Usage: python tests/profile_constraint_palette.py SNAPSHOT_JSON CANONICAL_JSON
Uses a real saved journal and real prepare/codec; runtime pointers are host
stand-ins, with no guarded solution. This is not an end-to-end GUI benchmark.
"""

import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "unit"))
import test_constraint_probe_authority as host  # noqa: E402

ACTIONS = (
    "coincident",
    "parallel",
    "perpendicular",
    "equal",
    "tangent",
    "point_on_line",
    "midpoint",
    "concentric",
    "circle_line_tangent",
)
raw = Path(sys.argv[1]).read_text()
base = Path(sys.argv[2]).read_text()
draft = host.codec.restore(raw, base)
owner, context = host.host(draft)


def before():
    values = []
    for action in ACTIONS:
        try:
            values.append(host.actions.prepare(owner, action).state in {"eligible", "existing"})
        except (ValueError, TypeError, KeyError, AttributeError, ReferenceError):
            values.append(False)
    return values


def after():
    return [
        host.actions.constraint_selection.applicability_hint(
            owner.commands.sketch,
            owner.draft.selection,
            action,
            has_solution=False,
            has_retained_evidence=False,
        )
        for action in ACTIONS
    ]


result = {
    "snapshot_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    "snapshot_bytes": len(raw.encode()),
    "selection": draft.selection,
    "scope": "Nine relation probes; real restored four-corner draft, native-free host",
}
assert before() == after()
for label, operation in [("before", before), ("after", after)]:
    elapsed = []
    for _ in range(7):
        start = time.perf_counter()
        values = operation()
        elapsed.append(time.perf_counter() - start)
    result[label] = {
        "seconds": elapsed,
        "median_seconds": statistics.median(elapsed),
        "available": values,
    }
print(json.dumps(result, indent=2))
