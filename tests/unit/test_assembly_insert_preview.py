"""Private insertion handoff and field dispatch; no native/GPU qualification."""

import ast
import copy
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from test_assembly_insert_preview_draft import InsertPreviewDraft, build, inputs  # noqa: F401
from test_assembly_source_update_preview import ADDON
from test_assembly_source_update_preview import host as source_host  # noqa: F401


@pytest.fixture
def insertion(source_host, inputs, monkeypatch):  # noqa: F811
    host = source_host
    accepted, part, args = inputs
    base = host.env["SourceUpdatePreview"]
    host.state.read_assembly = Mock(return_value=accepted)
    host.pending.prepare_insert_preview = Mock(return_value="pending")

    def init(self, context):
        self.__dict__.update(host.owner.__dict__)

    monkeypatch.setattr(base, "__init__", init)
    env = dict(
        bpy=NS(ops=NS(mcad=NS(assembly_insert_preview=Mock()))),
        Operator=object,
        assembly_pending=host.pending,
        assembly_state=host.state,
        assembly_source_update_preview=NS(
            SourceUpdatePreview=base,
            MCAD_OT_assembly_source_update_preview=host.env[
                "MCAD_OT_assembly_source_update_preview"
            ],
        ),
        InsertPreviewDraft=InsertPreviewDraft,
        BridgeError=ValueError,
        NO_SCALAR_COORDINATE={"fixed", "ball", "planar"},
        canonical_working_part=Mock(return_value=part),
        unit_value=Mock(side_effect=lambda value, kind: float(value)),
        extra_joint_arguments=Mock(return_value={}),
    )
    # Load the unchanged shared session before the launcher, retaining the same
    # injected native-free ports and all handoff/ownership assertions below.
    for name in ("assembly_insert_preview_session.py", "assembly_insert_preview.py"):
        path = ADDON / name
        tree = ast.parse(path.read_text())
        tree.body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
        exec(compile(tree, str(path), "exec"), env)
    draft = build(inputs)
    owner = env["InsertPreviewSession"](host.context, draft)
    owner.assert_current = Mock()
    owner.start = Mock(return_value=owner)
    owner.cancel = Mock()
    host.context.window_manager.modal_handler_add = Mock()
    op = env["MCAD_OT_assembly_insert_preview"]()
    op.report = Mock()
    return NS(
        env=env,
        host=host,
        draft=draft,
        owner=owner,
        op=op,
        context=host.context,
        accepted=accepted,
        part=part,
        args=args,
    )


def test_missing_or_untyped_handoff_refuses_without_start(insertion):
    h = insertion
    assert h.op.invoke(h.context, None) == {"CANCELLED"}
    h.context.window_manager.modal_handler_add.assert_not_called()
    h.host.state.commit_candidate.assert_not_called()
    assert h.env["_HANDOFF"] is None


def test_handoff_consumed_before_start_and_reentrant_invoke_cannot_reuse(insertion):
    h = insertion
    h.env["_HANDOFF"] = h.owner

    def start(context):
        assert h.env["_HANDOFF"] is None
        nested = h.env["MCAD_OT_assembly_insert_preview"]()
        nested.report = Mock()
        assert nested.invoke(context, None) == {"CANCELLED"}
        return h.owner

    h.owner.start.side_effect = start
    assert h.op.invoke(h.context, None) == {"RUNNING_MODAL"}
    h.owner.assert_current.assert_called_once_with(h.context)
    h.owner.start.assert_called_once_with(h.context)
    h.context.window_manager.modal_handler_add.assert_called_once_with(h.op)
    h.host.state.commit_candidate.assert_not_called()


@pytest.mark.parametrize("failure", ["context", "start", "modal"])
def test_invocation_failure_cancels_consumed_owner(insertion, failure):
    h = insertion
    h.env["_HANDOFF"] = h.owner
    target = {
        "context": h.owner.assert_current,
        "start": h.owner.start,
        "modal": h.context.window_manager.modal_handler_add,
    }[failure]
    target.side_effect = ValueError("stale or unavailable")
    assert h.op.invoke(h.context, None) == {"CANCELLED"}
    assert h.env["_HANDOFF"] is None
    h.owner.cancel.assert_called_once()
    h.host.state.commit_candidate.assert_not_called()


def test_lifecycle_cancellation_consumes_once(insertion):
    h = insertion
    h.env["_HANDOFF"] = h.owner
    h.env["cancel_handoff"]()
    h.env["cancel_handoff"]()
    h.owner.cancel.assert_called_once_with("Insertion handoff cancelled")
    assert h.env["_HANDOFF"] is None


@pytest.mark.parametrize(
    "result", [{"CANCELLED"}, {"RUNNING_MODAL"}, RuntimeError("launch failed")]
)
def test_launch_unconsumed_or_failed_handoff_does_not_survive(insertion, monkeypatch, result):
    h = insertion
    created = []
    real = h.env["InsertPreviewSession"]

    def construct(context, draft):
        owner = real(context, draft)
        owner.cancel = Mock()
        created.append(owner)
        return owner

    monkeypatch.setitem(h.env, "InsertPreviewSession", construct)
    invoke = h.env["bpy"].ops.mcad.assembly_insert_preview
    if isinstance(result, Exception):
        invoke.side_effect = result
        with pytest.raises(RuntimeError, match="launch failed"):
            h.env["launch"](h.context, h.draft)
    else:
        invoke.return_value = result
        assert h.env["launch"](h.context, h.draft) == result
    assert h.env["_HANDOFF"] is None
    assert created[0].cancel.called
    h.host.state.commit_candidate.assert_not_called()


def test_pending_handoff_blocks_second_launch_before_constructing(insertion):
    h = insertion
    h.env["_HANDOFF"] = h.owner
    with pytest.raises(ValueError, match="handoff is pending"):
        h.env["launch"](h.context, h.draft)
    h.env["bpy"].ops.mcad.assembly_insert_preview.assert_not_called()
    assert h.env["_HANDOFF"] is h.owner


def dialog(h, **changes):
    return NS(
        require_same_working_part=Mock(),
        _expected="accepted",
        use_working_part=False,
        part_id=h.draft.part_id,
        parent=h.args["parent"],
        parent_frame="origin",
        child_frame="origin",
        kind="fixed",
        coordinate="DO NOT PARSE",
        use_limits=True,
        lower="DO NOT PARSE",
        upper="DO NOT PARSE",
        rotation="0",
        use_rotation_limits=False,
        rotation_lower="-90",
        rotation_upper="90",
        name="New child",
        joint_name="New joint",
        **changes,
    )


def test_fixed_fields_ignore_hidden_scalar_values_and_cancel_has_no_publication(insertion):
    h = insertion
    operator = dialog(h)
    captured = []
    h.env["launch"] = lambda context, draft: captured.append(draft) or {"CANCELLED"}
    before = copy.deepcopy(h.accepted)
    assert h.env["launch_from_dialog"](operator, h.context) == {"CANCELLED"}
    assert type(captured[0]) is InsertPreviewDraft
    assert h.accepted == before
    h.env["unit_value"].assert_not_called()
    h.env["canonical_working_part"].assert_not_called()
    assert operator.require_same_working_part.call_count == 2
    h.host.state.commit_candidate.assert_not_called()


def test_cylindrical_fields_use_separate_linear_and_rotation_parsing(insertion):
    h = insertion
    operator = dialog(h)
    operator.kind, operator.coordinate, operator.lower, operator.upper = (
        "cylindrical",
        "2",
        "0",
        "10",
    )
    operator.rotation, operator.use_rotation_limits = "30", True
    captured = []
    h.env["launch"] = lambda context, draft: captured.append(draft) or {"RUNNING_MODAL"}
    h.env["launch_from_dialog"](operator, h.context)
    assert [(c.args) for c in h.env["unit_value"].call_args_list] == [
        ("2", "cylindrical"),
        ("0", "cylindrical"),
        ("10", "cylindrical"),
        ("30", "revolute"),
        ("-90", "revolute"),
        ("90", "revolute"),
    ]
    joint = captured[0].candidate()["joints"][-1]
    assert joint["coordinate"] == 2 and joint["rotation"] == 30


@pytest.mark.parametrize("phase", ["before", "capture", "part"])
def test_changed_dialog_binding_never_launches(insertion, phase):
    h = insertion
    operator = dialog(h)
    h.env["launch"] = Mock()
    if phase == "before":
        operator._expected = None
    elif phase == "part":
        operator.require_same_working_part.side_effect = ValueError("part changed")
    else:
        operator.use_working_part = True

        def capture(context):
            context.scene.mechanical_cad_assembly.document_json = "new"
            return h.part

        h.env["canonical_working_part"].side_effect = capture
    with pytest.raises(ValueError):
        h.env["launch_from_dialog"](operator, h.context)
    h.env["launch"].assert_not_called()


def test_insert_session_hooks_preserve_stable_ids_and_existing_source_hooks(insertion):
    h = insertion
    o = h.owner
    o.candidate = h.draft.candidate()
    before = h.draft.candidate()
    o.describe_candidate()
    assert o.affected == [
        "Child: Preview child",
        "Parent: " + h.accepted["instances"][0]["name"],
        "Joint: Attachment (fixed)",
    ]
    assert o.revisions.startswith("Reuse ") and o.summary().startswith("New child + joint")
    assert h.draft.candidate() == before
    assert o.prepare_pending(h.context) == "pending"
    h.host.pending.prepare_insert_preview.assert_called_once_with(
        h.context, h.draft, expected_json="accepted", expected_working_part="part"
    )
    assert h.host.owner.title == "Update source · not saved / checked"
    assert h.host.owner.summary() == "All 8 affected instances update together"


@pytest.mark.parametrize("changed", ["area", "region"])
def test_handoff_rejects_different_editor_before_start(insertion, changed):
    h = insertion
    h.env["_HANDOFF"] = h.owner
    setattr(h.context, changed, object())
    assert h.op.invoke(h.context, None) == {"CANCELLED"}
    assert h.env["_HANDOFF"] is None
    h.owner.assert_current.assert_not_called()
    h.owner.start.assert_not_called()
    h.owner.cancel.assert_called_once()


@pytest.fixture
def outer(insertion):
    h = insertion
    tree = ast.parse((ADDON / "assembly_operators.py").read_text())
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MCAD_OT_assembly_insert"
    )

    class WithoutImports(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            return None

    methods = [
        WithoutImports().visit(n)
        for n in cls.body
        if isinstance(n, ast.FunctionDef) and n.name in {"invoke", "execute", "cancel"}
    ]
    env = dict(
        assembly=lambda context: h.accepted,
        selected_component=lambda *a: None,
        state=lambda context: NS(selected_part_id=h.draft.part_id),
        launch_from_dialog=Mock(return_value={"RUNNING_MODAL"}),
        edit=NS(insert_instance=Mock(return_value={"candidate": True})),
        NO_SCALAR_COORDINATE={"fixed"},
        extra_joint_arguments=Mock(return_value={}),
        reject=Mock(return_value={"CANCELLED"}),
    )
    exec(compile(ast.Module(body=methods, type_ignores=[]), "<insertion-dialog>", "exec"), env)
    operator = dialog(h)
    operator.properties = NS(is_property_set=lambda name: False)
    operator.capture_dialog = Mock()
    operator.report = Mock()
    operator.apply = Mock(return_value={"FINISHED"})
    operator._preview_on_confirm = False
    h.context.window_manager.invoke_props_dialog = Mock(return_value={"RUNNING_MODAL"})
    return NS(env=env, operator=operator, context=h.context)


def test_outer_invocation_confirms_preview_not_apply(outer):
    h = outer
    assert h.env["invoke"](h.operator, h.context, None) == {"RUNNING_MODAL"}
    assert h.operator._preview_on_confirm is True
    h.operator.capture_dialog.assert_called_once_with(h.context)
    h.context.window_manager.invoke_props_dialog.assert_called_once_with(
        h.operator, width=520, confirm_text="Preview"
    )
    h.env["launch_from_dialog"].assert_not_called()


@pytest.mark.parametrize("failure", [False, True])
def test_outer_dispatch_consumes_flag_and_never_registers_success(outer, failure):
    h = outer
    h.operator._preview_on_confirm = True

    def launch(operator, context):
        assert operator._preview_on_confirm is False
        if failure:
            raise ValueError("refused")
        return {"RUNNING_MODAL"}

    h.env["launch_from_dialog"].side_effect = launch
    assert h.env["execute"](h.operator, h.context) == {"CANCELLED"}
    h.env["launch_from_dialog"].assert_called_once_with(h.operator, h.context)
    h.operator.apply.assert_not_called()
    h.env["edit"].insert_instance.assert_not_called()
    assert h.operator.report.call_count == int(failure)


def test_outer_cancel_never_launches_child(outer):
    h = outer
    h.operator._preview_on_confirm = True
    h.env["cancel"](h.operator, h.context)
    assert h.operator._preview_on_confirm is False
    h.env["launch_from_dialog"].assert_not_called()
    h.operator.apply.assert_not_called()


def test_headless_execute_keeps_existing_direct_path(outer):
    h = outer
    h.operator.use_limits = False
    assert h.env["execute"](h.operator, h.context) == {"FINISHED"}
    h.env["launch_from_dialog"].assert_not_called()
    h.operator.apply.assert_called_once_with(h.context, {"candidate": True})
