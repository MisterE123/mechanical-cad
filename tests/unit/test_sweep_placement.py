"""Versioned Sweep construction intent, strict mirrored boundary and no legacy migration."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.errors import CADException
from mechanical_cad.model import Feature
from mechanical_cad.sweep_placement import validate_placement

ROOT = Path(__file__).resolve().parents[2]
package = types.ModuleType("sweep_placement_tests")
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[package.__name__] = package
edit = importlib.import_module(package.__name__ + ".solid_feature_edit")
contracts = importlib.import_module(package.__name__ + ".part_contracts")
contracts3 = importlib.import_module(package.__name__ + ".part_contracts_v3")
INTENT = {"version": 1, "mode": "path_start_centroid", "reverse": False, "roll_degrees": 0}


def feature():
    return {
        "id": "s",
        "kind": "sweep",
        "label": "Sweep",
        "params": {},
        "inputs": {"profile": "p", "path": "path"},
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", True),
        ("version", 2),
        ("mode", "closest_face"),
        ("reverse", 1),
        ("roll_degrees", True),
        ("roll_degrees", float("nan")),
        ("roll_degrees", float("inf")),
        ("roll_degrees", 10**500),
        ("roll_degrees", "angle"),
        ("roll_degrees", 361),
        ("unknown", 0),
    ],
)
def test_strict_intent_rejects_unknown_or_unbounded_fields(field, value):
    intent = {**INTENT, field: value}
    with pytest.raises(ValueError):
        validate_placement(intent)
    with pytest.raises(CADException):
        Feature.from_dict({**feature(), "sweep_placement": intent})


def test_legacy_omission_and_immutable_new_field():
    old = feature()
    assert Feature.from_dict(old).to_dict() == old
    raw = {**old, "sweep_placement": copy.deepcopy(INTENT)}
    parsed = Feature.from_dict(raw)
    raw["sweep_placement"]["roll_degrees"] = 90
    assert parsed.sweep_placement["roll_degrees"] == 0
    with pytest.raises(TypeError):
        parsed.sweep_placement["reverse"] = True
    with pytest.raises(CADException):
        Feature.from_dict({**old, "sweep_placement": None})
    with pytest.raises(CADException):
        Feature(
            "x", "extrude", "Wrong kind", {"length": 2}, {"profile": "p"}, sweep_placement=INTENT
        )


def test_edit_same_intent_retains_literal_and_authored_removes_only_opt_in():
    f = feature()
    edit.set_sweep_placement(f, "AUTO", reverse=True, roll="12.3456789012345")
    before = copy.deepcopy(f)
    edit.set_sweep_placement(f, "AUTO", reverse=True, roll="12.3456789012345")
    assert f == before
    edit.set_sweep_placement(f, "AUTHORED")
    assert f == feature()
    edit.set_sweep_placement(f, "AUTO", roll="0")
    assert type(f["sweep_placement"]["roll_degrees"]) is int
    with pytest.raises(ValueError, match="literal"):
        edit.set_sweep_placement(f, "AUTO", roll="angle / 2")


def test_mirrored_native_free_validation_and_both_canonical_boundaries():
    assert (ROOT / "src/mechanical_cad/sweep_placement.py").read_bytes() == (
        ROOT / "blender_addon/mechanical_cad_blender/sweep_placement.py"
    ).read_bytes()
    doc = {
        "schema_version": 2,
        "units": "mm",
        "id": "d",
        "name": "D",
        "parameters": {},
        "features": [{**feature(), "sweep_placement": INTENT}],
        "active_feature": "s",
    }
    for contract in (contracts, contracts3):
        expected = contract._expected_document(doc)
        assert expected["features"][0]["sweep_placement"] == INTENT
        wrong = copy.deepcopy(doc)
        wrong["features"][0]["sweep_placement"]["mode"] = "inferred_identity"
        with pytest.raises(ValueError):
            contract._expected_document(wrong)
