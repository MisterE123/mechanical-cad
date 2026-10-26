"""Native-free visual-owner and current-display getter boundary tests.

Blender resources, the display projection and final publication are synthetic
ports. Scene/window/history guards and the actual visual session stay live.
These tests neither mint backend authority nor claim native geometry/GUI proof;
tests/blender_visual_joint_smoke.py exercises real guarded native publication.
"""

import copy
import importlib
import itertools
import json
import sys
import types
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
NAMES = itertools.count()


class Host(types.SimpleNamespace):
    def as_pointer(self):
        return id(self)

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other


def inert(*_args, **_kwargs):
    return None


def fixture_response(assembly):
    """Deliberately synthetic display-only ports, never a guarded receipt."""
    placements = {
        name: {"xyz_mm": position, "wxyz": [1, 0, 0, 0]}
        for name, position in {
            "base": [0, 0, 0],
            "sector_a": [10, 10, 20],
            "sector_b": [25, 10, 20],
        }.items()
    }
    parts = [
        {
            **copy.deepcopy(part),
            "mesh": {
                "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "triangles": [[0, 1, 2]],
                "triangle_face_ids": [None],
            },
        }
        for part in assembly["parts"]
    ]
    return {
        "result": {
            "canonical_assembly": copy.deepcopy(assembly),
            "instances": copy.deepcopy(assembly["instances"]),
            "parts": parts,
        },
        "report": {"base_pose": {"status": "evaluated", "transforms": placements}},
    }


@pytest.fixture
def host(monkeypatch):
    name = "mcad_visual_joint_owner_tests_" + str(next(NAMES))
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
    bpy, props, btypes = (types.ModuleType(key) for key in ("bpy", "bpy.props", "bpy.types"))
    display, workspace = (types.ModuleType(key) for key in ("display", "workspace"))
    resource_events, publication_calls, validation_calls = [], [], []

    def add_resource(kind, *_args, **_kwargs):
        token = object()
        resource_events.append(("add", kind, token))
        return token

    def remove_resource(kind, token, *_args, **_kwargs):
        resource_events.append(("remove", kind, token))

    btypes.Operator = type("Operator", (), {"report": inert})
    btypes.SpaceView3D = Host(
        draw_handler_add=lambda *args: add_resource("draw", *args),
        draw_handler_remove=lambda token, *args: remove_resource("draw", token, *args),
    )
    for key in ("BoolProperty", "StringProperty", "FloatProperty", "EnumProperty"):
        setattr(props, key, lambda **kwargs: kwargs)
    bpy.types, bpy.props = btypes, props
    bpy.ops = Host(ed=Host(undo_push=inert))
    workspace.active_draft = lambda: False
    workspace.has_draft = lambda _context: False
    display.trusted_display = lambda *_args, **_kwargs: True
    display.owned_objects = lambda scene, _owner: scene.objects
    # Used only for instance picking, which these explicit-ID adapter tests do not fake.
    for field in ("OWNER_KEY", "INSTANCE_KEY", "ROLE_KEY", "DEFINITION_KEY", "ORIGIN_KEY"):
        setattr(display, field, field)
    with patch.dict(
        sys.modules,
        {
            name: package,
            "bpy": bpy,
            "bpy.props": props,
            "bpy.types": btypes,
            "bpy_extras": Host(view3d_utils=Host()),
            "mathutils": Host(Vector=tuple),
            name + ".assembly_display": display,
            name + ".assembly_source_preview_registry": Host(active=lambda: None),
            name + ".workspace": workspace,
        },
    ):
        owner = importlib.import_module(name + ".assembly_joint_viewport")
        importlib.import_module(name + ".sketch_session")
        importlib.import_module(name + ".staged_edit_store")
        modules = {
            key: value
            for key, value in sys.modules.items()
            if key == name or key.startswith(name + ".")
        }
    for key, value in modules.items():
        monkeypatch.setitem(sys.modules, key, value)
    state_api = owner.state_api
    selection_api = importlib.import_module(name + ".backend_selection")
    selected = selection_api.BackendSelection.capture(
        str(ROOT), sys.executable, generation=2, lifetime_id="visual-owner-test", environment={}
    )
    current = [selected]
    monkeypatch.setattr(state_api.backend_runtime, "capture", lambda _context: current[0])
    monkeypatch.setattr(
        state_api.backend_runtime, "configuration", lambda _context: (current[0], 0.1)
    )

    def assert_selection(expected, _context):
        expected.assert_current(current[0])
        return current[0]

    monkeypatch.setattr(state_api.backend_runtime, "assert_current", assert_selection)
    assembly = json.loads((ROOT / "examples/box_sector/assembly.mcad-assembly.json").read_text())
    fields = {key: "" for key in state_api._STATE_FIELDS}
    fields.update(
        owner_id="synthetic-owner",
        document_json=state_api._json(assembly),
        display_status="CURRENT",
        verification_status="CURRENT",
        status="READY",
    )
    storage = Host(**fields)
    scene = Host(
        mechanical_cad_assembly=storage,
        mechanical_cad=Host(document_json="unchanged working Part", sketch_draft_json=""),
        unit_settings=Host(scale_length=1),
        objects=[],
    )
    storage.id_data = scene
    region = Host(type="WINDOW", x=0, y=0, width=1000, height=800)
    area = Host(
        type="VIEW_3D",
        regions=[region],
        spaces=Host(active=Host(region_3d=Host())),
        tag_redraw=inert,
        header_text_set=inert,
    )
    layer = Host(objects=Host(active=None))
    work = Host()
    window = Host(scene=scene, view_layer=layer, workspace=work, screen=Host(areas=[area]))
    manager = Host(
        event_timer_add=lambda *args, **kwargs: add_resource("timer", *args, **kwargs),
        event_timer_remove=lambda token: remove_resource("timer", token),
        modal_handler_add=inert,
        windows=[window],
    )
    context = Host(
        scene=scene,
        window=window,
        view_layer=layer,
        workspace=work,
        area=area,
        region=region,
        region_data=area.spaces.active.region_3d,
        window_manager=manager,
        preferences=Host(system=Host(ui_scale=1)),
        selected_objects=[],
        mode="OBJECT",
    )
    timers = set()

    def register_timer(callback, **_kwargs):
        timers.add(callback)
        resource_events.append(("add", "watchdog", callback))

    def unregister_timer(callback):
        timers.remove(callback)
        resource_events.append(("remove", "watchdog", callback))

    bpy.app = Host(
        timers=Host(
            register=register_timer, unregister=unregister_timer, is_registered=timers.__contains__
        )
    )
    bpy.context, bpy.data = context, Host(scenes=[scene], objects=[])

    class Mesh(dict):
        type = "MESH"

    scene.objects = [
        Mesh({display.INSTANCE_KEY: row["id"], display.ROLE_KEY: "instance"})
        for row in assembly["instances"]
    ]
    response = fixture_response(assembly)
    sentinel_evidence, sentinel_token = object(), object()
    runtime = {
        "owner_id": storage.owner_id,
        "display_document_json": storage.document_json,
        "display_response": {"must_not": "be used instead of evidence"},
        "display_evidence": sentinel_evidence,
        "display_owner_token": sentinel_token,
        "report_binding": None,
    }
    state_api._RUNTIME[scene.as_pointer()] = runtime

    def validate(evidence, token, current_selection, **kwargs):
        validation_calls.append((evidence, token, current_selection(), kwargs))
        return copy.deepcopy(response)

    display._validated = validate

    def publish(_context, candidate, expected_json=None):
        publication_calls.append((copy.deepcopy(candidate), expected_json))
        storage.document_json = state_api._json(candidate)
        return copy.deepcopy(response)

    monkeypatch.setattr(state_api, "commit_candidate", publish)
    result = Host(
        owner=owner,
        state_api=state_api,
        display=display,
        bpy=bpy,
        context=context,
        storage=storage,
        assembly=assembly,
        current=current,
        response=response,
        runtime=runtime,
        publication_calls=publication_calls,
        validation_calls=validation_calls,
        resource_events=resource_events,
    )
    yield result
    owner.cancel_active("Pure fixture cleanup")
    state_api.clear_runtime()


def begin(host, joint_id="slide_a"):
    session = host.owner.JointViewportSession(host.context, joint_id=joint_id)
    session.start()
    return session


def test_getter_reads_live_evidence_port_never_saved_projection(host):
    host.storage.report_json = '{"saved": "untrusted"}'
    before = vars(host.storage).copy()
    value = host.state_api.current_display_response(host.context)
    assert value == host.response
    assert host.validation_calls == [
        (
            host.runtime["display_evidence"],
            host.runtime["display_owner_token"],
            host.current[0],
            {},
        )
    ]
    assert vars(host.storage) == before and host.publication_calls == []
    value["report"]["base_pose"]["transforms"].clear()
    assert host.response["report"]["base_pose"]["transforms"]


def test_getter_rejects_untrusted_display_before_reading_evidence(host, monkeypatch):
    monkeypatch.setattr(host.state_api, "display_is_current", lambda _context: False)
    with pytest.raises(host.owner.BridgeError, match="Replay"):
        host.state_api.current_display_response(host.context)
    assert host.validation_calls == [] and host.publication_calls == []


def test_getter_does_not_fall_back_when_live_evidence_validation_rejects(host, monkeypatch):
    def reject(*_args, **_kwargs):
        raise host.owner.BridgeError("Controlled evidence revocation")

    monkeypatch.setattr(host.display, "_validated", reject)
    with pytest.raises(host.owner.BridgeError, match="revocation"):
        host.state_api.current_display_response(host.context)
    assert host.publication_calls == []


@pytest.mark.parametrize("change", ["runtime", "owner", "document"])
def test_getter_rejects_context_swap_during_validated_read(host, monkeypatch, change):
    def changed(*_args, **_kwargs):
        if change == "runtime":
            host.state_api._RUNTIME[host.context.scene.as_pointer()] = dict(host.runtime)
        elif change == "owner":
            host.storage.owner_id = "new-owner"
        else:
            host.storage.document_json += " "
        return copy.deepcopy(host.response)

    monkeypatch.setattr(host.display, "_validated", changed)
    with pytest.raises(host.owner.BridgeError, match="changed"):
        host.state_api.current_display_response(host.context)
    assert host.publication_calls == []


def test_parent_child_selection_and_preview_do_not_publish(host):
    original = host.storage.document_json
    session = begin(host, joint_id="")
    session.choose_instance(host.context, "base")
    session.choose_instance(host.context, "sector_a")
    assert session.draft.joint_id == "slide_a"
    with pytest.raises(Exception, match="discard motion"):
        session.set_kind(host.context, "fixed")
    session.clear_motion(host.context)
    session.set_kind(host.context, "fixed")
    assert session.preview_transforms["sector_a"]["xyz_mm"] == [10, 10, 10]
    session.set_kind(host.context, "slider")
    session.set_distance(host.context, 12)
    session.translate_connector(host.context, "child", "X", 1)
    assert session.preview_transforms["sector_a"]["xyz_mm"] == [9, 10, 22]
    assert session.preview_transforms["sector_b"]["xyz_mm"] == [25, 10, 20]
    assert host.storage.document_json == original and host.publication_calls == []
    assert host.owner.active(host.context) is session


def test_constructor_rejects_history_change_after_display_capture(host, monkeypatch):
    getter = host.state_api.current_display_response

    def change_history(context):
        response = getter(context)
        host.state_api.invalidate(context.scene, "History changed during visual capture")
        return response

    monkeypatch.setattr(host.state_api, "current_display_response", change_history)
    with pytest.raises(host.owner.BridgeError, match="history changed"):
        host.owner.JointViewportSession(host.context, joint_id="slide_a")
    assert host.owner.active() is None
    assert host.resource_events == [] and host.publication_calls == []


@pytest.mark.parametrize("change", ["scene", "window", "view_layer", "backend", "history"])
def test_stale_owner_rejects_apply_before_publication(host, change):
    session = begin(host)
    session.set_distance(host.context, 12)
    original = host.storage.document_json
    if change == "scene":
        host.context.scene = Host(**vars(host.context.scene))
    elif change == "window":
        host.context.window = Host(**vars(host.context.window))
    elif change == "view_layer":
        host.context.view_layer = Host(objects=Host(active=None))
    elif change == "backend":
        host.current[0] = replace(host.current[0], generation=3)
    else:
        host.state_api.invalidate(host.context.scene, "Synthetic history invalidation")
    assert not session.apply(host.context)
    assert host.storage.document_json == original and host.publication_calls == []
    assert host.owner.active() is None


def test_failed_current_apply_keeps_draft_and_exact_accepted_bytes(host, monkeypatch):
    session = begin(host)
    session.set_distance(host.context, 12)
    original = host.storage.document_json

    def reject(_context, candidate, expected_json=None):
        host.publication_calls.append((copy.deepcopy(candidate), expected_json))
        raise host.owner.BridgeError("Controlled native boundary rejection")

    monkeypatch.setattr(host.state_api, "commit_candidate", reject)
    assert not session.apply(host.context)
    assert host.storage.document_json == original
    assert host.owner.active(host.context) is session
    assert len(host.publication_calls) == 1
    candidate, expected = host.publication_calls[0]
    assert expected == original and candidate["joints"][0]["coordinate"] == 12
    session.set_distance(host.context, 14)
    assert session.draft.coordinate == 14


def test_successful_apply_uses_single_transaction_and_retires_resources(host):
    session = begin(host)
    original = host.storage.document_json
    session.set_distance(host.context, 12)
    assert session.apply(host.context)
    assert host.owner.active() is None
    assert len(host.publication_calls) == 1
    candidate, expected = host.publication_calls[0]
    assert expected == original
    assert candidate["joints"][0]["id"] == "slide_a"
    assert candidate["joints"][1] == host.assembly["joints"][1]
    assert not session.apply(host.context)
    assert len(host.publication_calls) == 1
    assert_resources_released(host)


def assert_resources_released(host):
    created = {(kind, token) for action, kind, token in host.resource_events if action == "add"}
    removed = [(kind, token) for action, kind, token in host.resource_events if action == "remove"]
    assert created and set(removed) == created and len(removed) == len(created)


def test_cancel_and_lifecycle_cleanup_are_idempotent_without_canonical_changes(host):
    session = begin(host)
    before = host.storage.document_json
    session.set_distance(host.context, 14)
    session.select_connector("child")
    session.roll_connector(host.context)
    host.owner.cancel_active("File/history/unregister lifecycle")
    host.owner.cancel_active("Repeated lifecycle cleanup")
    session.cancel("Repeated Cancel")
    assert host.owner.active() is None
    assert host.storage.document_json == before and host.publication_calls == []
    assert_resources_released(host)


def test_watchdog_retires_resources_when_original_window_closes(host):
    session = begin(host)
    before = host.storage.document_json
    watchdog = session.watchdog
    host.context.window_manager.windows.clear()
    assert watchdog() is None
    assert not session.alive and host.owner.active() is None
    assert host.storage.document_json == before and host.publication_calls == []
    assert_resources_released(host)


@pytest.mark.parametrize(
    ("mode", "raw"),
    [("field", "12.5"), ("field", ""), ("field", "1e-"), ("drag", "12.5")],
    ids=["valid-slide", "empty-slide", "invalid-slide", "typed-connector-drag"],
)
def test_modal_visible_cancel_discards_pending_numeric_input(host, mode, raw):
    """Real modal dispatch with synthetic events; no mouse/GUI usability claim."""
    session = begin(host)
    operator = host.owner.MCAD_OT_assembly_visual_joint()
    operator.owner = session
    canonical = host.storage.document_json
    display = [dict(obj) for obj in host.context.scene.objects]
    response = copy.deepcopy(host.response)

    def event(kind, point=(600, 400), text=""):
        return Host(
            type=kind,
            value="PRESS",
            ctrl=False,
            alt=False,
            unicode=text,
            ascii=text,
            mouse_x=point[0] + session.region.x,
            mouse_y=point[1] + session.region.y,
        )

    def button_center(action):
        button = next(item for item in session.panel_layout().buttons if item.action == action)
        assert button.enabled
        x, y, right, top = button.bounds
        return (x + right) / 2, (y + top) / 2

    if mode == "field":
        assert operator.modal(host.context, event("LEFTMOUSE", button_center("distance"))) == {
            "RUNNING_MODAL"
        }
        assert session.field_active
    else:
        assert operator.modal(host.context, event("X")) == {"RUNNING_MODAL"}
        assert session.drag is not None
    for character in raw:
        assert operator.modal(host.context, event("TEXTINPUT", text=character)) == {"RUNNING_MODAL"}
    assert (session.field_raw if mode == "field" else session.drag["raw"]) == raw

    assert operator.modal(host.context, event("LEFTMOUSE", button_center("cancel"))) == {
        "CANCELLED"
    }
    assert not session.alive and host.owner.active() is None
    assert session.drag is None and not session.field_active and session.ghost_positions == ()
    assert host.storage.document_json == canonical and host.publication_calls == []
    assert [dict(obj) for obj in host.context.scene.objects] == display
    assert host.response == response
    assert_resources_released(host)


class RayVector(tuple):
    """Only the vector arithmetic used by the synthetic picker boundary."""

    def __sub__(self, other):
        return RayVector(a - b for a, b in zip(self, other, strict=True))

    def dot(self, other):
        return sum(a * b for a, b in zip(self, other, strict=True))

    @property
    def length(self):
        return self.dot(self) ** 0.5

    def normalized(self):
        return RayVector(value / self.length for value in self)


class RayMatrix:
    """Diagonal affine matrix sufficient to expose local/world distance errors."""

    def __init__(self, scale=(1, 1, 1), translation=(0, 0, 0)):
        self.scale, self.translation = scale, translation

    def copy(self):
        return RayMatrix(self.scale, self.translation)

    def __matmul__(self, vector):
        return RayVector(
            a * b + c for a, b, c in zip(self.scale, vector, self.translation, strict=True)
        )

    def inverted(self):
        if not all(self.scale):
            raise ValueError("Synthetic singular matrix")
        return RayMatrix(
            tuple(1 / value for value in self.scale),
            tuple(
                -value / scale for value, scale in zip(self.translation, self.scale, strict=True)
            ),
        )

    def to_3x3(self):
        return RayMatrix(self.scale)


def picker_host(host, monkeypatch, specifications):
    """Fake visibility/evaluated-ray ports; execute the real picker algorithm."""
    visibility, rays, evaluations = [], [], []
    shared_mesh = object()

    class Objects(list):
        active = None

    class Mesh(dict):
        type = "MESH"
        data = shared_mesh

        def __init__(self, identifier, *, visible=True, hit=True, scale=1, z=0, owned=True):
            super().__init__(
                {
                    host.display.INSTANCE_KEY: identifier,
                    host.display.OWNER_KEY: "synthetic-owner" if owned else "foreign",
                    host.display.ROLE_KEY: "instance",
                }
            )
            self.name = identifier
            self.original = self
            self.matrix_world = RayMatrix((scale, scale, scale), (0, 0, z))
            self.visible, self.hit = visible, hit

        def visible_get(self, **kwargs):
            visibility.append((self.name, kwargs))
            return self.visible

        def evaluated_get(self, depsgraph):
            evaluations.append((self.name, depsgraph))
            return self

        def ray_cast(self, origin, direction, *, depsgraph):
            rays.append((self.name, tuple(origin), tuple(direction), depsgraph))
            return self.hit, RayVector((0, 0, 0)), RayVector((0, 0, 1)), 0

    objects = Objects(Mesh(**specification) for specification in specifications)
    host.context.scene.objects = objects
    host.context.view_layer.objects = objects
    depsgraph = Host(object_instances=[])
    host.context.evaluated_depsgraph_get = lambda: depsgraph
    monkeypatch.setattr(
        host.display,
        "owned_objects",
        lambda scene, owner: [obj for obj in scene.objects if obj[host.display.OWNER_KEY] == owner],
    )
    monkeypatch.setattr(
        host.owner.view3d_utils,
        "region_2d_to_origin_3d",
        lambda *_args: RayVector((0, 0, 10)),
        raising=False,
    )
    monkeypatch.setattr(
        host.owner.view3d_utils,
        "region_2d_to_vector_3d",
        lambda *_args: RayVector((0, 0, -1)),
        raising=False,
    )
    return Host(
        objects=objects,
        visibility=visibility,
        rays=rays,
        evaluations=evaluations,
        depsgraph=depsgraph,
    )


@pytest.mark.parametrize("case", ["owned", "local_hidden_foreign", "visible_foreign", "no_hit"])
def test_picker_respects_captured_viewport_visibility_and_foreign_occlusion(
    host, monkeypatch, case
):
    specs = [{"identifier": "base", "hit": case != "no_hit"}]
    if "foreign" in case:
        specs.insert(
            0,
            {
                "identifier": "Cube",
                "z": 5,
                "owned": False,
                "visible": case == "visible_foreign",
            },
        )
    picker = picker_host(host, monkeypatch, specs)
    session = begin(host, joint_id="")
    canonical = host.storage.document_json
    original_objects = [(dict(obj), obj.visible) for obj in picker.objects]
    if case in {"visible_foreign", "no_hit"}:
        with pytest.raises(host.owner.BridgeError):
            session.pick_instance(host.context, (50, 50))
    else:
        assert session.pick_instance(host.context, (50, 50)) == "base"
    assert all(
        kwargs
        == {
            "view_layer": host.context.view_layer,
            "viewport": host.context.area.spaces.active,
        }
        for _name, kwargs in picker.visibility
    )
    assert picker.visibility
    if case == "local_hidden_foreign":
        assert all(name != "Cube" for name, *_args in picker.rays)
        assert all(name != "Cube" for name, _depsgraph in picker.evaluations)
    assert [(dict(obj), obj.visible) for obj in picker.objects] == original_objects
    assert host.storage.document_json == canonical and host.publication_calls == []
    assert picker.objects.active is None


def test_picker_shared_transformed_instances_choose_positive_world_distance(host, monkeypatch):
    picker = picker_host(
        host,
        monkeypatch,
        [
            {"identifier": "sector_b", "scale": 100, "z": 4},
            {"identifier": "sector_a", "scale": 0.1, "z": 8},
            {"identifier": "base", "z": 12},  # Synthetic hit lies behind the world ray.
        ],
    )
    session = begin(host, joint_id="")
    assert picker.objects[0].data is picker.objects[1].data
    assert session.pick_instance(host.context, (50, 50)) == "sector_a"
    by_name = {name: (origin, direction) for name, origin, direction, _graph in picker.rays}
    assert by_name["sector_b"][0] == pytest.approx((0, 0, 0.06))
    assert by_name["sector_a"][0] == pytest.approx((0, 0, 20))
    assert all(direction == (0, 0, -1) for _origin, direction in by_name.values())
    assert host.publication_calls == [] and picker.objects.active is None


@pytest.mark.parametrize("case", ["nonmesh", "generated", "singular"])
def test_picker_fails_closed_for_unsupported_visible_surfaces(host, monkeypatch, case):
    picker = picker_host(host, monkeypatch, [{"identifier": "base"}])
    session = begin(host, joint_id="")
    mesh = picker.objects[0]
    if case == "nonmesh":
        mesh.type = "CURVE"
        reason = "visible non-mesh"
    elif case == "generated":
        picker.depsgraph.object_instances = [Host(is_instance=True, parent=Host(original=mesh))]
        reason = "Visible generated"
    else:
        mesh.matrix_world = RayMatrix((0, 1, 1))
        reason = "could not be tested safely"
    with pytest.raises(host.owner.BridgeError, match=reason):
        session.pick_instance(host.context, (50, 50))
    assert host.publication_calls == [] and picker.objects.active is None


def test_visual_revolute_degrees_reset_units_and_commit(host):
    session = begin(host)
    session.clear_motion(host.context)
    session.set_kind(host.context, "revolute")
    assert session.draft.coordinate == 0 and session.draft.limits is None
    session.set_distance(host.context, 90)
    assert session.draft.coordinate == pytest.approx(1.5707963267948966)
    panel = session.panel_layout()
    assert next(b for b in panel.buttons if b.action == "distance").label == "Angle: 90 °"
    session.click_action(host.context, "plus")
    assert session.draft.coordinate == pytest.approx(1.5882496193148399)
    assert host.publication_calls == []
    assert session.apply(host.context)
    candidate = host.publication_calls[0][0]
    joint = next(j for j in candidate["joints"] if j["id"] == "slide_a")
    assert joint["kind"] == "revolute"
    assert joint["coordinate"] == pytest.approx(1.5882496193148399)


def test_surface_mode_is_explicit_and_origin_reset_stays_transient(host):
    session = begin(host)
    session.click_action(host.context, "surface")
    assert session.surface_pick
    assert "not persistent face attachment" in session.hint
    session.select_connector("child")
    assert not session.surface_pick
    session.translate_connector(host.context, "child", "X", 5)
    session.click_action(host.context, "origin")
    assert session.draft.child_frame == {"xyz_mm": [0.0, 0.0, 0.0], "wxyz": [1.0, 0.0, 0.0, 0.0]}
    assert host.publication_calls == []


def test_joint_preview_uses_face_boundaries_not_tessellation_diagonals(host):
    session = begin(host)
    for part in session.parts.values():
        part["mesh"] = {
            "vertices": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
            "triangles": [[0, 1, 2], [0, 2, 3]],
            "triangle_face_ids": ["plane", "plane"],
        }
    session._prepare_edges()
    assert all(len(points) == 8 for points in session.ghost_edges.values())
    session.refresh_preview()
    assert "not checked" in session.message.lower()


def test_source_update_owner_excludes_joint_and_motion_before_other_work(host, monkeypatch):
    source_owner = sys.modules[host.owner.__package__ + ".assembly_source_preview_registry"]
    monkeypatch.setattr(source_owner, "active", lambda: object())
    for owner_type in (host.owner.JointViewportSession, host.owner.MotionViewportSession):
        with pytest.raises(host.owner.BridgeError, match="source update preview"):
            owner_type(host.context, "slide_a")
    assert not host.resource_events and not host.publication_calls
