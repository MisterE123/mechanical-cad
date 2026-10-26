"""Check actual target Blender icon enums, not a permissive mocked UILayout."""

import ast
import os
import sys
from pathlib import Path

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import workspace_ui  # noqa: E402

icons = set(bpy.types.UILayout.bl_rna.functions["operator"].parameters["icon"].enum_items.keys())
checked = []


def result_literals(node):
    """Only icon result branches; condition strings are not icon names."""
    if isinstance(node, ast.Constant) and type(node.value) is str:
        yield node.value
    elif isinstance(node, ast.IfExp):
        yield from result_literals(node.body)
        yield from result_literals(node.orelse)


for path in (ROOT / "blender_addon/mechanical_cad_blender").glob("*.py"):
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.keyword) or node.arg != "icon":
            continue
        for value in result_literals(node.value):
            assert value in icons, f"{path.name}:{node.lineno}: invalid icon {value}"
            checked.append((path.name, node.lineno, value))
for action, values in workspace_ui._ACTIONS.items():
    assert values[3] in icons, (action, values[3])
    checked.append(("workspace action", action, values[3]))
assert len(checked) > 100, "The production UI literal/icon registry should actually be covered"
print("UI_ICON_CONTRACT_OK", len(checked), bpy.app.version_string)
