"""Keep all three Part picker paths on the native-qualified visibility boundary."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender"


@pytest.mark.parametrize("name", ["face_pick", "edge_pick", "direct_edge_pick"])
def test_part_picker_uses_shared_viewport_ray_and_retains_display_binding(name):
    tree = ast.parse((ROOT / (name + ".py")).read_text())
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "viewport_ray"
        and any(alias.name == "ray_cast" for alias in node.names)
        for node in ast.walk(tree)
    )
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert any(isinstance(node.func, ast.Name) and node.func.id == "ray_cast" for node in calls)
    assert not any(
        isinstance(node.func, ast.Attribute) and node.func.attr == "ray_cast" for node in calls
    )
    assert any(
        isinstance(node.func, ast.Name) and node.func.id == "bound_feature" for node in calls
    )
