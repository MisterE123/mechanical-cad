"""Real prepare/Apply bindings with native-free host doubles, not solver evidence."""

import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_constraint_probe_authority_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package


class GeneralSession:
    def _require_idle(self):
        pass


current = None
for name, values in {
    "document_state": {"_REPLAY_RUNNING": False},
    "sketch_session": {"active_session": lambda context=None: current},
    "general_session": {"GeneralSession": GeneralSession},
}.items():
    module = types.ModuleType(PACKAGE + "." + name)
    vars(module).update(values)
    sys.modules[module.__name__] = module

actions = importlib.import_module(PACKAGE + ".constraint_actions")
drafts = importlib.import_module(PACKAGE + ".general_sketch_draft")
authoring = importlib.import_module(PACKAGE + ".general_authoring")
codec = importlib.import_module(PACKAGE + ".draft_dispatch")
BASE = '{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{},"features":[],"active_feature":null}'


def host(draft=None):
    global current
    owner = GeneralSession()
    if draft is None:
        command = drafts.GeneralSketchDraft(BASE)
        _, _, line = command.execute(
            drafts.AddLine(drafts.PointSeed(0, 0), drafts.PointSeed(3, 4))
        ).entity_ids
        draft = authoring.GeneralSketchAuthoringState(command)
        draft.select((("line", line),))
    owner.draft, owner.commands = draft, draft.command_draft
    owner.stored_snapshot = codec.dumps(draft)

    def pointer():
        return SimpleNamespace(as_pointer=lambda: 1)

    owner.area, owner.region, owner.workspace = pointer(), pointer(), pointer()
    owner.window = pointer()
    owner.window.view_layer = pointer()
    owner.scene_uid = 1
    owner.session_id, owner.input_token = "session", "input"
    owner.scene = SimpleNamespace(mechanical_cad=SimpleNamespace(document_json=draft.document_json))
    owner.evidence_request = owner.evidence_response = None
    owner.current_diagnostics = owner.guarded_evidence = owner.expected_prepared = None
    owner.publication = owner.annotation_drag = None
    owner.proposal_capture = False
    owner.backend = ("python", 1)
    owner.backend_stamp = lambda: owner.backend
    owner.execute = lambda *args: pytest.fail("Stale Apply must never execute")
    current = owner
    context = SimpleNamespace(
        area=owner.area, workspace=owner.workspace, view_layer=owner.window.view_layer
    )
    return owner, context


@pytest.mark.parametrize("mutation", ["selection", "revision", "backend", "context", "source"])
def test_hint_cannot_bypass_fresh_apply_binding(mutation):
    owner, context = host()
    hint = actions.constraint_selection.applicability_hint(
        owner.commands.sketch,
        owner.draft.selection,
        "horizontal",
        has_solution=False,
        has_retained_evidence=False,
    )
    assert hint is True
    with pytest.raises(ValueError, match="Prepare a constraint action first"):
        actions.apply(owner, context, hint)
    intent = actions.prepare(owner, "horizontal")
    if mutation == "selection":
        owner.draft.select(())
    elif mutation == "revision":
        owner.commands.execute(drafts.AddCircle(drafts.PointSeed(8, 8), 2))
    elif mutation == "backend":
        owner.backend = ("changed-python", 2)
    elif mutation == "context":
        context.area = object()
    elif mutation == "source":
        owner.scene.mechanical_cad.document_json += " "
    with pytest.raises(ValueError):
        actions.apply(owner, context, intent)
