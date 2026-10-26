"""Read-only component context from current, unambiguous native selection.

Persisted row IDs are presentation history, never a fallback for a different
viewport selection. Display tags alone do not establish ownership/currentness.
"""

from . import assembly_display, assembly_state


def selected_component(context, data):
    """Return one canonical instance row, or None; never change selection/state."""
    try:
        if context.mode != "OBJECT":
            return None
        scene, layer, window = context.scene, context.view_layer, context.window
        if window is None or window.scene != scene or window.view_layer != layer:
            return None
        current = scene.mechanical_cad_assembly
        active = layer.objects.active
        selected = list(context.selected_objects)
        if active is None or context.active_object != active or not any(obj == active for obj in selected):
            return None
        instances = {row["id"]: row for row in data["instances"]}
        parts = {row["id"]: row for row in data["parts"]}
        meshes = []
        for obj in selected:
            if (
                scene.objects.get(obj.name) != obj
                or layer.objects.get(obj.name) != obj
                or not obj.select_get(view_layer=layer)
                or obj.hide_get(view_layer=layer)
                or not obj.visible_get(view_layer=layer)
                or obj.hide_select
                or obj.get(assembly_display.OWNER_KEY) != current.owner_id
                or not current.owner_id
                or obj.get(assembly_display.ASSEMBLY_KEY) != data["id"]
            ):
                return None
            row = instances.get(obj.get(assembly_display.INSTANCE_KEY))
            if row is None or obj.get(assembly_display.DEFINITION_KEY) != row["part_id"]:
                return None
            role = obj.get(assembly_display.ROLE_KEY)
            if role == "instance" and obj.type == "MESH":
                meshes.append(obj)
            elif role == "frame" and obj.type == "EMPTY":
                part = parts.get(row["part_id"])
                if not part or obj.get(assembly_display.FRAME_KEY) not in {
                    frame["id"] for frame in part["mate_frames"]
                }:
                    return None
            else:
                return None
        if len(meshes) != 1 or meshes[0] != active:
            return None
        # Also rejects duplicate/spoofed tags, changed geometry, stale revision,
        # foreign publication evidence and backend changes. Called once, not per row.
        if not assembly_state.display_is_current(context):
            return None
        return instances[active.get(assembly_display.INSTANCE_KEY)]
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, ReferenceError):
        return None
