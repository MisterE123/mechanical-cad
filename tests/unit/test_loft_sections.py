"""Ordered Loft persistence and mirrored native-free client contract."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.errors import CADException
from mechanical_cad.loft_sections import set_sections
from mechanical_cad.model import Document, Feature, feature_input_schema

ROOT = Path(__file__).resolve().parents[2]
package = types.ModuleType("loft_contract_tests")
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[package.__name__] = package
contracts = [
    importlib.import_module(package.__name__ + "." + name)
    for name in ("part_contracts", "part_contracts_v3")
]


def feature(count=3):
    f = {"id": "loft", "kind": "loft", "label": "Ordered", "params": {"ruled": 1}}
    set_sections(f, [f"p{i}" for i in range(count)])
    return f


def document(count=3):
    return {
        "schema_version": 1,
        "id": "d",
        "name": "Loft",
        "units": "mm",
        "parameters": {},
        "active_feature": "loft",
        "features": [
            {"id": f"p{i}", "kind": "sketch_circle", "params": {"radius": 3, "z": i * 5}}
            for i in range(count)
        ]
        + [feature(count)],
    }


@pytest.mark.parametrize("count", [2, 3, 16])
def test_roundtrip_dependency_order_immutable_and_mirrored(count):
    raw = document(count)
    doc = Document.from_dict(raw)
    canonical = doc.to_dict()
    assert Document.from_json(doc.to_json()).to_dict() == canonical
    f = doc.features[-1]
    assert tuple(feature_input_schema(f)) == tuple(f"section_{i + 1}" for i in range(count))
    raw["features"][-1]["loft_sections"]["ports"].reverse()
    assert f.to_dict() == canonical["features"][-1]
    with pytest.raises(TypeError):
        f.loft_sections["version"] = 3
    for client in contracts:
        assert client._expected_document(canonical) == canonical


@pytest.mark.parametrize(
    "mutate",
    [
        lambda f: f.update(loft_sections=None),
        lambda f: f["loft_sections"].update(version=True),
        lambda f: f["loft_sections"].update(version=2),
        lambda f: f["loft_sections"].update(unknown=1),
        lambda f: f["loft_sections"]["ports"].reverse(),
        lambda f: f["loft_sections"]["ports"].pop(),
        lambda f: f["inputs"].update(start="p0", end="p1"),
        lambda f: f["inputs"].update(section_2="p0"),
        lambda f: f.update(kind="sweep"),
    ],
)
def test_reject_ambiguous_mixed_or_invalid_intent(mutate):
    raw = document()
    mutate(raw["features"][-1])
    with pytest.raises(CADException):
        Document.from_dict(raw)
    for client in contracts:
        with pytest.raises(ValueError):
            client._expected_document(raw)


@pytest.mark.parametrize("count", [0, 1, 17])
def test_count_bounds(count):
    with pytest.raises(ValueError):
        feature(count)


def test_order_edit_is_explicit_and_legacy_unchanged():
    legacy = {
        "id": "l",
        "kind": "loft",
        "label": "Old",
        "params": {"ruled": 0},
        "inputs": {"start": "p0", "end": "p1"},
    }
    assert Feature.from_dict(legacy).to_dict() == legacy
    f = copy.deepcopy(legacy)
    set_sections(f, ["p2", "p0", "p1"])
    assert list(f["inputs"].values()) == ["p2", "p0", "p1"]
    assert Feature.from_dict(f).to_dict() == f
    assert (ROOT / "src/mechanical_cad/loft_sections.py").read_bytes() == (
        ROOT / "blender_addon/mechanical_cad_blender/loft_sections.py"
    ).read_bytes()


def test_nonprofile_or_cycle_inputs_fail_document_validation():
    for target in ("loft", "missing"):
        raw = document()
        raw["features"][-1]["inputs"]["section_2"] = target
        with pytest.raises(CADException):
            Document.from_dict(raw)


def test_solid_is_not_a_section_profile():
    raw = document()
    raw["features"].insert(
        3, {"id": "solid", "kind": "extrude", "params": {"length": 2}, "inputs": {"profile": "p0"}}
    )
    raw["features"][-1]["inputs"]["section_2"] = "solid"
    with pytest.raises(CADException):
        Document.from_dict(raw)
