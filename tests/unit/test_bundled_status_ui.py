"""Actual presentation function bodies with fake layouts, never native work or RNA."""

import ast
import builtins
import importlib.util
import sys
import textwrap
import threading
import types
from pathlib import Path
from textwrap import wrap
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender"


def functions(module, names, namespace):
    tree = ast.parse((ROOT / (module + ".py")).read_bytes())
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in body} == set(names)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(ROOT / module), "exec"), namespace)
    return types.SimpleNamespace(**{n: namespace[n] for n in names})


def draw_method(module, cls, namespace):
    tree = ast.parse((ROOT / (module + ".py")).read_bytes())
    owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    draw = next(n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == "draw")
    # Execute the real body with a bounded import port for the independent
    # recovery-settings renderer. Never import Blender or perform recovery IO.
    def import_port(name, globals=None, locals=None, fromlist=(), level=0):
        assert (name, fromlist, level) == ("", ("local_recovery",), 1)
        return types.SimpleNamespace(
            local_recovery=types.SimpleNamespace(draw_configuration=lambda *_: None)
        )

    namespace["__name__"] = "mcad_status_ui_ports." + module
    namespace["__package__"] = "mcad_status_ui_ports"
    namespace["__builtins__"] = {
        **namespace.get("__builtins__", builtins.__dict__), "__import__": import_port
    }
    exec(compile(ast.Module(body=[draw], type_ignores=[]), str(ROOT / module), "exec"), namespace)
    return namespace["draw"]


@pytest.fixture
def lease():
    name = "mcad_status_ui_lease"
    spec = importlib.util.spec_from_file_location(name, ROOT / "execution_lease.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(name, None)


class Layout:
    def __init__(self, events=None):
        self.events = [] if events is None else events
        self.enabled = True
        self.alert = False

    def label(self, **values):
        self.events.append(("label", values))

    def box(self):
        return Layout(self.events)

    def row(self, **kwargs):
        row = Layout(self.events)
        self.events.append(("row", row))
        return row

    def prop(self, obj, key, **kwargs):
        self.events.append(("prop", key))

    def operator(self, name, **kwargs):
        self.events.append(("operator", name, kwargs, self.enabled))
        return types.SimpleNamespace()

    def menu(self, *args, **kwargs):
        self.events.append(("menu", args))


def forbidden(*args, **kwargs):
    raise AssertionError("Drawing must not poll, mutate, inspect files or launch work")


def adapter(module, lease, diagnostic):
    job = types.SimpleNamespace(cleanup_diagnostic=diagnostic, poll=forbidden, result=forbidden)
    pending = types.SimpleNamespace(_job=job, _retired="cancelled", _error="Old cancellation")
    active = {123: pending}
    namespace = {
        "_main_thread": lambda: None,
        "_ACTIVE": active,
        "execution_lease": lease,
        "_cleanup_diagnostic": forbidden,
        "status": forbidden,
        "reap": forbidden,
        "cancel": forbidden,
    }
    result = functions(module, {"cleanup_message"}, namespace)
    return result, pending, active


def ui_context(width=582, scale=1.0):
    return types.SimpleNamespace(
        region=types.SimpleNamespace(width=width),
        preferences=types.SimpleNamespace(system=types.SimpleNamespace(ui_scale=scale)),
        scene=object(),
    )


def panel_wrap():
    return functions("help_ui", {"_panel_wrap"}, {"textwrap": textwrap})._panel_wrap


def renderer(lease, sketch, assembly, context=None):
    draw = functions(
        "assembly_job_ui",
        {"draw_backend_failure"},
        {
            "execution_lease": lease,
            "sketch_pending": sketch,
            "assembly_pending": assembly,
            "_panel_wrap": panel_wrap(),
        },
    ).draw_backend_failure
    return lambda layout: draw(layout, context or ui_context())


@pytest.mark.parametrize("module", ["sketch_pending", "assembly_pending"])
@pytest.mark.parametrize("diagnostic", ["", None, False, {}, 1])
def test_normal_or_non_string_status_is_not_cleanup_failure(lease, module, diagnostic):
    owner, pending, active = adapter(module, lease, diagnostic)
    assert owner.cleanup_message() == ""
    assert active == {123: pending} and pending._error == "Old cancellation"


@pytest.mark.parametrize("module", ["sketch_pending", "assembly_pending"])
@pytest.mark.parametrize(
    "diagnostic",
    ["cleanup uncertain", "secret/path " * 10000, "<script>raw</script>"],
    ids=["cleanup-uncertain", "oversized-private-path", "markup"],
)
def test_orphaned_diagnostic_is_normalized_and_repeated_draw_is_readonly(lease, module, diagnostic):
    owner, pending, active = adapter(module, lease, diagnostic)
    idle = types.SimpleNamespace(cleanup_message=lambda: "")
    render = renderer(
        lease,
        owner if module == "sketch_pending" else idle,
        owner if module == "assembly_pending" else idle,
    )
    original = (id(pending), id(pending._job), dict(pending.__dict__), dict(active))
    for _ in range(12):
        layout = Layout()
        assert render(layout)
        texts = [e[1]["text"] for e in layout.events if e[0] == "label"]
        assert texts == ["Native operations blocked", *wrap(lease.QUARANTINE_MESSAGE, 72)]
        assert diagnostic not in " ".join(texts)
        assert (id(pending), id(pending._job), dict(pending.__dict__), dict(active)) == original
    assert lease._TOKEN is None and lease._QUARANTINE is None


def test_string_subclass_cannot_supply_display_diagnostic(lease):
    class Text(str):
        pass

    owner, _, _ = adapter("sketch_pending", lease, Text("uncertain"))
    assert owner.cleanup_message() == ""


def test_sync_quarantine_draw_preserves_exact_owner_and_token(lease):
    token = lease.try_acquire()
    original = object()
    with lease.synchronous(token):
        assert lease.bind_transport() == (token, False)
        assert lease.quarantine(token, original)
    idle = types.SimpleNamespace(cleanup_message=forbidden)
    render = renderer(lease, idle, idle)
    for _ in range(12):
        assert render(Layout())
        assert lease._QUARANTINE == (token, original)
        assert lease._TOKEN is token and lease._BOUND_TOKEN is token
        assert not lease.release(token) and lease.try_acquire() is None


def test_ordinary_busy_has_no_restart_banner(lease):
    token = lease.try_acquire()
    idle = types.SimpleNamespace(cleanup_message=lambda: "")
    layout = Layout()
    assert not renderer(lease, idle, idle)(layout)
    assert layout.events == [] and lease.is_busy()
    assert lease.release(token)


@pytest.mark.parametrize("module", ["sketch_pending", "assembly_pending"])
def test_cleanup_query_retains_main_thread_guard(lease, module):
    def main_thread():
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("main thread required")

    owner = functions(
        module,
        {"cleanup_message"},
        {"_main_thread": main_thread, "_ACTIVE": {}, "execution_lease": lease},
    )
    errors = []

    def run():
        try:
            owner.cleanup_message()
        except RuntimeError as exc:
            errors.append(str(exc))

    worker = threading.Thread(target=run)
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive() and errors == ["main thread required"]


@pytest.mark.parametrize("bundled", [False, True])
def test_preferences_shows_blocker_without_ready_checkmark_or_manual_bundle_paths(bundled):
    calls = []
    namespace = {
        "backend_runtime": types.SimpleNamespace(
            bundled_mode=lambda: bundled, bundle_status=lambda: ("ready", "Bundled backend ready.")
        ),
        "assembly_job_ui": types.SimpleNamespace(
            draw_backend_failure=lambda layout, context: calls.append("failure") or True
        ),
        "wrap": wrap,
    }
    layout = Layout()
    draw_method("properties", "MCAD_Preferences", namespace)(
        types.SimpleNamespace(layout=layout), None
    )
    assert calls == ["failure"]
    assert not any(e[0] == "label" and e[1].get("icon") == "CHECKMARK" for e in layout.events)
    props = [e[1] for e in layout.events if e[0] == "prop"]
    assert props == ([] if bundled else ["project_root", "python_executable"]) + [
        "timeout_seconds",
        "linear_deflection",
    ]
    if bundled:
        assert any(
            e[0] == "label" and "operations are blocked" in e[1]["text"] for e in layout.events
        )


@pytest.mark.parametrize("bundled", [False, True])
def test_preferences_retains_exact_copyright_acknowledgements_without_setup_or_io(bundled):
    namespace = {
        "backend_runtime": types.SimpleNamespace(
            bundled_mode=lambda: bundled, bundle_status=lambda: ("ready", "Bundled backend ready.")
        ),
        "assembly_job_ui": types.SimpleNamespace(draw_backend_failure=lambda *_: False),
        "wrap": wrap,
        "open": forbidden,
        "__builtins__": {"open": forbidden},
    }
    layout = Layout()
    draw_method("properties", "MCAD_Preferences", namespace)(
        types.SimpleNamespace(layout=layout), None
    )
    text = " ".join(event[1]["text"] for event in layout.events if event[0] == "label")
    assert "Copyright (c) 2026 Mechanical CAD contributors. GPL-3.0-or-later." in text
    assert (
        "contains paintlib code. paintlib is copyright (c) 1996-2002 "
        "Ulrich von Zadow and other contributors."
    ) in text
    assert "FreeImage" in text and "Open CASCADE Technology (LGPL-2.1 + exception)" in text
    assert "copyright OPEN CASCADE SAS and contributors; see licenses/occt/" in text
    assert "Copyright (C) 2008-2018 LibRaw LLC; LGPL-2.1" in text
    assert "MATERIALS.md, licenses/ and sources/ in the ZIP" in text
    assert not any(event[0] in {"operator", "menu"} for event in layout.events)
    assert [event[1] for event in layout.events if event[0] == "prop"] == (
        [] if bundled else ["project_root", "python_executable"]
    ) + ["timeout_seconds", "linear_deflection"]


@pytest.mark.parametrize("bundled", [False, True])
@pytest.mark.parametrize("setup_state", ["preparing", "ready"])
def test_empty_main_panel_uses_mode_correct_help_before_return(bundled, setup_state):
    calls = []
    state = types.SimpleNamespace(sketch_notice="", last_action_error="", document_json="")
    namespace = {
        "assembly_job_ui": types.SimpleNamespace(
            draw_backend_failure=lambda layout, context: calls.append("failure") or True
        ),
        "backend_runtime": types.SimpleNamespace(
            bundled_mode=lambda: bundled,
            bundle_status=lambda: (
                setup_state,
                "Preparing the bundled backend offline…"
                if setup_state == "preparing"
                else "Bundled backend ready.",
            ),
        ),
        "_state": lambda context: state,
        "_panel_wrap": lambda context, text: wrap(text, 72),
        "_help_button": lambda layout, topic, *args: calls.append(topic),
        "draw_suspended_draft": lambda *args: None,
    }
    layout = Layout()
    draw_method("panels", "MCAD_PT_main", namespace)(types.SimpleNamespace(layout=layout), None)
    assert calls[0] == "failure"
    assert ("setup.bundled" if bundled else "setup.backend") in calls
    texts = " ".join(e[1]["text"] for e in layout.events if e[0] == "label")
    assert ("external Python path" in texts) is not bundled
    assert ("Preparing the bundled backend" in texts) is (bundled and setup_state == "preparing")
    if bundled and setup_state == "ready":
        assert "operations are blocked" in texts and "Bundled backend ready" not in texts


@pytest.mark.parametrize("role", ["SKETCH", "PART", "ASSEMBLY"])
def test_workspace_history_draws_failure_before_every_empty_early_return(role):
    calls = []
    namespace = {
        "workspace": types.SimpleNamespace(
            get_role=lambda context: role, active_draft=lambda context: None
        ),
        "assembly_job_ui": types.SimpleNamespace(
            draw_backend_failure=lambda layout, context: calls.append("failure")
        ),
        "assembly_ui": types.SimpleNamespace(
            draw_assembly_history=lambda *args: calls.append("assembly")
        ),
        "workspace_view": types.SimpleNamespace(draw_focus=lambda *_: None),
        "draw_suspended_draft": lambda *args: calls.append("draft"),
    }
    context = types.SimpleNamespace(
        scene=types.SimpleNamespace(mechanical_cad=types.SimpleNamespace(document_json=""))
    )
    draw_method("workspace_ui", "MCAD_PT_workspace_history", namespace)(
        types.SimpleNamespace(layout=Layout()), context
    )
    assert calls[:2] == ["failure", "draft"]
    assert ("assembly" in calls) is (role == "ASSEMBLY")


def test_assembly_pending_display_exposes_restart_and_disables_futile_cancel(lease):
    details = {
        "state": "cancelling",
        "pairs_per_pose": 1,
        "pose_count": 1,
        "elapsed_seconds": 1.0,
        "message": lease.QUARANTINE_MESSAGE,
    }
    namespace = {
        "assembly_pending": types.SimpleNamespace(status=lambda scene: details),
        "execution_lease": lease,
        "_panel_wrap": panel_wrap(),
    }
    draw = functions("assembly_job_ui", {"draw_pending"}, namespace).draw_pending
    layout = Layout()
    assert draw(layout, ui_context())
    assert any(e[0] == "label" and "restart Blender" in e[1]["text"] for e in layout.events)
    assert [e[3] for e in layout.events if e[0] == "operator"] == [False]
    details["message"] = ""
    normal = Layout()
    assert draw(normal, ui_context())
    assert [e[3] for e in normal.events if e[0] == "operator"] == [True]


def test_standalone_help_is_distinct_and_contains_no_setup_instructions():
    # Help is split into pure sibling modules; use a package rather than execute
    # its text with no relative-import context. Restore the temporary imports.
    package = types.ModuleType("mcad_status_help_tests")
    package.__path__ = [str(ROOT)]
    with patch.dict(sys.modules, {package.__name__: package}):
        topics = importlib.import_module(package.__name__ + ".help_topics").HELP_TOPICS
    help_text = " ".join(topics["setup.bundled"][1])
    assert "automatic offline preparation" in help_text
    assert "no Project Root or Python path is required" in help_text
    assert "restart Blender" in help_text
    assert "set Project Root" not in help_text
    assert "set Project Root" in " ".join(topics["setup.backend"][1])


@pytest.mark.parametrize(
    "width, scale", [(140, 2.0), (300, 0.75), (300, 1.0), (300, 2.0), (600, 1.0)]
)
def test_restart_guidance_wraps_at_actual_sidebar_width_and_scale(lease, width, scale):
    owner, _, _ = adapter("sketch_pending", lease, "late orphaned cleanup")
    idle = types.SimpleNamespace(cleanup_message=lambda: "")
    context = ui_context(width, scale)
    layout = Layout()
    assert renderer(lease, owner, idle, context)(layout)
    texts = [e[1]["text"] for e in layout.events if e[0] == "label"][1:]
    character_width = max(12, min(80, int((width - 42) / (7.5 * max(scale, 0.5)))))
    assert all(len(line) <= character_width for line in texts)
    assert " ".join(texts) == lease.QUARANTINE_MESSAGE
    assert "Save your work and restart Blender" in " ".join(texts)


@pytest.mark.parametrize("source", [False, True])
def test_preview_pending_uses_purpose_specific_title_and_cancel_without_mutation(lease, source):
    details = {
        "state": "running", "preview": True, "source_preview": source,
        "elapsed_seconds": 2.5, "message": "",
    }
    before = details.copy()
    namespace = {
        "assembly_pending": types.SimpleNamespace(status=lambda scene: details),
        "execution_lease": lease,
        "_panel_wrap": panel_wrap(),
    }
    draw = functions("assembly_job_ui", {"draw_pending"}, namespace).draw_pending
    layout = Layout()
    assert draw(layout, ui_context())
    labels = [e[1]["text"] for e in layout.events if e[0] == "label"]
    controls = [e for e in layout.events if e[0] == "operator"]
    assert len(controls) == 1 and controls[0][3] is True
    if source:
        assert labels[0] == "Source update preview · running"
        assert "2.5 s elapsed · accepted source retained" in labels
        assert controls[0][1] == "mcad.assembly_source_update_cancel"
        assert controls[0][2]["text"] == "Cancel Source Preview"
        assert not any("motion" in label.lower() for label in labels)
    else:
        assert labels[0] == "Driver motion preview · running"
        assert controls[0][1] == "mcad.assembly_visual_joint_cancel"
        assert controls[0][2]["text"] == "Cancel Motion Preview"
        assert "Full assembly replay. Accepted display and checks retained." in labels
    assert details == before
