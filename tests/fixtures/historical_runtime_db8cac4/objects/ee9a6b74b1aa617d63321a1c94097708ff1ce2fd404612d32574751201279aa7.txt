"""Pre-native coordinate-cycle rejection and unchanged strict draft boundaries."""

import copy
import importlib
import itertools
import sys
import types
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from mechanical_cad import sketch_solver
from mechanical_cad.model import Document, Feature
from mechanical_cad.part_snapshot import input_fingerprint
from mechanical_cad.sidecar import process_request
from mechanical_cad.sketch_model import (
    Constraint,
    Line,
    Point,
    Sketch,
    SketchDefinition,
    SketchError,
)
from mechanical_cad.sketch_service import solve_sketch

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_dof_cycle_boundary_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
solve_bridge = importlib.import_module(PACKAGE + ".sketch_action_bridge")
drafts = importlib.import_module(PACKAGE + ".general_sketch_draft")
store = importlib.import_module(PACKAGE + ".general_draft_store")
diagnostics = importlib.import_module(PACKAGE + ".constraint_diagnostics")

CODE = "solver_dof_indeterminate"


def triangle(kind="coincident", *, schema_version=2):
    points = (Point("a", 0, 0), Point("b", 2, 1), Point("c", 4, 0))
    pairs = (("a", "b"), ("b", "c"), ("c", "a"))
    lines = tuple(Line(f"l{i}", *pair) for i, pair in enumerate(pairs))
    constraints = tuple(
        Constraint(f"c{i}", kind, pair if kind == "coincident" else (f"l{i}",))
        for i, pair in enumerate(pairs)
    )
    return Sketch("cycle", points, lines, constraints, schema_version=schema_version)


def candidate(sketch=None):
    definition = SketchDefinition.from_dict((sketch or triangle()).to_dict())
    return Document(
        "part",
        "Coordinate cycle",
        {},
        (Feature("profile", "sketch_constrained", "Sketch", sketch=definition),),
        "profile",
        schema_version=2,
    )


def request(document=None):
    return {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 2,
        "document": (document or candidate()).to_dict(),
        "feature_id": "profile",
    }


@pytest.fixture
def no_backend(monkeypatch):
    calls = []

    def forbidden():
        calls.append(True)
        pytest.fail("A coordinate-cycle rejection must precede loading the native backend")

    monkeypatch.setattr(sketch_solver, "_load_backend", forbidden)
    return calls


@pytest.mark.parametrize("kind", ["coincident", "horizontal", "vertical"])
@pytest.mark.parametrize("schema_version", [1, 2])
@pytest.mark.parametrize("diagnose", [False, True])
def test_minimal_cycle_rejected_before_backend_without_rewriting_source(
    no_backend, kind, schema_version, diagnose
):
    source = triangle(kind, schema_version=schema_version)
    if kind == "coincident":
        source = replace(source, lines=())  # Three points and three relations suffice.
    before = source.to_json()
    with pytest.raises(SketchError) as caught:
        sketch_solver.solve(source, diagnose=diagnose)
    assert caught.value.code == CODE
    assert source.to_json() == before and not no_backend


@pytest.mark.parametrize("kind", ["horizontal", "vertical"])
@pytest.mark.parametrize("reverse_line", [False, True])
def test_different_line_ids_with_same_coordinate_equation_are_parallel_edges(
    no_backend, kind, reverse_line
):
    source = triangle(kind)
    second = Line("other", "b", "a") if reverse_line else Line("other", "a", "b")
    source = replace(
        source,
        points=source.points[:2],
        lines=(source.lines[0], second),
        constraints=(Constraint("first", kind, ("l0",)), Constraint("second", kind, ("other",))),
    )
    with pytest.raises(SketchError) as caught:
        sketch_solver.solve(source)
    assert caught.value.code == CODE and not no_backend


@pytest.mark.parametrize("kind", ["horizontal", "vertical"])
def test_coincidence_and_axis_relation_can_close_only_one_coordinate_cycle(no_backend, kind):
    source = triangle()
    source = replace(
        source,
        constraints=(
            source.constraints[0],
            Constraint("axis_bc", kind, ("l1",)),
            Constraint("axis_ca", kind, ("l2",)),
        ),
    )
    with pytest.raises(SketchError) as caught:
        sketch_solver.solve(source)
    assert caught.value.code == CODE


@pytest.mark.parametrize("fixed_count", [1, 2, 3])
def test_anchors_do_not_authorize_a_count_for_cyclic_active_equalities(no_backend, fixed_count):
    source = triangle()
    source = replace(
        source,
        constraints=source.constraints
        + tuple(
            Constraint(f"anchor{i}", "fixed", (point.id,), target=(0, 0))
            for i, point in enumerate(source.points[:fixed_count])
        ),
    )
    before = source.to_json()
    with pytest.raises(SketchError) as caught:
        sketch_solver.solve(source)
    assert caught.value.code == CODE and source.to_json() == before


@pytest.mark.parametrize("kind", ["coincident", "horizontal", "vertical"])
def test_point_line_relation_permutations_and_reversed_endpoints_keep_rejection(no_backend, kind):
    source = triangle(kind)
    for points in itertools.permutations(source.points):
        for constraints in itertools.permutations(source.constraints):
            for reversed_endpoints in (False, True):
                lines = tuple(reversed(source.lines))
                if reversed_endpoints:
                    lines = tuple(replace(line, start=line.end, end=line.start) for line in lines)
                    constraints = tuple(
                        replace(c, refs=tuple(reversed(c.refs))) for c in constraints
                    )
                changed = replace(source, points=points, lines=lines, constraints=constraints)
                before = changed.to_json()
                with pytest.raises(SketchError) as caught:
                    sketch_solver.solve(changed)
                assert caught.value.code == CODE and changed.to_json() == before


def _rank(rows):
    """Small exact test oracle; independent of the production graph algorithm."""
    matrix = [[Fraction(value) for value in row] for row in rows]
    rank = 0
    for column in range(6):
        pivot = next((i for i in range(rank, len(matrix)) if matrix[i][column]), None)
        if pivot is None:
            continue
        matrix[rank], matrix[pivot] = matrix[pivot], matrix[rank]
        scale = matrix[rank][column]
        matrix[rank] = [value / scale for value in matrix[rank]]
        for i in range(rank + 1, len(matrix)):
            scale = matrix[i][column]
            matrix[i] = [a - scale * b for a, b in zip(matrix[i], matrix[rank], strict=True)]
        rank += 1
    return rank


def test_all_three_point_equality_subsets_match_exact_independence_before_native(monkeypatch):
    class ReachedNative(Exception):
        pass

    def native_boundary():
        raise ReachedNative

    monkeypatch.setattr(sketch_solver, "_load_backend", native_boundary)
    source = triangle()
    relations = tuple(
        Constraint(
            f"{kind}_{i}", kind, (line.start, line.end) if kind == "coincident" else (line.id,)
        )
        for kind in ("coincident", "horizontal", "vertical")
        for i, line in enumerate(source.lines)
    )
    lines = {line.id: line for line in source.lines}
    indices = {point.id: i * 2 for i, point in enumerate(source.points)}
    for mask in range(1 << len(relations)):
        constraints = tuple(c for i, c in enumerate(relations) if mask & (1 << i))
        rows = []
        for relation in constraints:
            if relation.kind == "coincident":
                start, end = relation.refs
                axes = (0, 1)
            else:
                line = lines[relation.refs[0]]
                start, end = line.start, line.end
                axes = (1,) if relation.kind == "horizontal" else (0,)
            for axis in axes:
                row = [0] * 6
                row[indices[start] + axis], row[indices[end] + axis] = 1, -1
                rows.append(row)
        changed = replace(source, constraints=constraints)
        if len(rows) > _rank(rows):
            with pytest.raises(SketchError) as caught:
                sketch_solver.solve(changed)
            assert caught.value.code == CODE, mask
        else:
            with pytest.raises(ReachedNative):
                sketch_solver.solve(changed)


def test_maximum_point_and_constraint_budget_is_bounded_and_rejected_pre_native(no_backend):
    points = tuple(Point(f"p{i:03}", i, 0) for i in range(256))
    cycle = tuple(
        Constraint(f"c{i:03}", "coincident", (points[i].id, points[(i + 1) % 256].id))
        for i in range(256)
    )
    source = Sketch(
        "max_cycle",
        points,
        (),
        cycle
        + tuple(replace(c, id="duplicate_" + c.id, refs=tuple(reversed(c.refs))) for c in cycle),
        schema_version=2,
    )
    before = source.to_json()
    with pytest.raises(SketchError) as caught:
        sketch_solver.solve(source)
    assert caught.value.code == CODE and source.to_json() == before
    assert len(source.points) == 256 and len(source.constraints) == 512
    assert len(before.encode()) < 256 * 1024 and not no_backend


@pytest.mark.parametrize("overflow", ["points", "constraints"])
def test_resource_validation_still_precedes_cycle_detection(no_backend, overflow):
    source = triangle()
    if overflow == "points":
        source = replace(
            source, points=source.points + tuple(Point(f"p{i}", i, 0) for i in range(254))
        )
    else:
        source = replace(
            source,
            constraints=source.constraints
            + tuple(Constraint(f"extra{i}", "coincident", ("a", "b")) for i in range(510)),
        )
    with pytest.raises(SketchError) as caught:
        sketch_solver.solve(source)
    assert caught.value.code == "resource_limit" and not no_backend


def test_solve_service_and_strict_action_error_preserve_canonical_input(no_backend):
    document = candidate()
    before = document.to_json()
    with pytest.raises(SketchError) as caught:
        solve_sketch(document, "profile")
    assert caught.value.code == CODE
    req = request(document)
    original = copy.deepcopy(req)
    response = process_request(req)
    assert response == {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 2,
        "input_fingerprint": input_fingerprint(req),
        "ok": False,
        "result": None,
        "error": caught.value.to_dict(),
    }
    validated = solve_bridge.validate_solve_response(response, req)
    assert validated == response and validated is not response
    assert document.to_json() == before and req == original and not no_backend
    with pytest.raises(diagnostics.ConstraintDiagnosticsError, match="failed native solve report"):
        diagnostics.FailureDiagnostics(
            response,
            req,
            session_id="owner",
            command_revision=0,
            input_token="",
            input_revision=None,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(ok=True),
        lambda r: r.update(input_fingerprint="0" * 64),
        lambda r: r.update(result_version=1),
        lambda r: r.update(action="replay"),
        lambda r: r.update(result={}),
        lambda r: r.update(solved={"points": []}),
        lambda r: r.update(remaining_dof=0),
        lambda r: r.update(error=None),
        lambda r: r["error"].update(extra=True),
    ],
)
def test_cycle_error_does_not_relax_strict_solve_protocol(no_backend, mutation):
    req = request()
    response = process_request(req)
    assert response["error"]["code"] == CODE
    mutation(response)
    with pytest.raises((ValueError, TypeError, KeyError)):
        solve_bridge.validate_solve_response(response, req)


def test_rejected_draft_check_preserves_exact_source_and_checkpoint(no_backend):
    original = candidate().to_json()
    draft = drafts.GeneralSketchDraft(original, "profile", True)
    before, checkpoint = copy.deepcopy(draft.candidate()), store.dumps(draft)
    req = draft.solve_request()
    response = process_request(req)
    assert response["error"]["code"] == CODE and response["result"] is None
    assert not draft.record_validated_solution(req, response, draft.revision)
    assert not draft.has_current_solution and not draft.has_verified_trial
    assert draft.document_json == original and draft.candidate() == before
    assert store.dumps(draft) == checkpoint
    restored = store.restore(checkpoint, original)
    assert restored.candidate() == before and not restored.has_current_solution
    assert {c["id"] for c in restored.sketch["constraints"]} == {"c0", "c1", "c2"}
