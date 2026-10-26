"""Read-only narrow panel drawing with real accepted/proposed native CAD state."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path[:0] = [str(ROOT / "blender_addon"), str(ROOT / "tests")]
from mechanical_cad_blender import (  # noqa: E402
    bridge,
    document_state,
    help_ui,
    register,
    staged_edit,
    unregister,
)
from mechanical_cad_blender import (  # noqa: E402
    support_intent_ui as ui,
)
from staged_edit_cases import support_case  # noqa: E402


class NarrowContext:
    region = SimpleNamespace(width=240)

    def __getattr__(self, key):
        return getattr(bpy.context, key)


class Layout:
    def __init__(self):
        self.events = []
        self.buttons = []

    def operator(self, name, **kwargs):
        self.events.append(("operator", name))
        button = SimpleNamespace(identifier=name, **kwargs)
        self.buttons.append(button)
        return button

    def label(self, **kwargs):
        self.events.append(("label", kwargs.get("text", "")))

    def prop(self, owner, name, **kwargs):
        self.events.append(("prop", name))

    def template_list(self, *args, **kwargs):
        self.events.append(("history", args[0]))

    def row(self, **kwargs):
        return self

    box = row
    column = row

    def menu(self, *args, **kwargs):
        pass

    def separator(self):
        pass


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **k: {"RUNNING_MODAL"})

    def __getattr__(self, name):
        return getattr(bpy.context, name)


class DrawOwner:
    def __init__(self, operator, layout):
        self.operator = operator
        self.layout = layout

    def __getattr__(self, name):
        return getattr(self.operator, name)


def exercise(self, context):
    assert isinstance(self.properties, bpy.types.OperatorProperties)
    assert self.invoke(DialogContext(), None) == {"RUNNING_MODAL"}
    counts = []
    original = context.scene.mechanical_cad.document_json
    proposal = staged_edit.current(context)
    for policy, orientation, reset in (
        ("STRICT", "MINIMAL_TWIST", False),
        ("PRESERVE_PLANE", "MINIMAL_TWIST", False),
        ("PRESERVE_PLANE", "MINIMAL_TWIST", True),
        ("PRESERVE_PLANE", "WORLD_AXES", True),
    ):
        self.policy, self.orientation, self.reset_frame = policy, orientation, reset
        captured = []
        original_help = help_ui._help_pages

        def pages(topic, detail="", captured=captured, original_help=original_help):
            captured.append(detail)
            return original_help(topic, detail)

        with patch.object(
            document_state, "_run_sidecar", side_effect=AssertionError("Draw replay")
        ):
            with patch.object(help_ui, "_help_pages", side_effect=pages):
                layout = Layout()
                ui.MCAD_OT_edit_sketch_support.draw(DrawOwner(self, layout), context)
        counts.append(len(layout.events))
        assert ("prop", "orientation") in layout.events
        assert ("prop", "reset_frame") in layout.events
        assert not layout.buttons, "No nested help operator"
        details = captured[-1]
        assert "Nearly opposite normals" in details and "Missing lineage stops" in details
        assert "Reset explicitly adopts" in details and "Strict requires an exact face" in details
        assert "Needs review:" in details or "ASSUMPTION:" in details or "Exact:" in details
        title, all_pages = original_help(self.help_topic, details)
        self.show_help = True
        # Real RNA callback can advance beyond the static topic's page count.
        for index in range(1, len(all_pages) + 1):
            self.help_page = index
            expanded = Layout()
            with patch.object(
                document_state, "_run_sidecar", side_effect=AssertionError("Help replay")
            ):
                ui.MCAD_OT_edit_sketch_support.draw(DrawOwner(self, expanded), context)
            assert len(expanded.events) == counts[-1]
            for line in all_pages[index - 1]:
                assert ("label", line) in expanded.events
            if index < len(all_pages):
                self.properties.help_next = True
                assert self.help_page == index + 1
        self.show_help = False
        self.help_page = 1
        assert (self.policy, self.orientation, self.reset_frame) == (policy, orientation, reset)
        assert context.scene.mechanical_cad.document_json == original
        assert staged_edit.current(context) is proposal
    assert len(set(counts)) == 1, counts
    assert counts[0] <= 24, counts
    self._release()
    return {"CANCELLED"}


assert bpy.app.background
ui.MCAD_OT_edit_sketch_support.execute = exercise
register()
base, proposed = support_case()
assert document_state._commit_candidate(bpy.context, base)
try:
    document_state._commit_candidate(bpy.context, proposed, stage_feature_id="slot_tool")
except bridge.BridgeError:
    pass
proposal = staged_edit.current(bpy.context)
assert proposal
assert bpy.ops.mcad.edit_sketch_support(
    "EXEC_DEFAULT", feature_id="attached", staged_token=proposal.token
) == {"CANCELLED"}
unregister()
print("SUPPORT_STABLE_DRAW_NATIVE_OK", flush=True)
