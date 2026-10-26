"""Component identity comes from an unambiguous current selection, never old UI state."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace as NS

import pytest


class DisplayObject(dict):
    __eq__ = object.__eq__
    __hash__ = object.__hash__

    def __init__(self, name, **tags):
        super().__init__(tags)
        self.name = name
        self.type = "MESH"
        self.selected = True
        self.visible = True
        self.hide_viewport = False
        self.hide_select = False

    def select_get(self, **kwargs):
        return self.selected

    def visible_get(self, **kwargs):
        return self.visible and not self.hide_viewport

    def hide_get(self, **kwargs):
        return not self.visible

    def as_pointer(self):
        return id(self)


class Objects(list):
    active = None

    def get(self, name):
        return next((obj for obj in self if obj.name == name), None)

    def __contains__(self, value):
        return any(obj.name == value if isinstance(value, str) else obj is value for obj in self)


@pytest.fixture
def host(monkeypatch):
    name = "component_context_tests"
    package = types.ModuleType(name)
    package.__path__ = [
        str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
    ]
    monkeypatch.setitem(sys.modules, name, package)
    display = types.ModuleType(name + ".assembly_display")
    for constant, suffix in (
        ("OWNER_KEY", "owner"),
        ("ASSEMBLY_KEY", "id"),
        ("DEFINITION_KEY", "definition"),
        ("INSTANCE_KEY", "instance"),
        ("FRAME_KEY", "frame"),
        ("ROLE_KEY", "role"),
    ):
        setattr(display, constant, "mechanical_cad_assembly_" + suffix)
    monkeypatch.setitem(sys.modules, display.__name__, display)
    calls, current = [], [True]

    def is_current(context, **kwargs):
        assert not kwargs.get("update", False), "Resolver cannot refresh/mutate display"
        calls.append(context)
        return current[0]

    state_module = types.ModuleType(name + ".assembly_state")
    state_module.display_is_current = is_current
    monkeypatch.setitem(sys.modules, state_module.__name__, state_module)
    monkeypatch.delitem(sys.modules, name + ".assembly_component_context", raising=False)
    module = importlib.import_module(name + ".assembly_component_context")
    data = {
        "id": "assembly",
        "instances": [
            {"id": "a", "part_id": "block", "name": "A"},
            {"id": "b", "part_id": "block", "name": "B"},
        ],
        "parts": [{"id": "block", "mate_frames": [{"id": "origin"}]}],
    }
    state = NS(owner_id="owner", selected_instance="b", document_json=json.dumps(data))

    def obj(instance="a", role="instance", name="Component"):
        result = DisplayObject(
            name,
            **{
                display.OWNER_KEY: "owner",
                display.ASSEMBLY_KEY: "assembly",
                display.DEFINITION_KEY: "block",
                display.INSTANCE_KEY: instance,
                display.FRAME_KEY: "" if role == "instance" else "origin",
                display.ROLE_KEY: role,
            },
        )
        result.type = "MESH" if role == "instance" else "EMPTY"
        return result

    active = obj()
    scene = NS(mechanical_cad_assembly=state, objects=Objects([active]))
    layer = NS(objects=Objects([active]))
    layer.objects.active = active
    window = NS(scene=scene, view_layer=layer)
    context = NS(
        scene=scene,
        window=window,
        view_layer=layer,
        active_object=active,
        selected_objects=[active],
        mode="OBJECT",
    )
    return NS(
        module=module,
        display=display,
        context=context,
        data=data,
        obj=obj,
        active=active,
        state=state,
        current=current,
        calls=calls,
    )


def resolve_unchanged(host):
    state = vars(host.state).copy()
    data = copy.deepcopy(host.data)
    selection = list(host.context.selected_objects)
    active = host.context.view_layer.objects.active
    objects = [(obj, dict(obj), vars(obj).copy()) for obj in host.context.scene.objects]
    result = host.module.selected_component(host.context, host.data)
    assert vars(host.state) == state and host.data == data
    assert (
        host.context.selected_objects == selection
        and host.context.view_layer.objects.active is active
    )
    for obj, tags, fields in objects:
        assert dict(obj) == tags and vars(obj) == fields
    return result


def test_selected_mesh_resolves_exact_instance_not_remembered_selection(host):
    assert resolve_unchanged(host) == host.data["instances"][0]
    assert host.calls == [host.context]


@pytest.mark.parametrize(
    "change",
    [
        "active-unselected",
        "selected-list-empty",
        "active-mismatch",
        "window-scene",
        "window-layer",
        "outside-scene",
        "outside-layer",
        "hidden",
        "hide-viewport",
        "hide-select",
        "edit-mode",
        "not-current",
        "no-window",
        "wrong-type",
        "frame-only",
        "foreign-owner",
        "foreign-assembly",
        "foreign-definition",
        "unknown-instance",
        "missing-instance",
        "missing-owner",
        "missing-assembly",
        "missing-definition",
        "wrong-role",
        "no-active",
        "empty-data",
    ],
)
def test_invalid_component_context_has_no_old_selection_fallback(host, change):
    c, o, d = host.context, host.active, host.display
    if change == "active-unselected":
        o.selected = False
    elif change == "selected-list-empty":
        c.selected_objects = []
    elif change == "active-mismatch":
        c.active_object = host.obj(instance="b")
    elif change == "window-scene":
        c.window.scene = object()
    elif change == "window-layer":
        c.window.view_layer = object()
    elif change == "outside-scene":
        c.scene.objects.clear()
    elif change == "outside-layer":
        c.view_layer.objects.clear()
    elif change == "hidden":
        o.visible = False
    elif change == "hide-viewport":
        o.hide_viewport = True
    elif change == "hide-select":
        o.hide_select = True
    elif change == "edit-mode":
        c.mode = "EDIT_MESH"
    elif change == "not-current":
        host.current[0] = False
    elif change == "no-window":
        c.window = None
    elif change == "wrong-type":
        o.type = "EMPTY"
    elif change == "frame-only":
        o[d.ROLE_KEY] = "frame"
        o[d.FRAME_KEY] = "origin"
        o.type = "EMPTY"
    elif change == "foreign-owner":
        o[d.OWNER_KEY] = "foreign"
    elif change == "foreign-assembly":
        o[d.ASSEMBLY_KEY] = "foreign"
    elif change == "foreign-definition":
        o[d.DEFINITION_KEY] = "foreign"
    elif change == "unknown-instance":
        o[d.INSTANCE_KEY] = "unknown"
    elif change.startswith("missing-"):
        key = {
            "instance": d.INSTANCE_KEY,
            "owner": d.OWNER_KEY,
            "assembly": d.ASSEMBLY_KEY,
            "definition": d.DEFINITION_KEY,
        }[change.removeprefix("missing-")]
        del o[key]
    elif change == "wrong-role":
        o[d.ROLE_KEY] = "foreign"
    elif change == "no-active":
        c.view_layer.objects.active = None
        c.active_object = None
    elif change == "empty-data":
        host.data["instances"] = []
    assert resolve_unchanged(host) is None


@pytest.mark.parametrize(
    "extra", ["second-component", "foreign-selected", "duplicate-tags", "bad-frame"]
)
def test_ambiguous_or_foreign_selection_refuses(host, extra):
    obj = host.obj(instance="b", name="Other")
    if extra == "foreign-selected":
        obj.clear()
    elif extra == "duplicate-tags":
        obj[host.display.INSTANCE_KEY] = "a"
        obj.selected = False
        host.current[0] = False  # Trusted display rejects duplicate role/instance/frame keys.
    elif extra == "bad-frame":
        obj = host.obj(role="frame", name="Bad helper")
        obj[host.display.FRAME_KEY] = "missing"
    host.context.scene.objects.append(obj)
    host.context.view_layer.objects.append(obj)
    if obj.selected:
        host.context.selected_objects.append(obj)
    assert resolve_unchanged(host) is None


def test_valid_owned_frame_helpers_can_coexist_with_one_component(host):
    for identifier in ("a", "b"):
        obj = host.obj(instance=identifier, role="frame", name="Frame " + identifier)
        host.context.scene.objects.append(obj)
        host.context.view_layer.objects.append(obj)
        host.context.selected_objects.append(obj)
    assert resolve_unchanged(host) == host.data["instances"][0]
