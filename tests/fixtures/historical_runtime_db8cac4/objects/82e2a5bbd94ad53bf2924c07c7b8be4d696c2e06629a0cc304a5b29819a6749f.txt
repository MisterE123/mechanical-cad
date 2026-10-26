"""Guard the Blender/native boundary and the maintainable add-on module split.

These tests parse source only, so the normal core suite needs neither bpy nor a
Blender installation. Runtime registration remains covered by Blender smokes.
"""

import ast
from pathlib import Path

ADDON = Path(__file__).resolve().parents[2] / "blender_addon" / "mechanical_cad_blender"


def _modules():
    return {path.stem: ast.parse(path.read_text(encoding="utf-8")) for path in ADDON.glob("*.py")}


def test_addon_never_imports_native_cad_or_core_model_in_blender():
    forbidden = {"OCP", "cadquery", "build123d", "mechanical_cad", "slvs"}
    for module, tree in _modules().items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            else:
                continue
            assert not forbidden.intersection(name.split(".")[0] for name in names), module


def test_addon_implementation_imports_are_acyclic():
    modules = _modules()
    edges = {name: set() for name in modules}
    for module, tree in modules.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                names = (
                    [node.module.split(".")[0]]
                    if node.module
                    else [alias.name for alias in node.names]
                )
                edges[module].update(name for name in names if name in modules)
    complete = set()

    def visit(module, path):
        assert module not in path, "Circular add-on dependency: " + " -> ".join((*path, module))
        if module not in complete:
            for dependency in sorted(edges[module]):
                visit(dependency, (*path, module))
            complete.add(module)

    for module in sorted(modules):
        visit(module, ())


def test_addon_entry_point_stays_metadata_and_lifecycle_only():
    source = (ADDON / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert len(source.splitlines()) <= 100, "Move implementation into a focused add-on module."
    assert not any(isinstance(node, ast.ClassDef) for node in tree.body)
    assert {
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    } <= {"register", "unregister"}
