"""Native settings/lifetime revocation and read-only current-evidence UI gates.

Use native Blender --background --factory-startup --python-exit-code 1.
This exercises real RNA callbacks and owners, not installed-package GUI usability.
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    assembly_state,
    backend_runtime,
    document_state,
    guarded_transport,
    panels,
    register,
    registration,
    unregister,
    workspace,
    workspace_ui,
)

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


class Layout:
    """A label recorder for the production panel draw methods."""

    def __init__(self, entries=None):
        self.entries = [] if entries is None else entries
        self.enabled = True
        self.alert = False

    def row(self, **_kwargs):
        return Layout(self.entries)

    column = box = row

    def label(self, **kwargs):
        self.entries.append(kwargs)

    def operator(self, *_args, **_kwargs):
        return SimpleNamespace()

    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


def labels(layout):
    return "\n".join(item.get("text", "") for item in layout.entries)


def draw_panels(context):
    with (
        patch.object(
            guarded_transport, "execute", side_effect=AssertionError("draw launched work")
        ),
        patch.object(
            guarded_transport.GuardedJob, "start", side_effect=AssertionError("draw launched job")
        ),
        patch.object(workspace, "get_role", return_value="PART"),
        patch.object(workspace, "has_draft", return_value=False),
        patch.object(workspace, "active_draft", return_value=None),
    ):
        main, history, feature = Layout(), Layout(), Layout()
        panels.MCAD_PT_main.draw(SimpleNamespace(layout=main), context)
        workspace_ui.MCAD_PT_workspace_history.draw(SimpleNamespace(layout=history), context)
        state = context.scene.mechanical_cad
        panels.MCAD_UL_features.draw_item(
            None, context, feature, state, state.features[0], 0, state, "feature_index", 0
        )
    return main, history, feature


register()
entry = bpy.context.preferences.addons.new()
entry.module = "mechanical_cad_blender"
preferences = entry.preferences
preferences.project_root = str(ROOT)
preferences.python_executable = os.environ["MCAD_PYTHON"]
window = bpy.context.window
area = next(item for item in window.screen.areas if item.type == "VIEW_3D")
region = next(item for item in area.regions if item.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    scene = context.scene
    state = scene.mechanical_cad
    document = json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
    document_state._populate_document(scene, document)
    check(document_state.regenerate(context), "Guarded real rectangle Part is ready")
    canonical = state.document_json
    unrelated = {obj.as_pointer() for obj in scene.objects if not obj.get("mechanical_cad_owner")}
    authentic = document_state.current_part_result(context)
    check(authentic is not None, "Current result comes from live guarded evidence")
    state.feature_index = 0
    state.features[0].status = "failed"
    state.features[0].sketch_report_json = json.dumps({"status": "forged", "remaining_dof": 987654})
    state.features[0].sketch_report_status = "CURRENT"
    state.features[0].sketch_document_json = canonical
    state.volume = 987654
    main, history, feature = draw_panels(context)
    check(
        "987654" not in labels(main) + labels(history),
        "Saved report/volume cannot replace current evidence",
    )
    check("Remaining DoF: 0" in labels(history), "Current DoF is read from immutable evidence")
    check(
        feature.entries[0]["icon"] == "CHECKMARK",
        "Feature success icon follows live result, not saved status",
    )
    other_scene = bpy.data.scenes.new("Other guarded CAD scene")
    try:
        window.scene = other_scene
        with bpy.context.temp_override(scene=other_scene):
            document_state._populate_document(other_scene, document_state.demo_document())
            check(
                document_state.regenerate(bpy.context),
                "Second scene establishes independent evidence",
            )
            other_canonical = other_scene.mechanical_cad.document_json
    finally:
        window.scene = scene

    for field, changed in (
        ("project_root", str(ROOT.parent / "cad_dof_hotfix")),
        ("python_executable", preferences.python_executable + ".unavailable"),
        ("timeout_seconds", 61.0),
        ("linear_deflection", 0.2),
    ):
        check(document_state.regenerate(context), "Fresh evidence before " + field + " ABA")
        old_evidence, _owner = document_state.current_part_evidence(context)
        old_stamp = backend_runtime.stamp()
        original = getattr(preferences, field)
        with (
            patch.object(
                guarded_transport, "execute", side_effect=AssertionError("callback solved")
            ),
            patch.object(
                guarded_transport.GuardedJob, "wait", side_effect=AssertionError("callback waited")
            ),
        ):
            setattr(preferences, field, changed)
            setattr(preferences, field, original)
        check(backend_runtime.stamp()[1] >= old_stamp[1] + 2, field + " callback observes ABA")
        check(
            not backend_runtime.is_current(old_evidence.selection, context),
            "Old " + field + " evidence stays revoked",
        )
        check(not document_state.part_is_current(context), field + " change revokes current Part")
        check(state.document_json == canonical, field + " change preserves exact authored data")
        check(
            other_scene.mechanical_cad.document_json == other_canonical
            and other_scene.mechanical_cad.status == "DIRTY",
            field + " callback invalidates every CAD scene without changing authored bytes",
        )
        state.status = "READY"
        state.geometry_status = "PASSED"
        state.features[0].sketch_report_status = "CURRENT"
        main, history, feature = draw_panels(context)
        check(
            "Build: Up to date" not in labels(main), "Saved READY cannot restore current UI"
        )
        check("Remaining DoF:" not in labels(history), "Saved CURRENT cannot restore DoF")
        check("Geometry: Outdated" in labels(history), "Saved PASSED cannot restore verification")
        check(feature.entries[0]["icon"] == "DOT", "Saved feature success has no current icon")

    check(
        document_state.regenerate(context), "Corrected settings recover through a fresh operation"
    )
    with (
        patch.object(
            document_state,
            "invalidate_backend",
            side_effect=RuntimeError("injected presentation failure"),
        ),
        patch.object(
            assembly_state, "invalidate_backend", wraps=assembly_state.invalidate_backend
        ) as assembly_invalidate,
    ):
        backend_runtime.revoke("Test independent invalidation callbacks")
        check(
            assembly_invalidate.call_count == 1,
            "A failed Part presentation hook cannot skip Assembly revocation",
        )
        check(
            not document_state.part_is_current(context),
            "Generation invalidation survives presentation cleanup failure",
        )
    check(
        document_state.regenerate(context),
        "Fresh operation recovers after a failed presentation hook",
    )
    old_evidence, _owner = document_state.current_part_evidence(context)
    registration._before_history_change(None)
    state.status = "READY"
    registration._after_history_change(None)
    check(
        not document_state.part_is_current(context),
        "History restoration cannot restore runtime evidence",
    )
    check(
        not backend_runtime.is_current(old_evidence.selection, context),
        "History revokes retained selection",
    )
    check(document_state.regenerate(context), "Fresh operation recovers after history")
    old_lifetime = backend_runtime.stamp()[0]
    unregister()
    register()
    state = scene.mechanical_cad
    check(backend_runtime.stamp()[0] != old_lifetime, "Re-enable uses a new nonrepeating lifetime")
    check(state.document_json == canonical, "Re-enable preserves exact canonical bytes")
    check(
        not document_state.part_is_current(context), "Rebind cannot restore saved READY authority"
    )
    check(document_state.regenerate(context), "Re-enabled owner can establish fresh authority")
    check(
        unrelated <= {obj.as_pointer() for obj in scene.objects},
        "Lifecycle preserves unrelated scene objects",
    )
    bpy.data.scenes.remove(other_scene)

check(
    not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules),
    "No native CAD imports in Blender",
)
bpy.context.preferences.addons.remove(entry)
unregister()
print("BACKEND_LIFECYCLE_OK", len(checks), bpy.app.version_string)
