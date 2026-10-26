"""Owned CAD workspaces and deferred native screen transitions.

Workspace duplication/switching is asynchronous in Blender. One native change is
issued per timer step, and the resulting context is verified before use. Model
JSON and scene data never belong to a workspace or get copied by this module.
"""

import bpy
from bpy.app.handlers import persistent
from mathutils import Quaternion, Vector

OWNER_KEY = "mechanical_cad_workspace_owner"
ROLE_KEY = "mechanical_cad_workspace_role"
OWNER = "mechanical_cad"
ROLES = ("SKETCH", "PART", "ASSEMBLY")
_JOBS = {}
_QUERY_DRAFT = None
_CANCEL_DRAFT = None
_SUSPEND_DRAFT = None
_SUSPENDED_DRAFT = None
_DRAFT_RECOVERY = None
_LAST_ERROR = ""


def get_role(context):
    workspace = getattr(context, "workspace", None)
    if workspace and workspace.get(OWNER_KEY) == OWNER:
        value = workspace.get(ROLE_KEY)
        return value if value in ROLES else None
    return None


role = get_role


def is_cad_workspace(context):
    return get_role(context) is not None


def set_draft_handlers(query=None, cancel=None, *, suspend=None, suspended=None, recovery=None):
    global _QUERY_DRAFT, _CANCEL_DRAFT, _SUSPEND_DRAFT, _SUSPENDED_DRAFT, _DRAFT_RECOVERY
    _QUERY_DRAFT, _CANCEL_DRAFT = query, cancel
    _SUSPEND_DRAFT, _SUSPENDED_DRAFT = suspend, suspended
    _DRAFT_RECOVERY = recovery


def active_draft(context=None):
    return _QUERY_DRAFT(context) if _QUERY_DRAFT else None


def suspended_draft(context):
    return _SUSPENDED_DRAFT(context) if _SUSPENDED_DRAFT else {"present": False}


def has_draft(context):
    active = active_draft()
    same_scene = active is not None and getattr(active, "scene", None) == context.scene
    return bool(same_scene or active_draft(context) or suspended_draft(context).get("present"))


def draft_recovery_notice():
    return _DRAFT_RECOVERY() if _DRAFT_RECOVERY else ""


def _handoff_draft(reason, context=None):
    if _SUSPEND_DRAFT:
        _SUSPEND_DRAFT(reason, context=context)
    elif _CANCEL_DRAFT:
        _CANCEL_DRAFT(reason, context=context)


def find_workspace(role):
    return next(
        (
            workspace
            for workspace in bpy.data.workspaces
            if workspace.get(OWNER_KEY) == OWNER and workspace.get(ROLE_KEY) == role
        ),
        None,
    )


def _window_alive(window):
    return any(item == window for item in bpy.context.window_manager.windows)


def _configure_new(window, workspace, role):
    """Only freshly duplicated layouts are configured; later entry is read-only."""
    workspace.use_pin_scene = False
    areas = list(window.screen.areas)
    if not any(area.type == "VIEW_3D" for area in areas):
        max(areas, key=lambda area: area.width * area.height).type = "VIEW_3D"
    for area in areas:
        if area.type != "VIEW_3D":
            continue
        space = area.spaces.active
        space.show_region_toolbar = False
        space.show_region_ui = True
        space.show_region_tool_header = False
        space.show_gizmo = True
        if role == "SKETCH":
            rv3d = space.region_3d
            rv3d.view_rotation = Quaternion((1, 0, 0, 0))
            rv3d.view_location = Vector((0, 0, 0))
            rv3d.view_perspective = "ORTHO"
            rv3d.view_distance = 0.08 / max(window.scene.unit_settings.scale_length, 1e-12)
            space.clip_start = min(space.clip_start, rv3d.view_distance / 1000)
        if role == "SKETCH":
            space.shading.type = "WIREFRAME"
        area.tag_redraw()


def _select_new_category(window):
    ready = True
    for area in window.screen.areas:
        if area.type != "VIEW_3D":
            continue
        for region in area.regions:
            if region.type != "UI" or not hasattr(region, "active_panel_category"):
                continue
            # Blender builds dynamic categories during drawing. Before that the
            # public RNA property is temporarily noneditable, even in 5.2.2.
            if region.is_property_readonly("active_panel_category"):
                ready = False
                continue
            try:
                region.active_panel_category = "CAD"
            except (TypeError, AttributeError):
                ready = False
        area.tag_redraw()
    return ready


def _with_ready_context(job):
    window = job["window"]
    area = max(
        (area for area in window.screen.areas if area.type == "VIEW_3D"),
        key=lambda area: area.width * area.height,
        default=None,
    )
    if area is None:
        raise RuntimeError("The CAD workspace needs a 3D Viewport")
    region = next((region for region in area.regions if region.type == "WINDOW"), None)
    if region is None:
        raise RuntimeError("The CAD viewport is not ready")
    callback = job["callback"]
    if callback:
        with bpy.context.temp_override(window=window, area=area, region=region):
            callback(bpy.context)


def _step(job):
    window = job["window"]
    if not _window_alive(window):
        return True
    if window.scene != job["scene"]:
        raise RuntimeError("CAD workspace setup cancelled because the scene changed")
    job["ticks"] += 1
    if job["ticks"] > 120:
        raise RuntimeError("CAD workspace setup timed out")
    phase = job["phase"]
    if phase == "create":
        if not job["remaining"]:
            # Only initial setup groups the owned tabs. Ordinary reentry keeps
            # any ordering the user chose.
            job["phase"] = "reorder" if job["created"] else "finish"
            # Native front insertion reverses order, so process Assembly first.
            job["reorder"] = list(reversed(ROLES))
            return False
        role = job["remaining"][0]
        existing = find_workspace(role)
        if existing:
            job["remaining"].pop(0)
            return False
        if window.workspace != job["source_workspace"]:
            window.workspace = job["source_workspace"]
            return False
        job["remaining"].pop(0)
        old = {workspace.as_pointer() for workspace in bpy.data.workspaces}
        with bpy.context.temp_override(window=window):
            bpy.ops.workspace.duplicate()
        new = next(
            workspace for workspace in bpy.data.workspaces if workspace.as_pointer() not in old
        )
        new.name = role.title()
        new[OWNER_KEY] = OWNER
        new[ROLE_KEY] = role
        new["mechanical_cad_layout_version"] = 1
        new.use_pin_scene = False
        job["created"] = True
        job["new"] = new
        job["phase"] = "configure"
        return False
    if phase == "configure":
        new = job["new"]
        if window.workspace != new:
            window.workspace = new
            return False
        _configure_new(window, new, new.get(ROLE_KEY))
        job["phase"] = "panel"
        job["panel_attempts"] = 0
        return False
    if phase == "panel":
        job["panel_attempts"] += 1
        if _select_new_category(window) or job["panel_attempts"] >= 20:
            job["phase"] = "create"
        return False
    if phase == "reorder":
        if job["reorder"]:
            target = find_workspace(job["reorder"][0])
            if target is None:
                raise RuntimeError("A CAD workspace was removed during initial ordering")
            # The native operator uses the window's active workspace, not a
            # generic temp_override(workspace=...) member. Activate and verify on
            # a separate event-loop turn just like the existing setup phases.
            if window.workspace != target:
                window.workspace = target
                return False
            # Clear area/region so a previously hovered tab cannot override the
            # active workspace in Blender's native reorder operator.
            with bpy.context.temp_override(window=window, area=None, region=None):
                bpy.ops.workspace.reorder_to_front()
            job["reorder"].pop(0)
            return False
        job["phase"] = "finish"
        return False
    target = find_workspace(job["role"])
    if target is None:
        raise RuntimeError("The requested CAD workspace was removed during setup")
    if window.workspace != target:
        window.workspace = target
        return False
    _with_ready_context(job)
    return True


def _tick():
    global _LAST_ERROR
    for key, job in list(_JOBS.items()):
        try:
            done = _step(job)
        except Exception as exc:
            _LAST_ERROR = str(exc)
            print("Mechanical CAD workspace:", _LAST_ERROR)
            done = True
        if done and _JOBS.get(key) is job:
            _JOBS.pop(key, None)
    return 0.05 if _JOBS else None


def request_workspace(context, role="PART", on_ready=None):
    """Create missing tabs and enter role; callback receives fresh viewport context.

    A new request updates a pending destination without interrupting its native
    transition. Repeated entry reuses tabs without resetting layouts. This does not
    commit a draft: context handoff suspends it for explicit compatible resume.
    """
    global _LAST_ERROR
    role = role.upper()
    if role not in ROLES:
        raise ValueError(f"Unknown CAD workspace role: {role}")
    if not context.window:
        raise RuntimeError("CAD workspaces require a Blender window")
    if context.mode != "OBJECT":
        raise RuntimeError("Return to Object Mode before opening CAD")
    window = context.window
    key = window.as_pointer()
    if on_ready is None and key not in _JOBS and get_role(context) == role:
        return True  # selecting the current role again is not a context handoff
    _handoff_draft("Workspace changed", context)
    _LAST_ERROR = ""
    pending = _JOBS.get(key)
    if pending and pending["scene"] == context.scene:
        pending["role"] = role
        pending["callback"] = on_ready
    else:
        _JOBS[key] = {
            "window": window,
            "source_workspace": context.workspace,
            "scene": context.scene,
            "role": role,
            "remaining": list(ROLES),
            "phase": "create",
            "new": None,
            "created": False,
            "callback": on_ready,
            "ticks": 0,
        }
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.05)
    return True


request_role = request_workspace


def cancel_pending_setup():
    _JOBS.clear()
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)


@persistent
def _load_pre(_dummy):
    cancel_pending_setup()
    _handoff_draft("File loading")


def register():
    if _load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_load_pre)


def unregister():
    cancel_pending_setup()
    _handoff_draft("CAD disabled")
    set_draft_handlers()
    if _load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_load_pre)
