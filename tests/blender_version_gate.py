"""Verify explicit older-runtime rejection before any RNA or handler mutation."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import registration  # noqa: E402
from mechanical_cad_blender.common import MIN_BLENDER_VERSION  # noqa: E402


def rejected():
    try:
        addon.register()
    except RuntimeError as exc:
        assert "requires Blender 5.2" in str(exc)
        assert "exit cleanup" in str(exc)
    else:
        raise AssertionError("Unsupported Blender was accepted")
    assert not hasattr(bpy.types.Scene, "mechanical_cad")
    assert not hasattr(bpy.types.Scene, "mechanical_cad_assembly")
    assert not any(getattr(cls, "is_registered", False) for cls in registration.CLASSES)
    assert registration._on_blend_load not in bpy.app.handlers.load_post


if bpy.app.version < MIN_BLENDER_VERSION:
    rejected()
    print("MCAD_OLDER_BLENDER_REJECTED_OK", bpy.app.version_string)
else:
    for old_version in ((4, 3, 2), (5, 1, 99)):
        # A deliberately minimal mock proves the gate runs before any other bpy API.
        with patch.object(
            registration, "bpy", SimpleNamespace(app=SimpleNamespace(version=old_version))
        ):
            rejected()
    addon.register()
    assert hasattr(bpy.types.Scene, "mechanical_cad_assembly")
    addon.unregister()
    assert not hasattr(bpy.types.Scene, "mechanical_cad")
    print("MCAD_BLENDER_VERSION_GATE_OK", bpy.app.version_string)
