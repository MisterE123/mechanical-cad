"""Three-reference mirror intent, strict persistence and independent residuals."""

import copy
import importlib
import itertools
import json
import math
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sketch_model import Constraint, Line, Point, SketchDefinition, SketchError
from mechanical_cad.sketch_relations import canonical_refs, equation_count, pair_residual
from mechanical_cad.sketch_solver import _unique_relations

package = types.ModuleType("mcad_symmetry_tests")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
selection = importlib.import_module(package.__name__ + ".constraint_selection")
draft_module = importlib.import_module(package.__name__ + ".general_sketch_draft")


def source(schema=3, constraints=True):
    return SketchDefinition(
        "geometry",
        (Point("a", -5, -5), Point("b", 5, 5), Point("p", 1, 3), Point("q", 3, 1)),
        (Line("axis", "a", "b", True),),
        (Constraint("sym", "symmetry", ("q", "p", "axis")),) if constraints else (),
        schema_version=schema,
    )


@pytest.mark.parametrize("schema", [1, 2, 3])
def test_roundtrip_and_selection_order(schema):
    sketch = source(schema)
    assert SketchDefinition.from_json(sketch.to_json()) == sketch
    entities = [
        {"kind": "point", "id": "p"},
        {"kind": "point", "id": "q"},
        {"kind": "line", "id": "axis"},
    ]
    for chosen in itertools.permutations(entities):
        action = selection.selection_contract(sketch.to_dict(), list(chosen)).action("symmetry")
        assert action.state == "existing" and action.relation_ids == ("sym",)
        assert action.refs == ("p", "q", "axis")
    assert canonical_refs("symmetry", ("q", "p", "axis")) == ("p", "q", "axis")
    assert equation_count("symmetry") == 2


@pytest.mark.parametrize(
    "refs",
    [
        ("p", "axis"),
        ("p", "p", "axis"),
        ("a", "p", "axis"),
        ("axis", "p", "q"),
        ("p", "q", "absent"),
        ("p", "q", "axis", "a"),
    ],
)
def test_invalid_reference_shape_and_axis_endpoint_rejected(refs):
    data = source().to_dict()
    data["constraints"][0]["refs"] = list(refs)
    with pytest.raises(SketchError):
        SketchDefinition.from_dict(data)
    with pytest.raises(ValueError):
        selection.selection_contract(data, [])


def test_independent_residual_rejects_midpoint_only_and_degenerate_axis():
    lines = {"axis": {"start": "a", "end": "b"}}
    points = {"a": (-5, 0), "b": (5, 0), "p": (1, 3), "q": (1, -3)}

    def residual():
        return pair_residual("symmetry", ("p", "q", "axis"), points, lines, {}, {})

    assert residual() == 0
    points["q"] = (-1, -3)  # Midpoint lies on axis, but these are not reflections.
    assert residual() == 2
    points["q"] = (1, -2)
    assert residual() == 0.5
    points["b"] = points["a"]
    assert math.isinf(residual())


def test_duplicate_equation_keeps_axis_role_and_authored_order():
    from dataclasses import replace

    sketch = source()
    duplicate = Constraint("sym2", "symmetry", ("p", "q", "axis"))
    unique, redundant = _unique_relations(
        replace(sketch, constraints=sketch.constraints + (duplicate,))
    )
    assert len(unique) == 1 and redundant == ("sym2",)
    assert unique[0].refs == ("p", "q", "axis")
    assert sketch.constraints[0].refs == ("q", "p", "axis")


@pytest.mark.parametrize("schema", [2, 3])
def test_command_idempotence_checkpoint_undo_redo_and_removal(schema):
    sketch = source(schema, constraints=False).to_dict()
    document = {
        "schema_version": 2,
        "id": "part",
        "name": "Symmetry",
        "units": "mm",
        "parameters": {},
        "active_feature": "sketch",
        "features": [{"id": "sketch", "kind": "sketch_constrained", "sketch": sketch}],
    }
    draft = draft_module.GeneralSketchDraft(json.dumps(document), "sketch", True, journal_version=3)
    before = copy.deepcopy(draft.sketch)
    result = draft.execute(draft_module.AddRelation("symmetry", ("q", "p", "axis")))
    identity = result.constraint_id
    assert result.changed
    assert not draft.execute(draft_module.AddRelation("symmetry", ("p", "q", "axis"))).changed
    restored = draft_module.GeneralSketchDraft.from_checkpoint_payload(
        draft.checkpoint_payload(), expected_journal_version=3
    )
    assert restored.sketch == draft.sketch
    restored.undo()
    assert restored.sketch == before
    restored.redo()
    assert restored.sketch["constraints"][0]["id"] == identity
    contract = selection.selection_contract(
        restored.sketch, [{"kind": "constraint", "id": identity}]
    )
    assert contract.relations[0].refs == ("q", "p", "axis")
    preview = restored.preview_delete((("constraint", identity),))
    with pytest.raises(ValueError, match="Check the current sketch"):
        restored.execute(draft_module.DeleteBatch(preview))
    restored.execute(draft_module.RecoverRemoveRelation(preview))
    assert restored.sketch["constraints"] == []
    restored.undo()
    assert restored.sketch["constraints"][0]["id"] == identity


def test_relation_math_mirrors_blender_contract():
    root = Path(__file__).resolve().parents[2]
    assert (root / "src/mechanical_cad/sketch_relations.py").read_bytes() == (
        root / "blender_addon/mechanical_cad_blender/sketch_relations.py"
    ).read_bytes()
