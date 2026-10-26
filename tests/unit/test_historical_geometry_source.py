"""Historical source stays pinned even when current source evolves."""

import ast
from pathlib import Path

import pytest
from historical_geometry_source import EXPECTED, historical_geometry_source


def test_source_pins_equal_independent_existing_inverse_pins():
    path = Path(__file__).with_name("test_arc_profile_native_end_cap.py")
    node = next(
        node for node in ast.parse(path.read_bytes()).body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "INTEGRATION_SOURCE_ORIGINALS"
                for target in node.targets)
    )
    existing = ast.literal_eval(node.value)
    for name, expected in EXPECTED.items():
        assert expected == existing[f"src/mechanical_cad/{name}.py"]
        assert historical_geometry_source(name)


@pytest.mark.parametrize("name", EXPECTED)
@pytest.mark.parametrize("change", ("append", "same_length"))
def test_mutated_historical_source_is_rejected(tmp_path, name, change):
    raw = historical_geometry_source(name)
    changed = raw + b" " if change == "append" else bytes([raw[0] ^ 1]) + raw[1:]
    (tmp_path / f"{name}.py.txt").write_bytes(changed)
    with pytest.raises(AssertionError):
        historical_geometry_source(name, root=tmp_path)


def test_unlisted_source_is_not_read(tmp_path):
    with pytest.raises(KeyError):
        historical_geometry_source("../sidecar", root=tmp_path)
