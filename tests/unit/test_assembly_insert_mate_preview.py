"""Native-free visual insertion owner transitions; GPU and actual ray UI are separate."""

import ast
import copy
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, Mock

import pytest
from test_assembly_insert_preview import insertion  # noqa: F401
from test_assembly_insert_preview_draft import inputs  # noqa: F401
from test_assembly_source_update_preview import ADDON
from test_assembly_source_update_preview import host as source_host  # noqa: F401


@pytest.fixture
def mate_owner(insertion, monkeypatch):  # noqa: F811
    h = insertion
    base = h.env["InsertPreviewSession"]
    h.host.owner.snapshot["fields"]["owner_id"] = "accepted-owner"
    h.context.area.spaces = NS(active=NS(region_3d=object(), region_quadviews=[]))
    accepted_object = object()
    display = NS(owned_objects=Mock(return_value=[accepted_object]))
    pending = NS(prepare_insert_mate_preview=Mock(return_value=object()))
    projection = NS(
        target_geometry=Mock(return_value=(((0, 0, 0), (2, 0, 0), (0, 2, 0)), ((0, 1, 2),))),
        pick=Mock(return_value={"face_id": "chosen", "distance_mm": 5}),
    )
    mate = NS(attach_face_pair=Mock(), candidate=Mock(return_value={"final": "candidate"}))
    env = dict(
        bpy=NS(),
        view3d_utils=NS(
            region_2d_to_origin_3d=Mock(return_value=[0, 0, 5]),
            region_2d_to_vector_3d=Mock(return_value=[0, 0, -1]),
        ),
        assembly_display=display,
        assembly_pending=pending,
        overlay=h.host.env["overlay"],
        viewport=h.host.viewport,
        InsertMateDraft=Mock(return_value=mate),
        PickProjection=Mock(return_value=projection),
        InsertPreviewSession=base,
        BridgeError=ValueError,
    )

    def show(self, response):
        self.expectation = response["digest"]
        self.ghost_positions = tuple(response["ghost"])
        self.error = ""

    monkeypatch.setattr(base, "_show_response", show)
    path = ADDON / "assembly_insert_mate_preview.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tree.body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    exec(compile(tree, str(path), "exec"), env)
    owner = env["InsertMateSession"](h.context, h.draft)
    owner.scale = 1
    operator = NS(report=Mock())
    return NS(
        env=env,
        owner=owner,
        context=h.context,
        original=h,
        projection=projection,
        mate=mate,
        pending=pending,
        display=display,
        accepted_object=accepted_object,
        operator=operator,
    )


def seed(h):
    response = {"digest": "seed-exact", "ghost": ((1, 2, 3),)}
    h.owner._show_response(response)
    return response


def event(h, action=None, *, kind="LEFTMOUSE"):
    point = (999, 999)
    if action is not None:
        button = next(b for b in h.owner.panel_layout().buttons if b.action == action)
        point = (
            (button.bounds[0] + button.bounds[2]) / 2,
            (button.bounds[1] + button.bounds[3]) / 2,
        )
    return NS(type=kind, value="PRESS", ctrl=False, point=point)


def test_seed_builds_mate_projection_but_has_no_apply_authority(mate_owner):
    h = mate_owner
    assert not h.owner.ready()
    response = seed(h)
    h.env["InsertMateDraft"].assert_called_once_with(h.original.draft, response)
    h.env["PickProjection"].assert_called_once_with(
        response, "seed-exact", h.original.draft.candidate()
    )
    assert h.owner.phase == "picking" and h.owner.expectation is None
    assert h.owner.seed_ghost == ((1, 2, 3),) and not h.owner.ready()
    assert not next(b for b in h.owner.panel_layout().buttons if b.action == "apply").enabled
    h.original.host.state.commit_candidate.assert_not_called()


def test_target_switch_resets_explicit_isolation_and_seed_geometry(mate_owner):
    h = mate_owner
    seed(h)
    h.owner.target_only = True
    h.owner.ghost_positions = ((99, 99, 99),)
    h.owner.expectation = "stale-final"
    h.owner.select_end("child")
    assert not h.owner.target_only and h.owner.expectation is None
    assert h.owner.ghost_positions == h.owner.seed_ghost and h.owner.pick_end == "child"
    h.projection.target_geometry.assert_called_with(h.owner.child_id)


def test_rejected_second_face_keeps_previous_fields_and_draft(mate_owner):
    h = mate_owner
    seed(h)
    h.owner.faces = {"parent": "parent-face", "child": None}
    h.owner.select_end("child")
    h.owner.target_only = True
    before = copy.deepcopy(h.owner.candidate)
    h.mate.attach_face_pair.side_effect = ValueError("unsupported face pair")
    assert h.owner.modal_event(h.operator, h.context, event(h)) == {"RUNNING_MODAL"}
    assert h.owner.faces == {"parent": "parent-face", "child": None}
    assert h.owner.candidate == before and h.owner.expectation is None and not h.owner.ready()
    assert "unsupported face pair" in h.owner.error
    h.pending.prepare_insert_mate_preview.assert_not_called()


def test_restart_discards_faces_and_final_authority_restores_seed_ghost(mate_owner):
    h = mate_owner
    seed(h)
    h.owner.faces = {"parent": "old-parent", "child": "old-child"}
    h.owner.phase, h.owner.expectation = "final", "final-exact"
    h.owner.ghost_positions = ((99, 99, 99),)
    h.owner.target_only = True
    assert h.owner.modal_event(h.operator, h.context, event(h, "restart")) == {"RUNNING_MODAL"}
    assert h.owner.faces == {"parent": None, "child": None}
    assert h.owner.phase == "picking" and h.owner.expectation is None
    assert h.owner.ghost_positions == h.owner.seed_ghost and not h.owner.target_only
    h.original.host.state.commit_candidate.assert_not_called()


def test_pending_freezes_picks_target_switch_and_apply(mate_owner):
    h = mate_owner
    seed(h)
    h.owner.pending = object()
    h.owner.phase = "final_pending"
    h.owner.pick(h.context, (999, 999))
    h.projection.pick.assert_not_called()
    with pytest.raises(ValueError, match="Wait"):
        h.owner.select_end("parent")
    buttons = {b.action: b for b in h.owner.panel_layout().buttons}
    assert all(
        not buttons[name].enabled for name in ("parent", "child", "target_only", "restart", "apply")
    )
    assert buttons["cancel"].enabled and not h.owner.ready()


def test_final_replay_not_seed_digest_is_only_ready_state(mate_owner):
    h = mate_owner
    seed(h)
    h.owner.phase = "final_pending"
    h.owner._show_response({"digest": "final-exact", "ghost": ((4, 5, 6),)})
    assert h.owner.phase == "final" and h.owner.expectation == "final-exact"
    assert h.owner.ready() and not h.owner.target_points
    h.env["PickProjection"].assert_called_once()
    h.original.host.state.commit_candidate.assert_not_called()


def test_failed_pending_clears_authority_without_publication(mate_owner):
    h = mate_owner
    seed(h)
    h.owner.phase, h.owner.pending = "final_pending", object()
    h.original.host.pending.poll = Mock(side_effect=ValueError("exact replay failed"))
    h.owner.tick(h.context)
    assert h.owner.pending is None and h.owner.expectation is None
    assert not h.owner.ghost_positions and not h.owner.ready()
    h.original.host.state.commit_candidate.assert_not_called()


@pytest.mark.parametrize("changed", ["document", "part", "mode"])
def test_wrong_context_modal_cleans_resources_and_intent(mate_owner, changed):
    h = mate_owner
    seed(h)
    if changed == "document":
        h.context.scene.mechanical_cad_assembly.document_json = "new"
    if changed == "part":
        h.context.scene.mechanical_cad.document_json = "new"
    if changed == "mode":
        h.context.mode = "EDIT_MESH"
    assert h.owner.modal_event(h.operator, h.context, event(h, kind="TIMER")) == {"CANCELLED"}
    assert not h.owner.alive and h.owner.projection is None and h.owner.mate is None
    assert not h.owner.target_points and h.owner.expectation is None


@pytest.mark.parametrize("changed", ["object", "viewport"])
def test_accepted_identity_or_viewport_rebinding_refuses(mate_owner, changed):
    h = mate_owner
    seed(h)
    if changed == "object":
        h.display.owned_objects.return_value = [object()]
    else:
        h.context.area.spaces.active.region_3d = object()
    with pytest.raises(ValueError, match="display or picking viewport changed"):
        h.owner.assert_current(h.context)
    assert h.owner.modal_event(h.operator, h.context, event(h, kind="TIMER")) == {"CANCELLED"}
    assert not h.owner.alive


def test_foreign_object_with_copied_tags_is_not_an_accepted_identity(mate_owner):
    h = mate_owner
    foreign = MagicMock()
    foreign.get.return_value = "accepted-owner"
    matrix = MagicMock()
    evaluated = foreign.evaluated_get.return_value
    evaluated.matrix_world.copy.return_value = matrix
    evaluated.ray_cast.return_value = (True, object(), object(), 0)
    (matrix.__matmul__.return_value.__sub__.return_value.dot).return_value = 2
    h.env["viewport"]._nearest_visible_mesh = Mock(return_value=foreign)
    h.context.evaluated_depsgraph_get = Mock(return_value=object())
    with pytest.raises(ValueError, match="obscures"):
        h.owner._foreign_occlusion(h.context, MagicMock(), MagicMock(), 5)
    foreign.get.assert_not_called()
    excluded = h.env["viewport"]._nearest_visible_mesh.call_args.kwargs["exclude_objects"]
    assert excluded == frozenset({h.accepted_object}) and foreign not in excluded


def test_explicit_target_only_is_forwarded_and_skips_foreign_query_only_when_chosen(mate_owner):
    h = mate_owner
    seed(h)
    h.owner.target_only = True
    h.owner._foreign_occlusion = Mock(
        side_effect=AssertionError("should not inspect other geometry")
    )
    h.owner.pick(h.context, (999, 999))
    assert h.projection.pick.call_args.kwargs == {"target_only": True}
    h.owner._foreign_occlusion.assert_not_called()
    assert h.owner.faces["parent"] == "chosen" and h.owner.pick_end == "child"
    assert not h.owner.target_only  # No silent carry-over to next target.


def test_completed_face_pair_starts_final_replay_without_publishing(mate_owner):
    h = mate_owner
    seed(h)
    h.owner.faces = {"parent": "parent-face", "child": None}
    h.owner.select_end("child")
    h.owner.target_only = True
    h.owner.pick(h.context, (999, 999))
    h.mate.attach_face_pair.assert_called_once_with("parent-face", "chosen")
    assert h.owner.faces == {"parent": "parent-face", "child": "chosen"}
    assert h.owner.candidate == {"final": "candidate"}
    assert h.owner.phase == "final_pending" and h.owner.pending is not None
    assert h.owner.expectation is None and not h.owner.ready()
    h.pending.prepare_insert_mate_preview.assert_called_once_with(
        h.context, h.mate, expected_json="accepted", expected_working_part="part"
    )
    h.original.host.state.commit_candidate.assert_not_called()


def test_failed_final_admission_leaves_no_ready_candidate_and_allows_restart(mate_owner):
    h = mate_owner
    seed(h)
    h.owner.faces = {"parent": "parent-face", "child": None}
    h.owner.select_end("child")
    h.owner.target_only = True
    h.pending.prepare_insert_mate_preview.side_effect = ValueError("admission refused")
    assert h.owner.modal_event(h.operator, h.context, event(h)) == {"RUNNING_MODAL"}
    assert h.owner.expectation is None and h.owner.pending is None and not h.owner.ready()
    assert "admission refused" in h.owner.error
    assert next(b for b in h.owner.panel_layout().buttons if b.action == "restart").enabled
    h.original.host.state.commit_candidate.assert_not_called()


def test_initial_quad_view_refuses_visual_insertion(mate_owner):
    h = mate_owner
    h.context.area.spaces.active.region_quadviews = [object(), object(), object(), object()]
    with pytest.raises(ValueError, match="not Quad View"):
        h.env["InsertMateSession"](h.context, h.original.draft)
    h.env["InsertMateDraft"].assert_not_called()
    h.original.host.state.commit_candidate.assert_not_called()


def test_switch_to_quad_view_revokes_live_picking_context(mate_owner):
    h = mate_owner
    seed(h)
    h.context.area.spaces.active.region_quadviews = [object(), object(), object(), object()]
    with pytest.raises(ValueError, match="picking viewport changed"):
        h.owner.assert_current(h.context)
    assert h.owner.modal_event(h.operator, h.context, event(h, kind="TIMER")) == {"CANCELLED"}
    assert not h.owner.alive and h.owner.projection is None and h.owner.expectation is None
    h.original.host.state.commit_candidate.assert_not_called()


@pytest.mark.parametrize("phase", ["final_pending", "final"])
def test_full_mate_review_never_claims_inactive_highlighted_only_mode(mate_owner, phase):
    h = mate_owner
    seed(h)
    h.owner.target_only = True
    picking_labels = [label.text for label in h.owner.panel_layout().labels]
    assert "HIGHLIGHTED ONLY: other geometry ignored" in picking_labels
    assert "Full Assembly geometry + mate preview" not in picking_labels
    assert "not saved / checked" in h.owner.title
    h.owner.phase = "final_pending"
    if phase == "final":
        h.owner._show_response({"digest": "final-exact", "ghost": ((4, 5, 6),)})
        assert h.owner.target_only is False
    labels = [label.text for label in h.owner.panel_layout().labels]
    assert "Full Assembly geometry + mate preview" in labels
    assert not any("HIGHLIGHTED ONLY" in text or "other geometry ignored" in text for text in labels)
    assert not next(b for b in h.owner.panel_layout().buttons if b.action == "target_only").enabled
    h.original.host.state.commit_candidate.assert_not_called()
