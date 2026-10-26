"""Explicit, reversible viewport focus; never rewrite a workspace layout."""

import bpy

from . import workspace


def is_focused(context):
    return bool(getattr(getattr(context, "screen", None), "show_fullscreen", False))


def focus_label(context):
    return "Restore Layout" if is_focused(context) else "Focus CAD"


def compact_draft_part_status(state, draft):
    """Only compress the ordinary dirty notice, never an unexplained diagnostic."""
    return bool(
        draft is not None
        and state.status == "DIRTY"
        and state.error in {"", "Regenerate to build this document."}
    )


class MCAD_OT_focus_workspace(bpy.types.Operator):
    bl_idname = "mcad.focus_workspace"
    bl_label = "Focus CAD / Restore Layout"
    bl_description = (
        "Temporarily maximize this CAD viewport, keeping its history and sketch controls; "
        "click Restore Layout to return all editors to their previous layout. "
        "An active sketch is saved for Resume because Blender replaces the viewport. "
        "Does not isolate objects or change the model"
    )

    @classmethod
    def poll(cls, context):
        return bool(
            workspace.is_cad_workspace(context)
            and getattr(context, "area", None)
            and context.area.type == "VIEW_3D"
            and getattr(context, "window", None)
            and bpy.ops.screen.screen_full_area.poll()
        )

    def execute(self, context):
        owner = workspace.active_draft(context)
        if owner is not None:
            # Maximize replaces Blender's area/region identity. Save authoring
            # intent before that happens; never rebind or weaken draft guards.
            try:
                owner.checkpoint()
                if not owner.suspend("CAD view changed; choose Resume to keep editing"):
                    self.report({"ERROR"}, "Sketch needs recovery; layout was not changed")
                    return {"CANCELLED"}
            except Exception as exc:
                self.report({"ERROR"}, "Could not save sketch; layout unchanged: " + str(exc))
                return {"CANCELLED"}
            self.report({"INFO"}, "Sketch saved. Choose Resume in the CAD sidebar to keep editing")
        # Blender owns the exact reversible layout, including customized editors.
        # Unlike fullscreen with hidden panels, maximize retains the sidebar and
        # header. Never join/close areas or change any other workspace's screen.
        return bpy.ops.screen.screen_full_area(use_hide_panels=False)


def draw_focus(layout, context, *, compact=False):
    layout.operator(
        "mcad.focus_workspace",
        text="" if compact else focus_label(context),
        icon="FULLSCREEN_EXIT" if is_focused(context) else "FULLSCREEN_ENTER",
    )
