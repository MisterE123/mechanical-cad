"""Pure authoring defaults, correction and draft recovery for support intent."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
package = types.ModuleType("mcad_support_edit_tests")
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[package.__name__] = package
edit = importlib.import_module(package.__name__ + ".support_intent_edit")
drafts = importlib.import_module(package.__name__ + ".general_sketch_draft")
store = importlib.import_module(package.__name__ + ".general_draft_store")
help_catalog = importlib.import_module(package.__name__ + ".help_catalog")


def base():
    return {
        "schema_version": 2,
        "id": "part",
        "name": "Part",
        "units": "mm",
        "parameters": {},
        "active_feature": "block",
        "features": [
            {
                "id": "profile",
                "label": "Profile",
                "kind": "sketch_rectangle",
                "inputs": {},
                "params": {"width": 20, "height": 20},
            },
            {
                "id": "block",
                "label": "Block",
                "kind": "extrude",
                "inputs": {"profile": "profile"},
                "params": {"length": 10},
            },
        ],
    }


def exact_result():
    return {
        "features": [
            {
                "id": "block",
                "kind": "extrude",
                "status": "ok",
                "output": {"kind": "solid"},
                "inputs": {"profile": "profile"},
                "topology": [
                    {
                        "id": "block/face/cap.end",
                        "feature_id": "block",
                        "role": "cap.end",
                        "signature": {
                            "surface": "plane",
                            "area": 400,
                            "centroid": [10, 10, 10],
                            "normal": [0, 0, 1],
                        },
                        "provenance": {"semantic_status": "stable"},
                    },
                ],
            }
        ]
    }


def add_legacy_cut_ledger(result, cut_id="cut"):
    """Complete request-only evidence for deliberately small authoring fixtures."""
    cut = next(row for row in result["features"] if row["id"] == cut_id)
    base = next(row for row in result["features"] if row["id"] == cut["inputs"]["base"])
    tool = copy.deepcopy(exact_result()["features"][0])
    tool.update(id=cut["inputs"]["tool"], inputs={})
    tool["topology"][0].update(id=tool["id"] + "/face/cap.end", feature_id=tool["id"])
    result["features"].append(tool)
    cut["cut_ancestry"] = {
        "version": 1,
        "sources": [
            {
                "port": "base",
                "source_id": base["topology"][0]["id"],
                "deleted": False,
                "modified": [face["id"] for face in cut["topology"]],
                "generated": [],
                "unchanged": [],
            },
            {
                "port": "tool",
                "source_id": tool["topology"][0]["id"],
                "deleted": True,
                "modified": [],
                "generated": [],
                "unchanged": [],
            },
        ],
    }


def new_draft(*, preserve=False):
    intent = (
        edit.capture_support_intent(exact_result(), "block", "block/face/cap.end")
        if preserve
        else None
    )
    return drafts.GeneralSketchDraft(
        json.dumps(base()),
        support={"feature_id": "block", "face_id": "block/face/cap.end"},
        support_intent=intent,
    )


def test_captured_default_survives_commands_resume_without_aliasing():
    draft = new_draft(preserve=True)
    draft.execute(drafts.AddCircle(drafts.PointSeed(0, 0), 2))
    source = draft.candidate()["features"][-1]
    assert source["support_intent"]["signature"]["centroid"] == [10, 10, 10]
    assert source["support_intent"]["orientation"] == {
        "policy": "minimal_twist",
        "tangent": [1, 0, 0],
    }
    source["support_intent"]["signature"]["centroid"][0] = 100
    source["support_intent"]["orientation"]["tangent"][0] = 100
    assert draft.candidate()["features"][-1]["support_intent"]["signature"]["centroid"][0] == 10
    assert draft.candidate()["features"][-1]["support_intent"]["orientation"]["tangent"][0] == 1
    restored = store.restore(store.dumps(draft), draft.document_json)
    assert restored.candidate() == draft.candidate()
    assert restored.checkpoint_payload() == draft.checkpoint_payload()


def test_legacy_draft_stays_strict_on_resume_and_existing_edit():
    draft = new_draft()
    assert "support_intent" not in draft.checkpoint_payload()
    restored = store.restore(store.dumps(draft), draft.document_json)
    document = restored.candidate()
    assert "support_intent" not in document["features"][-1]
    existing = drafts.GeneralSketchDraft(json.dumps(document), restored.feature_id, True)
    assert existing.candidate() == document


def test_policy_edit_is_detached_preserves_placement_and_capture():
    document = new_draft().candidate()
    saved = copy.deepcopy(document)
    identifier = document["features"][-1]["id"]
    changed = edit.edit_support_candidate(
        document, identifier, "PRESERVE_PLANE", "block", "block/face/cap.end", exact_result()
    )
    assert document == saved
    assert changed["features"][-1]["sketch"] == saved["features"][-1]["sketch"]
    reopened = edit.edit_support_candidate(
        changed, identifier, "PRESERVE_PLANE", "block", "block/face/cap.end", exact_result()
    )
    assert reopened == changed
    strict = edit.edit_support_candidate(
        changed, identifier, "STRICT", "block", "block/face/cap.end", exact_result()
    )
    assert strict == saved
    existing = drafts.GeneralSketchDraft(json.dumps(changed), identifier, True)
    assert existing.candidate() == changed
    assert "support_intent" not in existing.checkpoint_payload()  # canonical base owns it


def test_capture_refuses_unstable_or_missing_support_and_cycles():
    result = exact_result()
    result["features"][0]["topology"][0]["provenance"]["semantic_status"] = "split"
    with pytest.raises(ValueError):
        edit.capture_support_intent(result, "block", "block/face/cap.end")
    document = new_draft().candidate()
    identifier = document["features"][-1]["id"]
    document["features"].append(
        {"id": "child", "kind": "extrude", "inputs": {"profile": identifier}}
    )
    assert edit.eligible_support_ids(document, identifier) == {"block", "profile"}
    for source in (identifier, "child", "missing"):
        with pytest.raises(ValueError, match="depends"):
            edit.edit_support_candidate(
                document, identifier, "STRICT", source, "face", exact_result()
            )


def test_invalid_intent_and_detached_checkpoint_are_rejected():
    draft = new_draft(preserve=True)
    payload = draft.checkpoint_payload()
    payload["support_intent"]["version"] = 2
    with pytest.raises(ValueError):
        drafts.GeneralSketchDraft.from_checkpoint_payload(payload)
    payload = draft.checkpoint_payload()
    payload.pop("support")
    with pytest.raises(ValueError):
        drafts.GeneralSketchDraft.from_checkpoint_payload(payload)


def test_split_case_help_is_searchable_and_discloses_limits():
    for query in (
        "tnp",
        "split face",
        "strict support",
        "assumption undo",
        "minimal twist",
        "reset frame",
    ):
        assert "sketch.support_intent" in help_catalog.search_topics(query)
    text = " ".join(help_catalog.HELP_TOPICS["sketch.support_intent"][1])
    for disclosure in ("original", "removed", "Strict", "Undo", "Cancel", "legacy", "lineage"):
        assert disclosure in text
    for disclosure in (
        "World axes",
        "material spin",
        "shortest rotation",
        "Nearly opposite",
        "rotate",
    ):
        assert disclosure in text


def test_explicit_legacy_split_repair_adopts_current_original_source_only():
    document = new_draft().candidate()
    feature = document["features"][-1]
    identifier = feature["id"]
    feature["inputs"]["support"] = "cut"
    document["features"].insert(
        -1, {"id": "cut", "kind": "cut", "inputs": {"base": "block", "tool": "profile"}}
    )
    result = exact_result()
    descendants = []
    for index, x in enumerate((4, 16)):
        face = copy.deepcopy(result["features"][0]["topology"][0])
        face["id"] = f"snapshot:cut:face:{index}"
        face["signature"]["centroid"][0] = x
        face["signature"]["area"] = 180
        face["provenance"] = {
            "semantic_status": "split",
            "source_id": "block/face/cap.end",
            "operation": "cut",
            "operation_id": "cut",
            "relation": "modified",
            "source_count": 1,
            "image_count": 2,
        }
        descendants.append(face)
    result["features"].append(
        {
            "id": "cut",
            "kind": "cut",
            "inputs": {"base": "block", "tool": "profile"},
            "status": "ok",
            "output": {"kind": "solid"},
            "topology": descendants,
        }
    )
    add_legacy_cut_ledger(result)
    before = copy.deepcopy(document)
    with pytest.raises(ValueError):
        edit.capture_support_intent(result, "cut", "block/face/cap.end")
    repaired = edit.edit_support_candidate(
        document, identifier, "PRESERVE_PLANE", "cut", "block/face/cap.end", result
    )
    assert document == before
    assert repaired["features"][-1]["support_intent"]["signature"]["centroid"] == [10, 10, 10]
    assert edit.support_decision(repaired["features"][-1], result)["status"] == "assumed"
    bad = copy.deepcopy(result)
    next(row for row in bad["features"] if row["id"] == "cut")["topology"].pop()
    with pytest.raises(ValueError):
        edit.edit_support_candidate(
            document, identifier, "PRESERVE_PLANE", "cut", "block/face/cap.end", bad
        )
    with pytest.raises(ValueError):
        edit.edit_support_candidate(
            repaired,
            identifier,
            "PRESERVE_PLANE",
            "cut",
            "block/face/cap.end",
            bad,
            orientation="MINIMAL_TWIST",
            reset_frame=True,
        )


def test_capture_records_cut_source_baseline_separately_from_selected_centroid():
    result = exact_result()
    cut = copy.deepcopy(result["features"][0])
    cut.update(id="cut", kind="cut", inputs={"base": "block", "tool": "tool"})
    cut["topology"][0]["signature"]["centroid"][0] = 8
    cut["topology"][0]["signature"]["area"] = 350
    cut["topology"][0]["provenance"].update(
        operation="cut",
        operation_id="cut",
        relation="modified",
        source_id="block/face/cap.end",
        source_count=1,
        image_count=1,
    )
    tool = copy.deepcopy(result["features"][0])
    tool.update(id="tool", inputs={})
    tool["topology"][0].update(id="tool/face/cap.end", feature_id="tool")
    cut["cut_ancestry"] = {
        "version": 1,
        "sources": [
            {
                "port": "base",
                "source_id": "block/face/cap.end",
                "deleted": False,
                "modified": ["block/face/cap.end"],
                "generated": [],
                "unchanged": [],
            },
            {
                "port": "tool",
                "source_id": "tool/face/cap.end",
                "deleted": True,
                "modified": [],
                "generated": [],
                "unchanged": [],
            },
        ],
    }
    result["features"].extend([tool, cut])
    intent = edit.capture_support_intent(result, "cut", "block/face/cap.end")
    assert intent["signature"]["centroid"] == [8, 10, 10]
    assert intent["source_signature"]["centroid"] == [10, 10, 10]
    intent["signature"]["centroid"][0] = -100
    assert result["features"][-1]["topology"][0]["signature"]["centroid"] == [8, 10, 10]


def test_legacy_repair_uses_immediate_base_not_its_earlier_cut_baseline():
    document = new_draft().candidate()
    feature = document["features"][-1]
    feature["inputs"]["support"] = "cut"
    document["features"].insert(
        -1, {"id": "cut", "kind": "cut", "inputs": {"base": "block", "tool": "profile"}}
    )
    result = exact_result()
    base = result["features"][0]
    base.update(kind="cut", inputs={"base": "earlier", "tool": "profile"})
    earlier = copy.deepcopy(base)
    earlier.update(id="earlier", kind="extrude", inputs={"profile": "profile"})
    earlier["topology"][0]["signature"]["centroid"][0] = 8
    # Rebaselining must also recapture the tangent, not retain an earlier plane's direction.
    earlier["topology"][0]["signature"]["normal"] = [1, 0, 0]
    result["features"].append(earlier)
    descendants = []
    for i, x in enumerate((4, 16)):
        face = copy.deepcopy(base["topology"][0])
        face["id"] = f"snapshot:cut:face:{i}"
        face["signature"]["centroid"][0] = x
        face["signature"]["area"] = 180
        face["provenance"] = {
            "semantic_status": "split",
            "source_id": "block/face/cap.end",
            "operation": "cut",
            "operation_id": "cut",
            "relation": "modified",
            "source_count": 1,
            "image_count": 2,
        }
        descendants.append(face)
    result["features"].append(
        {
            "id": "cut",
            "kind": "cut",
            "inputs": {"base": "block", "tool": "profile"},
            "status": "ok",
            "output": {"kind": "solid"},
            "topology": descendants,
        }
    )
    add_legacy_cut_ledger(result)
    # Legacy repair still uses the immediate source. A new chain capture would
    # require complete native ledgers rather than this deliberately partial fixture.
    repaired = edit.edit_support_candidate(
        document, feature["id"], "PRESERVE_PLANE", "cut", "block/face/cap.end", result
    )
    intent = repaired["features"][-1]["support_intent"]
    assert intent["source_signature"] == intent["signature"]
    assert intent["signature"]["centroid"] == [10, 10, 10]
    assert intent["orientation"] == {"policy": "minimal_twist", "tangent": [1, 0, 0]}


@pytest.mark.parametrize("with_source", [False, True])
def test_legacy_world_axes_open_apply_never_upgrades_orientation(with_source):
    document = new_draft(preserve=True).candidate()
    feature = document["features"][-1]
    feature["support_intent"].pop("orientation")
    feature["support_intent"].pop("source_feature", None)
    if not with_source:
        feature["support_intent"].pop("source_signature")
    saved = copy.deepcopy(document)
    assert edit.orientation_choice(feature["support_intent"]) == "WORLD_AXES"
    for orientation in (None, "WORLD_AXES"):
        candidate = edit.edit_support_candidate(
            document,
            feature["id"],
            "PRESERVE_PLANE",
            "block",
            "block/face/cap.end",
            exact_result(),
            orientation=orientation,
        )
        assert candidate == saved
        assert document == saved


def test_orientation_choices_are_explicit_and_preserve_existing_saved_tangent():
    document = new_draft(preserve=True).candidate()
    feature = document["features"][-1]
    feature["support_intent"]["orientation"]["tangent"] = [0, 1, 0]
    saved = copy.deepcopy(document)
    assert edit.orientation_choice(feature["support_intent"]) == "MINIMAL_TWIST"
    assert edit.orientation_choice(None) == "MINIMAL_TWIST"
    for orientation in (None, "MINIMAL_TWIST"):
        assert (
            edit.edit_support_candidate(
                document,
                feature["id"],
                "PRESERVE_PLANE",
                "block",
                "block/face/cap.end",
                exact_result(),
                orientation=orientation,
            )
            == saved
        )
    world = edit.edit_support_candidate(
        document,
        feature["id"],
        "PRESERVE_PLANE",
        "block",
        "block/face/cap.end",
        exact_result(),
        orientation="WORLD_AXES",
    )
    assert "orientation" not in world["features"][-1]["support_intent"]
    minimal = edit.edit_support_candidate(
        world,
        feature["id"],
        "PRESERVE_PLANE",
        "block",
        "block/face/cap.end",
        exact_result(),
        orientation="MINIMAL_TWIST",
    )
    assert minimal["features"][-1]["support_intent"]["orientation"] == {
        "policy": "minimal_twist",
        "tangent": [1, 0, 0],
    }
    assert minimal["features"][-1]["sketch"] == feature["sketch"]
    strict = edit.edit_support_candidate(
        document,
        feature["id"],
        "STRICT",
        "block",
        "block/face/cap.end",
        exact_result(),
        orientation="MINIMAL_TWIST",
        reset_frame=True,
    )
    assert "support_intent" not in strict["features"][-1]
    assert document == saved


def test_antiparallel_frame_reset_is_explicit_detached_and_stays_reset_on_reopen():
    document = new_draft(preserve=True).candidate()
    feature = document["features"][-1]
    saved = copy.deepcopy(document)
    current = exact_result()
    signature = current["features"][0]["topology"][0]["signature"]
    signature.update(normal=[0, 0, -1], centroid=[10, 10, -4], area=500)
    with pytest.raises(ValueError, match="antiparallel"):
        edit.edit_support_candidate(
            document,
            feature["id"],
            "PRESERVE_PLANE",
            "block",
            "block/face/cap.end",
            current,
            orientation="MINIMAL_TWIST",
        )
    reset = edit.edit_support_candidate(
        document,
        feature["id"],
        "PRESERVE_PLANE",
        "block",
        "block/face/cap.end",
        current,
        orientation="MINIMAL_TWIST",
        reset_frame=True,
    )
    reset_feature = reset["features"][-1]
    assert reset_feature["support_intent"]["signature"] == signature
    assert reset_feature["support_intent"]["source_signature"] == signature
    assert reset_feature["support_intent"]["orientation"] == {
        "policy": "minimal_twist",
        "tangent": [1, 0, 0],
    }
    assert reset_feature["sketch"] == feature["sketch"]
    assert (
        edit.edit_support_candidate(
            reset,
            feature["id"],
            "PRESERVE_PLANE",
            "block",
            "block/face/cap.end",
            current,
            orientation="MINIMAL_TWIST",
        )
        == reset
    )
    assert document == saved
    # The alternate explicit correction keeps the old baseline but opts out of transport.
    world = edit.edit_support_candidate(
        document,
        feature["id"],
        "PRESERVE_PLANE",
        "block",
        "block/face/cap.end",
        current,
        orientation="WORLD_AXES",
    )
    assert "orientation" not in world["features"][-1]["support_intent"]
    assert world["features"][-1]["support_intent"]["signature"]["normal"] == [0, 0, 1]


def test_orientation_edit_rejects_unknown_choices_and_incompatible_reset():
    document = new_draft(preserve=True).candidate()
    feature = document["features"][-1]
    for options in (
        {"orientation": "GUESS"},
        {"reset_frame": 1},
        {"orientation": "WORLD_AXES", "reset_frame": True},
    ):
        with pytest.raises(ValueError):
            edit.edit_support_candidate(
                document,
                feature["id"],
                "PRESERVE_PLANE",
                "block",
                "block/face/cap.end",
                exact_result(),
                **options,
            )


def test_exact_capture_failure_never_downgrades_to_legacy_intent(monkeypatch):
    document = new_draft().candidate()
    feature = document["features"][-1]
    saved = copy.deepcopy(document)

    def refused(*args):
        raise ValueError("Competing or aliased Cut source")

    monkeypatch.setattr(edit, "capture_support_intent", refused)
    with pytest.raises(ValueError, match="aliased"):
        edit.edit_support_candidate(
            document, feature["id"], "PRESERVE_PLANE", "block", "block/face/cap.end", exact_result()
        )
    assert document == saved
