"""Shared validation keeps authoring exception identity and strict input rules."""

import importlib
import sys
import types
from pathlib import Path

import pytest

PACKAGE = "mcad_shared_validation_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
validation = importlib.import_module(PACKAGE + ".general_sketch_validation")
commands = importlib.import_module(PACKAGE + ".general_sketch_commands")
fillet = importlib.import_module(PACKAGE + ".sketch_corner_fillet")


def test_command_reexports_keep_exact_exception_and_helper_identity():
    for name in ("DraftError", "_identifier", "_keys", "_require", "_json", "_coordinate",
                 "_point", "_journal_version", "_validate_sketch", "_normalized_sketch", "_ID"):
        assert getattr(commands, name) is getattr(validation, name)


@pytest.mark.parametrize("value", ["a", "0", "_", "a.b-c_9", "a" * 128])
def test_identifier_accepts_unchanged_stable_id_grammar(value):
    assert validation._identifier(value) == value


@pytest.mark.parametrize("value", [None, True, 1, [], "", ".a", "-a", "a b", "a\n", "é", "a" * 129])
def test_identifier_rejects_noncanonical_values(value):
    with pytest.raises(commands.DraftError, match="Invalid stable sketch ID"):
        validation._identifier(value)


def test_key_and_requirement_checks_stay_strict():
    validation._keys({"id": "a"}, {"id"})
    validation._require(True, "unused")
    for value in ({}, {"id": "a", "extra": 1}, ["id"]):
        with pytest.raises(commands.DraftError, match="Unsupported draft fields"):
            validation._keys(value, {"id"})
    with pytest.raises(commands.DraftError, match="exact message"):
        validation._require(False, "exact message")


def test_fillet_rejections_use_the_existing_command_exception():
    with pytest.raises(commands.DraftError, match="Radius must be"):
        fillet.prepare_corner({}, (), 0, {})
    with pytest.raises(commands.DraftError, match="Unsupported draft fields"):
        fillet.apply_record({}, {})
