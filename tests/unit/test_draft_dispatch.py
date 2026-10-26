"""One scene slot dispatches strict, independent, lossless editor codecs."""

import hashlib
import importlib
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_draft_dispatch_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
d = importlib.import_module(PACKAGE + ".draft_dispatch")
g = importlib.import_module(PACKAGE + ".general_sketch_draft")
a = importlib.import_module(PACKAGE + ".general_authoring")
BASE = '{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{},"features":[],"active_feature":null}\n'
RAW_INPUT = " \t invalid + ( 半径 🛠 \n"


def rectangle():
    draft = d.RectangleDraft(BASE)
    draft.first_point((2, 3))
    draft.second_point((42, 33))
    draft.pending_dimensions = {"width": " 60mm +( ", "height": "30", "fix_corner": False}
    return draft


def general():
    draft = d.GeneralSketchDraft(BASE)
    _, circle = draft.execute(g.AddCircle(g.PointSeed(2, 3), 4)).entity_ids
    constraint = draft.execute(g.AddRelation("radius", (circle,), value=4)).entity_ids[0]
    draft.begin_edit(constraint)
    draft.update_edit(" 60mm +( ")
    return draft


def authoring(*, proposal="line", pending=True):
    command = d.GeneralSketchDraft(BASE)
    first, second, line = command.execute(
        g.AddLine(g.PointSeed(0, 0), g.PointSeed(3, 4))
    ).entity_ids
    center, circle = command.execute(g.AddCircle(g.PointSeed(8, 9), 4.125)).entity_ids
    distance = command.execute(g.AddRelation("distance", (first, second), value=5)).constraint_id
    radius = command.execute(g.AddRelation("radius", (circle,), value="4 + 0.125")).constraint_id
    state = a.GeneralSketchAuthoringState(command)
    state.select((("line", line), ("circle", circle)))
    state.place_annotation(distance, (2, -3))
    state.place_annotation(radius, (7.25, -8))
    if proposal == "line":
        state.begin_line(g.PointRef(second), (12.25, -3))
    else:
        state.begin_circle(g.PointRef(center), 6.25)
    state.select_tool("Dimension")
    if pending:
        state.command_draft.begin_edit(radius)
        state.command_draft.update_edit(RAW_INPUT)
    return state


@pytest.mark.parametrize(
    "factory,kind,version,phase,codec",
    [
        (rectangle, d.RECTANGLE, 1, "DIMENSIONS", d.draft_store),
        (general, d.GENERAL, 1, "DIMENSION_EDIT", d.general_draft_store),
        (authoring, d.GENERAL, 2, "DIMENSION_EDIT", d.general_authoring_store),
    ],
)
def test_exact_codec_bytes_and_pending_text_survive(factory, kind, version, phase, codec):
    original = factory()
    encoded = d.dumps(original)
    assert encoded == codec.dumps(original)
    info = d.inspect(encoded)
    assert (info.kind, info.phase, info.pending_input) == (kind, phase, True)
    assert info.schema_version == version
    assert info.is_current(BASE) and not info.is_current(BASE.rstrip())
    restored = d.restore(encoded, BASE)
    assert type(restored) is type(original)
    assert d.dumps(restored) == encoded
    with pytest.raises(d.SnapshotError, match="different committed"):
        d.restore(encoded, BASE.rstrip())
    assert d.dumps(original) == encoded


@pytest.mark.parametrize("factory", [rectangle, general, authoring])
@pytest.mark.parametrize(
    "change",
    [
        lambda x: x.update(kind="future"),
        lambda x: x.update(schema_version=True),
        lambda x: x.update(schema_version=3),
        lambda x: x.update(extra=1),
        lambda x: x.update(base_sha256="0" * 64),
    ],
)
def test_unknown_or_forged_envelopes_do_not_fall_through(factory, change):
    envelope = json.loads(d.dumps(factory()))
    change(envelope)
    text = json.dumps(envelope)
    for action in (d.inspect, lambda value: d.restore(value, BASE)):
        with pytest.raises(d.SnapshotError):
            action(text)
    assert json.loads(text) == envelope


@pytest.mark.parametrize(
    "factory,wrong_kind",
    [(rectangle, d.GENERAL), (general, d.RECTANGLE), (authoring, d.RECTANGLE)],
)
def test_cross_kind_payload_is_rejected(factory, wrong_kind):
    envelope = json.loads(d.dumps(factory()))
    envelope["kind"] = wrong_kind
    with pytest.raises(d.SnapshotError):
        d.inspect(json.dumps(envelope))


@pytest.mark.parametrize(
    "text",
    [
        None,
        {},
        [],
        "null",
        "[]",
        "{",
        '{"kind":"rectangle_ui_draft","kind":"general_sketch_ui_draft","schema_version":1}',
        '{"kind":"rectangle_ui_draft","schema_version":1,"value":NaN}',
        "\ud800",
        "[" * 2000 + "]" * 2000,
    ],
)
def test_invalid_input_is_bounded_and_read_only(text):
    with pytest.raises(d.SnapshotError):
        d.inspect(text)


def test_byte_budget_and_unsupported_live_object():
    with pytest.raises(d.SnapshotError, match="byte limit"):
        d.inspect('"' + "é" * (d.MAX_SNAPSHOT_BYTES // 2) + '"')
    with pytest.raises(d.SnapshotError, match="bounded"):
        d.inspect(" " * (d.MAX_SNAPSHOT_BYTES + 1))
    with pytest.raises(d.SnapshotError, match="type"):
        d.dumps(object())


def test_import_has_no_blender_native_or_transport_dependency():
    script = f"""
import sys, types, importlib
p = types.ModuleType('isolated'); p.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules['isolated'] = p
importlib.import_module('isolated.draft_dispatch')
assert not any(n == 'bpy' or n == 'slvs' or n.startswith('OCP') or n.endswith('.sidecar_job') for n in sys.modules)
"""
    subprocess.run([sys.executable, "-S", "-c", script], check=True, capture_output=True)


@pytest.mark.parametrize("field", ["width_text", "height_text", "error"])
def test_decoded_lone_surrogate_cannot_be_advertised_as_resumable(field):
    envelope = json.loads(d.dumps(rectangle()))
    envelope["draft"][field] = "bad\ud800text"
    encoded = json.dumps(envelope)
    assert encoded.encode("utf-8")  # JSON bytes alone are valid UTF-8.
    for action in (d.inspect, lambda text: d.restore(text, BASE)):
        with pytest.raises(d.SnapshotError):
            action(encoded)
    assert json.loads(encoded)["draft"][field] == "bad\ud800text"


def test_dump_invalid_unicode_uses_public_snapshot_error():
    draft = rectangle()
    draft.width_text = "\ud800"
    with pytest.raises(d.SnapshotError):
        d.dumps(draft)


@pytest.mark.parametrize(
    "factory,expected_bytes,expected_hash",
    [
        (rectangle, 873, "955cf255879ba7a996a54c6e388cd78344abe54760a932f71038763f69acc97c"),
        (general, 2491, "074c3b4a0eb88c45eb5bfcc43653d32d00586bfba6b89d00456a3db5133e48e4"),
    ],
)
def test_v1_snapshot_bytes_match_audited_3951d39(factory, expected_bytes, expected_hash):
    # Independent golden bytes from the frozen shared-owner audit source.
    encoded = d.dumps(factory()).encode("utf-8")
    assert len(encoded) == expected_bytes
    assert hashlib.sha256(encoded).hexdigest() == expected_hash


@pytest.mark.parametrize("proposal", ["line", "circle"])
@pytest.mark.parametrize("pending", [False, True])
def test_v2_retains_separate_ui_and_exact_command_intent(proposal, pending):
    original = authoring(proposal=proposal, pending=pending)
    command = original.command_draft.checkpoint_payload()
    ui = original.ui_payload()
    encoded = d.dumps(original)
    restored = d.restore(encoded, BASE)
    assert type(restored) is a.GeneralSketchAuthoringState
    assert restored is not original and restored.command_draft is not original.command_draft
    assert restored.command_draft.checkpoint_payload() == command
    assert restored.ui_payload() == ui
    assert restored.candidate() == original.candidate()
    assert restored.revision == original.revision
    assert restored.tool == "Dimension"
    assert restored.proposal["kind"] == proposal
    assert len(restored.annotations) == 2
    assert not restored.command_draft.has_current_solution
    assert not restored.command_draft.has_verified_trial
    info = d.inspect(encoded)
    assert info.pending_input is pending
    assert info.phase == ("DIMENSION_EDIT" if pending else "EDITING")
    assert info.document_json == BASE and info.feature_id == restored.feature_id
    assert set(vars(info)) == {
        "kind",
        "document_json",
        "feature_id",
        "phase",
        "pending_input",
        "schema_version",
    }
    if pending:
        assert restored.command_draft.pending_edit.raw_text == RAW_INPUT
        with pytest.raises(g.DraftError, match="driving field"):
            restored.resume_proposal()
    else:
        for _ in range(3):
            observed = restored.resume_proposal()
            assert observed == ui["proposal"]
            observed["anchor"] = {"kind": "new", "position": [100, 100]}
    assert d.dumps(restored) == encoded
    assert d.dumps(original) == encoded
    assert not any(
        key in encoded
        for key in (
            "pointer_capture",
            "input_lease",
            "gesture_grab",
            "queuedEnter",
            "process_token",
        )
    )


def test_v1_restoration_never_implicitly_constructs_authoring_wrapper():
    original = general()
    encoded = d.dumps(original)
    restored = d.restore(encoded, BASE)
    assert type(restored) is g.GeneralSketchDraft
    assert d.dumps(restored) == encoded
    # Only an explicit caller-selected wrapper writes v2; command bytes do not change.
    wrapped = a.GeneralSketchAuthoringState.from_v1_draft(restored)
    assert json.loads(d.dumps(wrapped))["schema_version"] == 2
    assert wrapped.ui_payload() == a.empty_ui()
    assert d.dumps(wrapped.command_draft) == encoded


def test_mixed_inspection_is_order_independent_and_old_descriptor_callers_still_work():
    sources = [rectangle(), general(), authoring(pending=False), authoring()]
    encoded = [d.dumps(source) for source in sources]
    expected = [d.inspect(raw) for raw in encoded]
    for index in (2, 0, 3, 1, 0, 2, 1, 3):
        assert d.inspect(encoded[index]) == expected[index]
        assert d.dumps(d.restore(encoded[index], BASE)) == encoded[index]
    assert [info.schema_version for info in expected] == [1, 1, 2, 2]
    assert [info.pending_input for info in expected] == [True, True, False, True]
    assert d.DraftDescriptor(d.GENERAL, BASE, "sketch_1", "EDITING", False).schema_version == 1


@pytest.mark.parametrize("factory", [rectangle, general, authoring])
def test_wrong_version_never_migrates_an_existing_payload(factory):
    envelope = json.loads(d.dumps(factory()))
    envelope["schema_version"] = 1 if envelope["schema_version"] == 2 else 2
    raw = json.dumps(envelope)
    for action in (d.inspect, lambda value: d.restore(value, BASE)):
        with pytest.raises(d.SnapshotError):
            action(raw)
        assert json.loads(raw) == envelope


@pytest.mark.parametrize("factory", [rectangle, general, authoring])
def test_dumps_requires_the_exact_supported_type(factory):
    original = factory()
    subclass = type("UnregisteredDraft", (type(original),), {})
    original.__class__ = subclass
    with pytest.raises(d.SnapshotError, match="type"):
        d.dumps(original)


@pytest.mark.parametrize("field", ["pending", "base", "tool", "selection", "unknown_key"])
def test_v2_decoded_surrogate_rejects_publicly_and_retains_raw_bytes(field):
    envelope = json.loads(d.dumps(authoring()))
    if field == "pending":
        envelope["draft"]["pending_edit"]["raw_text"] = "bad\ud800text"
    elif field == "base":
        envelope["draft"]["document_json"] += "\ud800"
    elif field == "tool":
        envelope["ui"]["tool"] = "\ud800"
    elif field == "selection":
        envelope["ui"]["selection"][0]["id"] += "\ud800"
    else:
        envelope["ui"]["\ud800"] = "unknown"
    raw = json.dumps(envelope, ensure_ascii=True)
    before = raw.encode("utf-8")
    for action in (d.inspect, lambda value: d.restore(value, BASE)):
        with pytest.raises(d.SnapshotError):
            action(raw)
        assert raw.encode("utf-8") == before


def test_v2_malformed_ui_is_not_hidden_by_valid_nested_command():
    envelope = json.loads(d.dumps(authoring()))
    envelope["ui"]["schema_version"] = 2
    raw = json.dumps(envelope)
    for action in (d.inspect, lambda value: d.restore(value, BASE)):
        with pytest.raises(d.SnapshotError):
            action(raw)
    assert json.loads(raw) == envelope
