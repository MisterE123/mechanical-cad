"""Native-free presentation probes; no transaction preparation on pointer events."""

import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_constraint_selection import c, selected, sketch

ROOT = Path(__file__).resolve().parents[2]


def ui_functions(**namespace):
    # Execute the actual small UI adapter without importing Blender or replacing
    # its implementation. Native owner/Apply coverage remains in Blender smoke.
    path = ROOT / "blender_addon/mechanical_cad_blender/constraint_ui.py"
    tree = ast.parse(path.read_text())
    tree.body = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"action_available", "_require_ui_idle"}
    ]
    exec(compile(tree, str(path), "exec"), namespace)
    return SimpleNamespace(**namespace)


class GeneralSession:
    def _require_idle(self):
        if self.busy:
            raise ValueError("busy or stale owner")


class Commands:
    pending_edit = None

    def __init__(self):
        self.sketch = sketch()
        self.solution_reads = 0

    @property
    def has_current_solution(self):
        self.solution_reads += 1
        return False


@pytest.fixture
def host():
    context = SimpleNamespace(area=object(), workspace=object(), view_layer=object())
    owner = GeneralSession()
    owner.area, owner.workspace = context.area, context.workspace
    owner.window = SimpleNamespace(view_layer=context.view_layer)
    owner.commands = Commands()
    owner.draft = SimpleNamespace(selection=selected(("line", "line")), proposal=None)
    owner.proposal_capture = False
    owner.annotation_drag = owner.publication = owner.gesture_intent = None
    owner.evidence_request = owner.evidence_response = None
    owner.busy = False

    def forbidden(*args, **kwargs):
        raise AssertionError("Presentation must not prepare or serialize a transaction")

    ui = ui_functions(
        GeneralSession=GeneralSession,
        DraftError=ValueError,
        active=lambda _context: owner,
        constraint_selection=c,
        constraint_actions=SimpleNamespace(prepare=forbidden),
        draft_dispatch=SimpleNamespace(dumps=forbidden),
    )
    return context, owner, ui


def test_pointer_probe_never_captures_transaction_or_reads_unneeded_solution(host):
    context, owner, ui = host
    before = copy.deepcopy(owner.commands.sketch)
    assert ui.action_available(context, "horizontal") is True
    assert ui.action_available(context, "coincident") is False
    assert owner.commands.solution_reads == 0
    assert owner.commands.sketch == before
    owner.draft.selection = selected(("point", "a"))
    assert ui.action_available(context, "fix_here") is False
    assert owner.commands.solution_reads == 1
    assert ui.action_available(context, "fix_origin") is True
    assert owner.commands.solution_reads == 1


@pytest.mark.parametrize("field", ["area", "workspace", "view_layer"])
def test_context_change_fails_closed(host, field):
    context, _, ui = host
    setattr(context, field, object())
    assert ui.action_available(context, "horizontal") is False


@pytest.mark.parametrize(
    "field", ["annotation_drag", "publication", "gesture_intent", "proposal_capture", "busy"]
)
def test_busy_or_unfinished_owner_disables_hint(host, field):
    context, owner, ui = host
    setattr(owner, field, True)
    assert ui.action_available(context, "horizontal") is False


def test_selection_and_authored_changes_are_read_fresh_without_cache(host):
    context, owner, ui = host
    assert ui.action_available(context, "horizontal")
    owner.draft.selection = selected(("point", "a"))
    assert not ui.action_available(context, "horizontal")
    owner.draft.selection = selected(("line", "line"))
    owner.commands.sketch["lines"] = []
    assert not ui.action_available(context, "horizontal")


@pytest.mark.parametrize(
    "selection",
    [
        [],
        selected(("point", "a")),
        selected(("line", "line")),
        selected(("point", "a"), ("point", "c")),
    ],
)
def test_hint_matches_selection_contract_without_mutating_input(selection):
    source = sketch()
    before = copy.deepcopy((source, selection))
    contract = c.selection_contract(source, selection)
    for spec in contract.actions:
        if spec.action in {"fix_here", "remove_relation"}:
            continue  # These add a current-solution prerequisite.
        assert c.applicability_hint(
            source, selection, spec.action, has_solution=False, has_retained_evidence=False
        ) == (spec.state in {"eligible", "existing"})
    assert (source, selection) == before
