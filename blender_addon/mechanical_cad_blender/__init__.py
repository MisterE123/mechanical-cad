"""Mechanical CAD: parametric history backed by an isolated OpenCascade process.

The .mcad.json document is authoritative. Blender meshes are disposable display
caches. Implementation layers are separate from this Blender add-on entry point.
"""

# Blender convention keeps discoverable metadata ahead of imports.
# ruff: noqa: E402

bl_info = {
    "name": "Mechanical CAD",
    "author": "Mechanical CAD contributors",
    "version": (1, 30, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > CAD > Open CAD Workspaces",
    "description": "Parametric sketches, editable solid features, mechanical assemblies and exact exports",
    "category": "Add Mesh",
}

from . import bridge as bridge
from . import registration
from .common import DOCUMENT_KEY as DOCUMENT_KEY
from .common import FEATURE_KEY as FEATURE_KEY
from .common import MM_TO_METERS as MM_TO_METERS
from .common import OWNER_KEY as OWNER_KEY
from .display import _owned_objects as _owned_objects
from .document_state import demo_document as demo_document
from .document_state import regenerate as regenerate
from .registration import _deferred_rebind as _deferred_rebind
from .registration import _on_blend_load as _on_blend_load
from .registration import _rebind_existing_documents as _rebind_existing_documents


def register():
    """Register the add-on; retain the baseline test hook during module migration."""
    registration.register(rebind=_rebind_existing_documents)


def unregister():
    """Unregister classes, handlers and deferred work without deleting documents."""
    registration.unregister()


if __name__ == "__main__":
    register()
