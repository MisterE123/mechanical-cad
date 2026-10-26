"""Repeated Blender selector validation must not grow compound CAD suffixes."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

P = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender/document_paths.py"
spec = importlib.util.spec_from_file_location("document_paths", P)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize("suffix", [".mcad.json", ".mcad-assembly.json"])
@pytest.mark.parametrize("ending", ["", ".json", "full", "stem", "upper"])
def test_compound_suffix_is_idempotent(suffix, ending):
    ending = {"full": suffix, "stem": suffix[:-5], "upper": suffix.upper()}.get(ending, ending)
    value = SimpleNamespace(filepath="/tmp/my.part" + ending, filename_ext=suffix)
    module.normalized_export_check(value, None)
    accepted = value.filepath
    assert accepted.lower() == "/tmp/my.part" + suffix
    for _ in range(5):
        assert not module.normalized_export_check(value, None)
        assert value.filepath == accepted
