"""Real UI routing/operator methods with pure drafts, not native/GUI evidence."""
import ast
import copy
import importlib
import math
from types import SimpleNamespace as NS

import pytest
from test_pending_circle_diameter import a, c, d

ROOT = __import__(a.__package__, fromlist=['x']).__path__[0]


def load(name, *, cls=None, **extra):
    from pathlib import Path
    module = "constraint_ui" if cls else "general_viewport"
    tree = ast.parse((Path(ROOT) / (module + ".py")).read_text())
    body = next(n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls) if cls else tree.body
    node = copy.deepcopy(next(n for n in body if isinstance(n, ast.FunctionDef) and n.name == name))
    node.decorator_list = []
    env = {"__package__": a.__package__, **extra}
    if cls:
        env["_diameter_display_text"] = load_display()
        env["_diameter_radius_value"] = load_display("_diameter_radius_value")
    exec(compile(ast.Module(body=[node], type_ignores=[]), module, "exec"), env)
    return env[name]


def load_display(name="_diameter_display_text"):
    from pathlib import Path
    tree = ast.parse((Path(ROOT) / "constraint_ui.py").read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    env = {"math": math}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "display", "exec"), env)
    return env[name]


def owner(value=10):
    state = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(
        '{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{"size":20},"features":[],"active_feature":null}'
    ))
    receipt = state.command_draft.execute(c.AddDiameterCircle(c.PointSeed(0, 0), 20))
    rid = receipt.constraint_id
    state.place_annotation(rid, (8, 8), display="diameter")
    # Arbitrary valid authored radius expression, never a rewritten display value.
    if value != 10:
        state.command_draft._sketch["constraints"][0]["value"] = value
    result = NS(draft=state, commands=state.command_draft, calls=[], stamp=1)
    result.open_dimension_field = lambda *args, **kw: result.calls.append((args, kw))
    result.begin_dimension = result.commands.begin_edit
    result.update_raw = result.commands.update_edit
    result.checkpoint = lambda: result.calls.append("checkpoint")
    result.request_driver_accept = lambda context: result.calls.append("accept")
    return result, rid


def field(value):
    calls = []
    route = load("_open_field", bpy=NS(ops=NS(mcad=NS(
        sketch_numeric_relation=lambda *args, **kw: calls.append((args, kw))
    ))))
    return lambda rid: route(value, rid, (100, 100)), calls


def test_diameter_annotation_opens_exact_driver_without_changing_selection_or_draft():
    value, rid = owner()
    before = importlib.import_module(a.__package__ + ".draft_dispatch").dumps(value.draft)
    route, calls = field(value)
    route(rid)
    assert calls == [(("INVOKE_DEFAULT",), {"mode": "DIAMETER", "constraint_id": rid})]
    assert importlib.import_module(a.__package__ + ".draft_dispatch").dumps(value.draft) == before and not value.calls


def test_existing_radius_and_retained_raw_edits_keep_original_semantics():
    value, rid = owner()
    route, calls = field(value)
    value.commands.begin_edit(rid)
    value.commands.update_edit("size + 2")
    route(rid)
    assert not calls and value.commands.pending_edit.raw_text == "size + 2"
    value.commands.cancel_edit()
    value.draft.place_annotation(rid, (8, 8), display="radius")
    route(rid)
    assert len(value.calls) == 2 and not calls


def dialog(value, rid):
    selection = importlib.import_module(a.__package__ + ".constraint_selection")
    def idle(current, context):
        if current.commands.pending_edit is not None:
            raise c.DraftError("Retained edit")
    env = dict(active=lambda ctx: value, _require_ui_idle=idle,
               constraint_selection=selection, constraint_actions=NS(_binding=lambda current: current.stamp),
               DraftError=c.DraftError, _error=lambda op, exc: op.errors.append(str(exc)) or {"CANCELLED"})
    invoke = load("invoke", cls="MCAD_OT_sketch_numeric_relation", **env)
    execute = load("execute", cls="MCAD_OT_sketch_numeric_relation", **env)
    op = NS(mode="DIAMETER", constraint_id=rid, errors=[])
    context = NS(window_manager=NS(invoke_props_dialog=lambda op: {"RUNNING_MODAL"}))
    return op, context, invoke, execute


@pytest.mark.parametrize("source,shown", [(10, "20.0"), ("size / 2", "2*(size / 2)"), ("  size + 1  ", "2*(  size + 1  )"), ("size" + " " * 252, "2*(size" + " " * 252 + ")")])
def test_dialog_cancel_and_unchanged_apply_preserve_exact_radius_source(source, shown):
    value, rid = owner(source)
    before = value.commands.checkpoint_payload()
    op, context, invoke, execute = dialog(value, rid)
    assert invoke(op, context, None) == {"RUNNING_MODAL"}, op.errors
    assert op.value == shown
    # Dismissal requires no command: invocation is read-only.
    assert value.commands.checkpoint_payload() == before
    assert execute(op, context) == {"FINISHED"}, op.errors
    assert value.commands.checkpoint_payload() == before and not value.calls


@pytest.mark.parametrize("raw,stored", [("3 cm", "15.0"), ("1/8 in", "1.5875"), ("1 1/2 in", "19.049999999999997"), ("30", "15.0"), ("size + 4", "(size + 4)/2")])
def test_literal_unit_and_named_formula_are_halved_exactly_once(raw, stored):
    value, rid = owner()
    op, context, invoke, execute = dialog(value, rid)
    assert invoke(op, context, None) == {"RUNNING_MODAL"}
    op.value = raw
    assert execute(op, context) == {"FINISHED"}, op.errors
    assert value.commands.pending_edit.raw_text == stored
    assert value.commands.sketch["constraints"][0]["value"] == 10
    assert value.calls == ["checkpoint", "accept"]


def test_stale_dialog_cannot_open_edit_or_change_source():
    value, rid = owner()
    op, context, invoke, execute = dialog(value, rid)
    assert invoke(op, context, None) == {"RUNNING_MODAL"}
    value.stamp += 1
    op.value = "30"
    assert execute(op, context) == {"CANCELLED"}
    assert "sketch changed" in op.errors[0]
    assert value.commands.pending_edit is None and not value.calls


def test_exact_missing_target_does_not_fall_back_to_selected_circle():
    value, rid = owner()
    value.draft.select((("circle", value.commands.sketch["circles"][0]["id"]),))
    op, context, invoke, _ = dialog(value, "missing")
    assert invoke(op, context, None) == {"CANCELLED"}
    assert value.commands.pending_edit is None and not value.calls


def test_dimension_tool_reposition_preserves_diameter_display_and_routes_dialog():
    value, rid = owner()
    circle = value.commands.sketch["circles"][0]["id"]
    value.draft.select((("circle", circle),))
    value.geometry = lambda: NS(circles={circle: NS(radius_mm=10, center_mm=(0, 0))},
                                dimensions={rid: NS(kind="radius", refs=(circle,))})
    opened = []
    dimension = load("_dimension", _point_dimension=lambda owner: None,
                     _pointer=lambda owner, event: (20, 20),
                     _xy=lambda owner, event: (100, 100), AddRelation=c.AddRelation,
                     _open_field=lambda *args, **kw: opened.append((args, kw)))
    dimension(value, None, None)
    assert value.draft.annotations[rid]["display"] == "diameter"
    assert value.draft.annotations[rid]["offset"] == [20.0, 20.0]
    assert not value.draft.selection
    assert opened == [((value, rid, (100, 100)), {"select_all": True})]


@pytest.mark.parametrize("source,shown", [
    ("15.0", "30.0"), ("  1e-6  ", "2e-06"), ("1e6", "2000000.0"),
    ("+10", "20.0"), ("1_000", "2000.0"), ("1+2", "2*(1+2)"),
    ("size", "2*(size)"), ("inf", "2*(inf)"), ("nan", "2*(nan)"),
    ("1e999", "2*(1e999)"),
])
def test_numeric_source_display_never_evaluates_formulas(source, shown):
    assert load_display()(source) == shown
    value, rid = owner(source)
    before = value.commands.checkpoint_payload()
    op, context, invoke, execute = dialog(value, rid)
    # Invalid sources are only a helper defense probe; real drafts reject them.
    if source in {"inf", "nan", "1e999"}:
        return
    assert invoke(op, context, None) == {"RUNNING_MODAL"}
    assert op.value == shown
    assert execute(op, context) == {"FINISHED"}
    assert value.commands.checkpoint_payload() == before
