"""One solver-evidence contract shared by full replay and solve-only authoring."""

from __future__ import annotations

from collections.abc import Mapping

from .sketch_model import SketchDefinition, resolve_sketch
from .sketch_solver import SolveReport, solve


def evaluate_sketch(
    definition: SketchDefinition, values: Mapping[str, float]
) -> tuple[SolveReport, dict]:
    """Return detached native evidence without creating any CAD-kernel geometry."""
    numeric = resolve_sketch(definition, values)
    report = solve(numeric)
    return report, {
        "solver": "libslvs",
        "solver_version": "3.2",
        "status": report.status.name.lower(),
        "remaining_dof": report.remaining_dof,
        "failed_constraints": list(report.failed_constraints),
        "redundant_constraints": list(report.redundant_constraints),
        "max_residual_mm": report.max_residual,
        "solved": report.sketch.to_dict() if report.success else None,
        "dimensions": {
            c.id: c.value for c in numeric.constraints if c.kind in {"distance", "radius", "angle"}
        },
    }
