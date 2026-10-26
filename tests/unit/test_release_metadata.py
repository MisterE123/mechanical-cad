"""Source and Blender metadata must identify the same preview version."""

import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def assigned_literal(path, name):
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Missing {name} in {path}")


def test_project_core_and_blender_versions_match():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    core = assigned_literal(ROOT / "src/mechanical_cad/__init__.py", "__version__")
    addon = assigned_literal(ROOT / "blender_addon/mechanical_cad_blender/__init__.py", "bl_info")[
        "version"
    ]
    verifier = assigned_literal(ROOT / "scripts/verify_sidecar_install.py", "EXPECTED_VERSION")
    assert project == core == verifier == ".".join(str(part) for part in addon)
    bootstrap = ast.parse((ROOT / "scripts/standalone_child_bootstrap.py").read_text())
    bootstrap_versions = [
        node.comparators[0].value
        for node in ast.walk(bootstrap)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Attribute)
        and node.left.attr == "__version__"
        and len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Constant)
    ]
    assert bootstrap_versions == [project]



def test_declared_minimum_matches_registration_and_committed_release_metadata():
    addon = ROOT / "blender_addon/mechanical_cad_blender"
    info = assigned_literal(addon / "__init__.py", "bl_info")
    minimum = assigned_literal(addon / "common.py", "MIN_BLENDER_VERSION")
    release = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["mechanical_cad"][
        "release"
    ]
    assert info["blender"] == minimum == tuple(release["blender_minimum"])
    assert minimum == (5, 2, 0)
    assert "rooted-tree" in release["scope"]
    assert "Linux" in release["qualified_runtime"]


def test_native_dependency_pin_is_independent_of_application_version():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    # This is the qualified native pin already asserted by
    # test_assembly_kernel.test_runtime_versions_are_actual_and_json_safe and
    # recorded in THIRD_PARTY_NOTICES.md, not the application's release number.
    # Numeric components avoid rewriting this guard with an application-version
    # substring replacement (which previously changed 8.0.1.1.0 to 8.0.1.3.0).
    native_version = ".".join(map(str, (8, 0, 1, 1, 0)))
    declared = [item for item in project["dependencies"] if item.startswith("cadquery-ocp")]
    assert declared == [f"cadquery-ocp-novtk=={native_version}"]
