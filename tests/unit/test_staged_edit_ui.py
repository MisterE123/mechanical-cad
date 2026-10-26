"""Host-only proposal UI seams; native RNA and GUI qualification are separate."""

import ast
import copy
import importlib
import json
import sys
import textwrap
import types
from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender"


@pytest.fixture
def ui(monkeypatch):
    name = "mcad_staged_edit_ui_tests"
    for key in tuple(sys.modules):
        if key == name or key.startswith(name + "."):
            monkeypatch.delitem(sys.modules, key)
    package = types.ModuleType(name)
    package.__path__ = [str(ADDON)]
    monkeypatch.setitem(sys.modules, name, package)

    def module(suffix, **attrs):
        result = types.ModuleType(suffix)
        result.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, suffix, result)
        return result

    module("bpy")
    module(
        "bpy.props",
        BoolProperty=lambda **kw: kw,
        EnumProperty=lambda **kw: kw,
        IntProperty=lambda **kw: kw,
        StringProperty=lambda **kw: kw,
    )
    module("bpy.types", Operator=type("Operator", (), {}))
    module(name + ".document_state", _REPLAY_RUNNING=False)
    module(name + ".execution_lease", is_busy=lambda: False)
    module(name + ".repair_resume", active_for_scene=lambda scene: None)
    module(name + ".staged_edit_store", resume_reserved=lambda: False)
    module(name + ".workspace", has_draft=lambda context: False)
    module(name + ".common", _state=lambda context: context.state)
    module(
        name + ".help_ui",
        _panel_wrap=lambda context, text: [text],
        _draw_feature_help=lambda *args: None,
        _feature_help_next=lambda *args: None,
        _feature_help_previous=lambda *args: None,
        _help_button=lambda *args: None,
    )
    module(
        name + ".operators",
        _reject_candidate=lambda op, context, message: ("REJECTED", message),
        _report_result=lambda op, context, result: result,
    )
    module(name + ".history_operators", _HistoryDialog=type("History", (), {}))
    for suffix in ("backend_contracts", "backend_runtime", "guarded_transport"):
        module(name + "." + suffix)
    staged = module(
        name + ".staged_edit",
        pending=None,
        saved_raw=lambda context: getattr(context.state, "repair_intent_json", ""),
    )

    def require(context, token):
        proposal = staged.pending
        if proposal is None or proposal.token != token:
            raise ValueError("Proposal expired")
        return proposal

    def discard(context, token=None):
        if token is not None:
            require(context, token)
        staged.pending = None

    staged.require = require
    staged.current = lambda context: staged.pending
    staged.discard = discard
    return importlib.import_module(name + ".staged_edit_ui")


class Proposal:
    token = "proposal-a"
    feature_id = "body"

    def __init__(self, document, failures):
        self._document = copy.deepcopy(document)
        accepted = copy.deepcopy(document)
        accepted["features"][0]["params"]["length"] = 1
        self.base_json = json.dumps(accepted)
        self.failures = copy.deepcopy(failures)

    @property
    def document(self):
        return copy.deepcopy(self._document)


@pytest.fixture
def proposal():
    return Proposal(
        {
            "features": [
                {"id": "body", "label": "Body", "kind": "extrude", "params": {"length": 5}},
                {
                    "id": "sketch",
                    "label": "Attached sketch",
                    "kind": "sketch_constrained",
                    "inputs": {"support": "body", "external": "body"},
                    "support_face": "body/face/top",
                    "projections": [{"target": "guide", "source": "edge"}],
                },
            ]
        },
        [
            {
                "id": "sketch",
                "status": "failed",
                "error": {"code": "missing", "message": "Unresolved reference"},
            }
        ],
    )


@pytest.fixture
def context(proposal):
    return types.SimpleNamespace(
        mode="OBJECT",
        scene=object(),
        state=types.SimpleNamespace(document_json=proposal.base_json, last_action_error=""),
    )


class Layout:
    def __init__(self, root=None):
        self.root = root or self
        if root is None:
            self.labels, self.buttons, self.children, self.events = [], [], [], []
        self.enabled = True
        self.alert = False
        self.operator_context = "EXEC_DEFAULT"

    def row(self, **kwargs):
        child = Layout(self.root)
        self.root.children.append(child)
        return child

    box = row

    def label(self, *, text, **kwargs):
        self.root.labels.append(text)
        self.root.events.append(("label", text))

    def operator(self, identifier, **kwargs):
        button = types.SimpleNamespace(
            identifier=identifier,
            enabled=self.enabled,
            operator_context=self.operator_context,
            **kwargs,
        )
        self.root.buttons.append(button)
        self.root.events.append(("operator", identifier))
        return button


def test_review_uses_detached_proposal_and_rejects_changed_snapshot(ui, proposal, context):
    ui.staged_edit.pending = proposal
    document = ui.review_document(context, proposal.token, proposal.base_json)
    assert document == proposal.document
    assert document != json.loads(context.state.document_json)
    ui.validate_review(context, proposal.token, proposal.base_json, document)
    document["features"][0]["params"]["length"] = 99
    assert proposal.document["features"][0]["params"]["length"] == 5
    with pytest.raises(ValueError, match="proposed edit changed"):
        ui.validate_review(context, proposal.token, proposal.base_json, document)


@pytest.mark.parametrize("token,original", [("expired", None), (None, "changed")])
def test_review_rejects_token_or_accepted_base(ui, proposal, context, token, original):
    ui.staged_edit.pending = proposal
    with pytest.raises(ValueError):
        ui.review_document(context, token or proposal.token, original or proposal.base_json)


def test_explicit_discard_requires_matching_token_and_never_edits_accepted_json(
    ui, proposal, context
):
    ui.staged_edit.pending = proposal
    operator = ui.MCAD_OT_discard_proposed_edit()
    operator.report = lambda *args: None
    operator.staged_token = "older-proposal"
    assert operator.execute(context)[0] == "REJECTED"
    assert ui.staged_edit.pending is proposal
    operator.staged_token = proposal.token
    assert operator.execute(context) == {"FINISHED"}
    assert ui.staged_edit.pending is None
    assert context.state.document_json == proposal.base_json


def test_empty_proposal_draws_nothing(ui, context):
    layout = Layout()
    assert ui.draw_staged_edit(layout, context) is False
    assert layout.labels == [] and layout.buttons == []


def test_history_exposes_failed_proposal_not_accepted_graph_actions(ui, proposal, context):
    ui.staged_edit.pending = proposal
    layout = Layout()
    assert ui.draw_staged_edit(layout, context) is True
    labels = "\n".join(layout.labels)
    assert "Unapplied edit" in labels
    assert "Accepted model unchanged" in labels
    assert "length: 1 → 5" in labels
    assert "JSON / STEP Export use accepted model" in labels
    assert ".blend Save keeps intent" in labels
    assert "missing: Unresolved reference" in labels
    assert "Accepted feature history" in labels
    assert [button.identifier for button in layout.buttons] == [
        "mcad.edit_sketch_support",
        "mcad.replace_projection_reference",
        "mcad.discard_proposed_edit",
        "mcad.help",
    ]
    assert "Proposed edit: Body [body]" in layout.buttons[-1].detail
    for button in layout.buttons[:-1]:
        assert button.staged_token == proposal.token
        if button.identifier != "mcad.discard_proposed_edit":
            assert button.feature_id == "sketch"
    assert context.state.document_json == proposal.base_json


@pytest.mark.parametrize(
    "missing,expected",
    [
        ("support_face", "mcad.replace_projection_reference"),
        ("projections", "mcad.edit_sketch_support"),
    ],
)
def test_only_eligible_failed_sketch_repairs_are_offered(ui, proposal, context, missing, expected):
    ui.staged_edit.pending = proposal
    proposal._document["features"][1].pop(missing)
    layout = Layout()
    ui.draw_staged_edit(layout, context)
    assert [button.identifier for button in layout.buttons] == [
        expected,
        "mcad.discard_proposed_edit",
        "mcad.help",
    ]


@pytest.mark.parametrize("blocked", ["mode", "draft", "replay", "busy"])
def test_repair_buttons_are_disabled_while_editing_or_replaying(ui, proposal, context, blocked):
    ui.staged_edit.pending = proposal
    if blocked == "mode":
        context.mode = "EDIT_MESH"
    elif blocked == "draft":
        ui.workspace.has_draft = lambda context: True
    elif blocked == "replay":
        ui.document_state._REPLAY_RUNNING = True
    else:
        ui.execution_lease.is_busy = lambda: True
    layout = Layout()
    ui.draw_staged_edit(layout, context)
    assert all(
        not button.enabled
        for button in layout.buttons
        if button.identifier in {"mcad.edit_sketch_support", "mcad.replace_projection_reference"}
    )


def test_notice_distinguishes_cancel_from_discard_and_partial_apply(ui):
    layout = Layout()
    ui.draw_review_notice(layout)
    text = "\n".join(layout.labels)
    assert "entire proposed Part" in text
    assert "until the entire Part succeeds" in text
    assert "Undo Proposal Repair reverses" in text
    assert "Cancel closes this review; the proposal and kept repairs remain" in text
    assert "Discard Proposed Edit abandons them" in text


@pytest.mark.parametrize(
    "module_name,class_name",
    [
        ("support_intent_ui", "MCAD_OT_edit_sketch_support"),
        ("projection_repair_ui", "MCAD_OT_replace_projection_reference"),
    ],
)
@pytest.mark.parametrize("state", ["proposal", "newer", "expired", "accepted"])
def test_dialog_cancel_releases_only_its_evidence_and_preserves_all_work(
    ui, proposal, context, module_name, class_name, state, monkeypatch
):
    module = importlib.import_module(ui.__package__ + "." + module_name)
    cls = getattr(module, class_name)
    assert cls.__annotations__["staged_token"]["options"] == {"HIDDEN", "SKIP_SAVE"}
    operator = cls()
    operator.staged_token = "" if state == "accepted" else proposal.token
    calls = []
    evidence = types.SimpleNamespace(
        publication=types.SimpleNamespace(cancel=lambda: calls.append("release"))
    )
    field = "_review_evidence" if module_name == "support_intent_ui" else "_catalog_evidence"
    setattr(operator, field, evidence)
    proposal.repairs = ("exact prior proposal",)
    proposal.annotation_after = "unapplied annotation intent"
    pending = copy.deepcopy(proposal) if state == "newer" else proposal
    if state == "newer":
        pending.token = "newer-token"
    elif state in {"expired", "accepted"}:
        pending = None
    ui.staged_edit.pending = pending
    context.state.repair_intent_json = "exact saved checkpoint"
    context.state.last_action_error = "existing diagnostic"
    before = copy.deepcopy(vars(context.state))
    proposal_before = copy.deepcopy(vars(pending)) if pending else None

    # Cancellation must not inspect/retire a newer proposal under an old dialog's
    # context. Expiry remains owned by the existing lifecycle/current guards.
    def unexpected(*args):
        raise AssertionError("Cancel must not touch proposal ownership")

    monkeypatch.setattr(ui.staged_edit, "current", unexpected)
    monkeypatch.setattr(ui.staged_edit, "discard", unexpected)
    operator.cancel(context)
    operator.cancel(context)
    assert calls == ["release"]
    assert getattr(operator, field) is None
    assert ui.staged_edit.pending is pending
    assert (vars(pending) if pending else None) == proposal_before
    assert vars(context.state) == before


@pytest.mark.parametrize(
    "module_name,class_name",
    [
        ("support_intent_ui", "MCAD_OT_edit_sketch_support"),
        ("projection_repair_ui", "MCAD_OT_replace_projection_reference"),
    ],
)
def test_dialog_expired_proposal_rejects_before_native_evidence(
    ui, proposal, context, module_name, class_name
):
    module = importlib.import_module(ui.__package__ + "." + module_name)
    operator = getattr(module, class_name)()
    operator.staged_token = "expired"
    operator.original_json = proposal.base_json
    operator._document = proposal.document
    operator._original = lambda context: json.loads(context.state.document_json)
    ui.staged_edit.pending = proposal
    with pytest.raises(ValueError, match="Proposal expired"):
        operator._review(context)


@pytest.mark.parametrize("filename", ["panels.py", "workspace_ui.py"])
def test_accepted_graph_repair_buttons_are_hidden_while_proposal_visible(filename):
    tree = ast.parse((ADDON / filename).read_text())
    names = {"draw_support_intent", "draw_projection_repair"}
    # The upper projection launcher and lower support disclosure have separate
    # positions, but both must be gated on absence of a pending proposal.
    guarded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and ast.unparse(node.test) in {"not proposed", "staged_edit.current(context) is None"}
    ]
    calls = {
        child.func.id
        for guard in guarded
        for statement in guard.body
        for child in ast.walk(statement)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }
    assert names <= calls
    for name in names:
        assert (
            sum(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == name
                for node in ast.walk(tree)
            )
            == 1
        )


@pytest.mark.parametrize(
    "module_name,class_name",
    [
        ("support_intent_ui", "MCAD_OT_edit_sketch_support"),
        ("projection_repair_ui", "MCAD_OT_replace_projection_reference"),
    ],
)
@pytest.mark.parametrize("succeeds", [True, False])
def test_dialog_repair_accept_uses_only_staged_atomic_sink_and_releases(
    ui, proposal, context, monkeypatch, module_name, class_name, succeeds
):
    module = importlib.import_module(ui.__package__ + "." + module_name)
    operator = getattr(module, class_name)()
    operator.staged_token = proposal.token
    operator._document = proposal.document
    operator._review = lambda context: {}
    operator.poll = lambda context: True
    candidate = proposal.document
    candidate["features"][1]["support_face"] = "body/face/side"
    calls = []
    evidence = types.SimpleNamespace(
        publication=types.SimpleNamespace(cancel=lambda: calls.append("release"))
    )
    if module_name == "support_intent_ui":
        operator._review_evidence = evidence
        operator.feature_id = "sketch"
        operator.policy = "STRICT"
        operator.support_source = "body"
        operator.support_face = "body/face/side"
        operator.orientation = "WORLD_AXES"
        operator.reset_frame = False
        monkeypatch.setattr(module, "edit_support_candidate", lambda *args, **kwargs: candidate)
    else:
        operator._catalog_evidence = evidence
        operator._candidate = lambda: candidate
    ui.staged_edit.pending = proposal

    def accept(context, token, received):
        assert token == proposal.token
        assert received is candidate
        assert context.state.document_json == proposal.base_json
        calls.append("accept")
        if not succeeds:
            raise ValueError("Another dependent feature still fails")
        ui.staged_edit.pending = None
        return True

    ui.staged_edit.accept = accept
    result = operator.execute(context)
    assert calls == ["accept", "release"]
    if succeeds:
        assert result is True
        assert ui.staged_edit.pending is None
    else:
        assert result == ("REJECTED", "Another dependent feature still fails")
        assert ui.staged_edit.pending is proposal
        assert proposal.document != candidate
    assert context.state.document_json == proposal.base_json


def test_history_discloses_linked_tool_and_input_changes(ui, proposal, context):
    accepted = json.loads(proposal.base_json)
    tool = {"id": "tool", "label": "Linked tool", "kind": "extrude", "params": {"length": 1}}
    accepted["features"].append(copy.deepcopy(tool))
    proposal.base_json = json.dumps(accepted)
    context.state.document_json = proposal.base_json
    tool["params"]["length"] = 9
    proposal._document["features"].append(tool)
    proposal._document["features"][0]["inputs"] = {"profile": "another_profile"}
    ui.staged_edit.pending = proposal
    layout = Layout()
    assert ui.draw_staged_edit(layout, context)
    labels = "\n".join(layout.labels)
    assert "Linked tool · length: 1 → 9" in labels
    assert "profile: None → another_profile" in labels


@pytest.mark.parametrize("filename", ["panels.py", "workspace_ui.py"])
def test_parameter_widgets_guard_pending_proposal(filename):
    source = (ADDON / filename).read_text()
    if filename == "workspace_ui.py":
        source = source[source.index("class MCAD_PT_workspace_parameters") :]
    assignments = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Assign)]
    guarded = []
    for assignment in assignments:
        if not any(
            (isinstance(target, ast.Attribute) and target.attr == "enabled")
            or (isinstance(target, ast.Name) and target.id == "editable")
            for target in assignment.targets
        ):
            continue
        guarded.extend(
            node
            for node in ast.walk(assignment.value)
            if isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.Not)
            and isinstance(node.operand, ast.Call)
            and isinstance(node.operand.func, ast.Attribute)
            and node.operand.func.attr == "has_staged_edit"
        )
    assert guarded, "Parameter editing must be disabled while proposal ownership is active"


def test_narrow_recovery_controls_precede_bounded_details_with_full_message_access(
    ui, proposal, context
):
    ui.staged_edit.pending = proposal
    ui._panel_wrap = lambda context, text: textwrap.wrap(text, width=24)
    long_error = "A long exact native reference diagnostic " * 100
    proposal.failures[0]["error"]["message"] = long_error
    layout = Layout()
    before = proposal.document
    assert ui.draw_staged_edit(layout, context)
    events = layout.events
    first = events.index(("operator", "mcad.edit_sketch_support"))
    discard = events.index(("operator", "mcad.discard_proposed_edit"))
    assert first == 2 and discard < 5
    assert len(layout.labels) <= 11
    assert "keeps intent" in " ".join(layout.labels)
    details = layout.buttons[-1]
    assert details.identifier == "mcad.help" and details.topic == "error.rebuild"
    assert long_error in details.detail
    assert "Undo Proposal Repair reverses them" in details.detail
    assert proposal.document == before and context.state.document_json == proposal.base_json


@pytest.mark.parametrize(
    "message",
    [
        "Extrude rejected: Unapplied edit retained for repair; accepted model unchanged.",
        "An unapplied edit is retained for repair. Repair and accept it, or Discard proposed edit first.",
        "Repair and accept or discard the proposed edit before changing parameters; accepted model unchanged.",
    ],
)
def test_only_duplicate_pending_guidance_is_suppressed(ui, proposal, context, message):
    ui.staged_edit.pending = proposal
    assert ui.pending_message_is_duplicate(context, message)
    assert not ui.pending_message_is_duplicate(context, "STEP export permission denied")
    ui.staged_edit.pending = None
    assert not ui.pending_message_is_duplicate(context, message)


def test_saved_invalid_intent_exposes_resume_and_discard_without_parsing(ui, context):
    context.state.repair_intent_json = "{unsupported raw"
    layout = Layout()
    assert ui.draw_staged_edit(layout, context)
    assert ("operator", "mcad.resume_saved_repair") in layout.events
    assert ("operator", "mcad.discard_saved_repair") in layout.events
    assert context.state.repair_intent_json == "{unsupported raw"
    assert "Saved repair work" in layout.labels
    assert "Not applied to model" in layout.labels
    detail = next(button.detail for button in layout.buttons if button.identifier == "mcad.help")
    assert "unsupported or incompatible intent stays saved until explicit Discard" in detail


def test_repeated_stale_workspace_draw_and_poll_use_read_only_real_store(
    ui, proposal, context, monkeypatch
):
    # Reproduce Blender's draw-time RNA write prohibition, not only a mocked
    # current() getter. Captured validators/backend checks are not passive reads.
    class ReadOnlyState:
        document_json = proposal.base_json
        repair_intent_json = "  {unsupported raw\n"
        last_action_error = "Prior diagnostic"

        def __setattr__(self, name, value):
            raise AssertionError("Writing to ID classes during draw is not allowed")

    name = ui.__package__ + ".staged_edit_store"
    monkeypatch.delitem(sys.modules, name)
    store = importlib.import_module(name)
    monkeypatch.setattr(ui, "staged_edit_store", store)
    monkeypatch.setattr(ui.staged_edit, "current", store.current)
    context.state = ReadOnlyState()
    context.scene = types.SimpleNamespace(as_pointer=lambda: 1234, mechanical_cad=context.state)
    context.workspace = "Part after switching from Assembly"
    proposal.binding = {"workspace": "Assembly"}

    def forbidden(*args):
        pytest.fail("Passive presentation invoked binding/backend lifecycle validation")

    proposal.assert_binding = forbidden
    monkeypatch.setattr(store.backend_runtime, "configuration", forbidden, raising=False)
    monkeypatch.setattr(store, "_notify_changed", forbidden)
    monkeypatch.setitem(store._PENDING, 1234, proposal)
    for role in ("PART", "ASSEMBLY", "PART", "SKETCH", "PART"):
        context.workspace = role
        assert ui.draw_staged_edit(Layout(), context)
        assert not ui.pending_message_is_duplicate(context, "Prior diagnostic")
        assert not ui.MCAD_OT_resume_saved_repair.poll(context)
        assert store.current(context) is proposal
        assert context.state.repair_intent_json == "  {unsupported raw\n"
        assert context.state.last_action_error == "Prior diagnostic"
        assert context.state.document_json == proposal.base_json


@pytest.mark.parametrize(
    "message", ["", "Saved repair base changed; Resume refused", "STEP export permission denied"]
)
def test_saved_card_is_compact_action_first_read_only_and_keeps_error_access(
    ui, context, monkeypatch, message
):
    context.state.repair_intent_json = "{unsupported raw"
    context.state.last_action_error = message
    before = copy.deepcopy(vars(context.state))
    monkeypatch.setattr(ui, "_panel_wrap", lambda context, text: textwrap.wrap(text, width=24))
    layout = Layout()
    assert ui.draw_staged_edit(layout, context)
    assert layout.events[:4] == [
        ("label", "Saved repair work"),
        ("label", "Not applied to model"),
        ("operator", "mcad.resume_saved_repair"),
        ("operator", "mcad.discard_saved_repair"),
    ]
    assert len(layout.labels) <= 6
    assert "Resume checks saved repairs without applying changes." in " ".join(layout.labels)
    detail = layout.buttons[-1]
    assert detail.identifier == "mcad.help" and detail.topic == "error.details"
    assert "never applies edits or restores old native evidence" in detail.detail
    assert "Only a complete successful Apply Repair accepts changes" in detail.detail
    assert "Cancel Resume keeps the exact saved intent" in detail.detail
    assert "unsupported or incompatible intent stays saved" in detail.detail
    assert "Cancel in a repair review keeps the proposal" in detail.detail
    assert not ui.pending_message_is_duplicate(context, message)
    assert vars(context.state) == before
    assert ui.staged_edit.pending is None


def test_saved_sidebar_uses_invoke_and_visible_cancel(ui, context, monkeypatch):
    context.state.repair_intent_json = "saved raw"
    layout = Layout()
    assert ui.draw_staged_edit(layout, context)
    resume = next(b for b in layout.buttons if b.identifier == "mcad.resume_saved_repair")
    assert resume.operator_context == "INVOKE_DEFAULT" and resume.enabled
    monkeypatch.setattr(
        ui.repair_resume,
        "active_for_scene",
        lambda scene: types.SimpleNamespace(message="Checking proposal 2"),
    )
    monkeypatch.setattr(ui.staged_edit_store, "resume_reserved", lambda: True)
    layout = Layout()
    assert ui.draw_staged_edit(layout, context)
    assert "Checking proposal 2" in layout.labels
    buttons = {b.identifier: b for b in layout.buttons}
    assert buttons["mcad.cancel_repair_resume"].enabled
    assert not buttons["mcad.resume_saved_repair"].enabled
    assert not buttons["mcad.discard_saved_repair"].enabled
    assert not ui.MCAD_OT_resume_saved_repair.poll(context)
    assert not ui.MCAD_OT_discard_saved_repair.poll(context)
    assert context.state.repair_intent_json == "saved raw"


def test_resume_invoke_and_execute_are_distinct(ui, context, monkeypatch):
    calls = []
    monkeypatch.setattr(
        ui.repair_resume,
        "start",
        lambda *a: calls.append("modal") or {"RUNNING_MODAL"},
        raising=False,
    )
    monkeypatch.setattr(ui.staged_edit, "resume", lambda *a: calls.append("sync"), raising=False)
    operator = types.SimpleNamespace(report=lambda *a: None)
    assert ui.MCAD_OT_resume_saved_repair.invoke(operator, context, None) == {"RUNNING_MODAL"}
    assert calls == ["modal"]
    assert ui.MCAD_OT_resume_saved_repair.execute(operator, context) == {"FINISHED"}
    assert calls == ["modal", "sync"]
