"""Native registration and paged in-dialog explanations for every solid tool."""

import os
import sys
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import register, unregister  # noqa: E402
from mechanical_cad_blender.help_ui import _help_pages  # noqa: E402
from mechanical_cad_blender.solid_feature_edit import FEATURE_FIELDS  # noqa: E402

register()
for name in ("add_solid_feature", "edit_solid_feature"):
    props = getattr(bpy.ops.mcad, name).get_rna_type().properties
    for prop in ("show_help", "help_page", "help_previous", "help_next"):
        assert prop in props, (name, prop)
for kind in FEATURE_FIELDS:
    title, pages = _help_pages("feature." + kind)
    assert title != "From 2D profiles to a mechanical solid", kind
    assert pages and all(len(page) <= 2 for page in pages)
    assert all(len(line) <= 64 for page in pages for line in page)
print("MCAD_SOLID_HELP_SMOKE_OK", len(FEATURE_FIELDS))
unregister()
