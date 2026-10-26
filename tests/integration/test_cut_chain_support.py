"""Source-bound logical planes survive proven Cut chains, never regain face identity."""

import copy
import importlib
import json
import math
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest
from test_split_support_intent import rows, split_document

from mechanical_cad.cut_support_ancestry import resolve_replay_support
from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document
from mechanical_cad.sidecar import process_request
from mechanical_cad.support_intent import capture_orientation
from mechanical_cad.support_plane import rotate

ROOT = Path(__file__).resolve().parents[2]
FACE = "block/face/cap.end"


def chain_document(count=2, *, bound=True, strict=False):
    """Parallel 2 mm slots, each removing 120 mm3 without disconnecting the block."""
    data = split_document().to_dict()
    attached, boss = data["features"][-2:]
    data["features"] = data["features"][:2]
    base = "block"
    for index, x in enumerate((4, 9, 14)[:count], 1):
        profile, tool, cut = f"slot_{index}_profile", f"slot_{index}_tool", f"cut_{index}"
        data["features"].extend(
            [
                {
                    "id": profile,
                    "kind": "sketch_rectangle",
                    "params": {"width": 2, "height": 22, "x": x, "y": -1, "z": 7},
                },
                {
                    "id": tool,
                    "kind": "extrude",
                    "params": {"length": 5},
                    "inputs": {"profile": profile},
                },
                {"id": cut, "kind": "cut", "inputs": {"base": base, "tool": tool}},
            ]
        )
        base = cut
    attached["inputs"]["support"] = base
    if strict:
        attached.pop("support_intent")
    elif bound:
        intent = attached["support_intent"]
        intent["source_feature"] = "block"
        intent["source_signature"] = copy.deepcopy(intent["signature"])
        intent["orientation"] = capture_orientation(intent)
    data["features"].extend([attached, boss])
    return Document.from_dict(data)


def feature(data, identifier):
    return next(row for row in data["features"] if row["id"] == identifier)


def resolve(document, result):
    source = feature(document.to_dict(), "attached")
    return resolve_replay_support(
        source["support_face"],
        source.get("support_intent"),
        source["inputs"]["support"],
        result["features"],
    )


def lineage_faces(result, identifier):
    # Construction labels identify the lineage to ASSERT, not a selected geometry guess.
    return [
        face
        for face in feature(result, identifier)["topology"]
        if face["feature_id"] == "block" and face["role"] == "cap.end"
    ]


@pytest.fixture(scope="module")
def client():
    package = types.ModuleType("mcad_cut_chain_contracts")
    package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
    sys.modules[package.__name__] = package
    return importlib.import_module(package.__name__ + ".operation_contracts")


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("count", [2, 3])
def test_successive_cuts_preserve_source_plane_after_dimension_edits(version, count):
    original = chain_document(count)
    for width, depth in ((20, 10), (24, 11), (20, 10)):
        data = original.to_dict()
        feature(data, "footprint")["params"]["width"] = width
        data["parameters"]["depth"] = depth
        document = Document.from_json(Document.from_dict(data).to_json())
        canonical = document.to_json()
        kernel = OCPKernel()
        replay = regenerate(document, kernel, result_version=version)
        assert replay.ok, replay.result
        result = rows(replay)
        for index in range(1, count + 1):
            cut = result[f"cut_{index}"]
            assert cut["stats"]["volume"] == pytest.approx(
                width * 20 * depth - index * 2 * 20 * (depth - 7)
            )
            assert cut["cut_ancestry"]["version"] == 1
            descendants = lineage_faces(replay.result, cut["id"])
            assert len(descendants) == index + 1
            assert all(face["id"].startswith("snapshot:") for face in descendants)
            assert all(face["provenance"]["semantic_status"] == "split" for face in descendants)
            assert all(face["id"] != FACE for face in descendants)
        plane = result["attached"]["support_plane"]
        assert plane["origin"] == pytest.approx([width / 2, 10, depth])
        assert rotate(plane["quaternion"], [0, 0, 1]) == pytest.approx([0, 0, 1])
        assert result["attached"]["sketch"]["solved"]["plane"] == plane
        assert result["boss"]["stats"]["volume"] == pytest.approx(8 * math.pi)
        assert kernel.manufacturing_check(replay.shapes[f"cut_{count}"])["mesh"]["watertight"]
        signature, decision = resolve(document, replay.result)
        assert signature["centroid"] == pytest.approx(plane["origin"])
        assert decision["status"] == "assumed"
        assert decision["cut_count"] == count
        assert decision["descendant_count"] == count + 1
        assert decision["source_feature"] == "block"
        assert decision["identity_status"] == "split"
        assert document.to_json() == canonical
        assert "snapshot:" not in canonical and "cut_ancestry" not in canonical


def test_real_saved_modified_face_offset_survives_three_cuts_and_edit():
    initial = chain_document(1, strict=True).to_dict()
    feature(initial, "slot_1_profile")["params"]["height"] = 10
    before = regenerate(Document.from_dict(initial), OCPKernel(), result_version=3)
    assert before.ok, before.result
    selected = next(
        face["signature"] for face in rows(before)["cut_1"]["topology"] if face["id"] == FACE
    )
    baseline = next(
        face["signature"] for face in rows(before)["block"]["topology"] if face["id"] == FACE
    )
    delta = [selected["centroid"][i] - baseline["centroid"][i] for i in range(3)]
    assert math.hypot(*delta) > 0.1  # The saved anchor actually differs from the source.
    data = chain_document(3).to_dict()
    intent = feature(data, "attached")["support_intent"]
    intent.update(signature=selected, source_signature=baseline)
    for width, depth in ((20, 10), (24, 11), (20, 10)):
        feature(data, "footprint")["params"]["width"] = width
        data["parameters"]["depth"] = depth
        document = Document.from_json(Document.from_dict(data).to_json())
        replay = regenerate(document, OCPKernel(), result_version=3)
        assert replay.ok, replay.result
        plane = rows(replay)["attached"]["support_plane"]
        assert plane["origin"] == pytest.approx([width / 2 + delta[0], 10 + delta[1], depth])
        assert plane["quaternion"] == pytest.approx(
            rows(before)["attached"]["support_plane"]["quaternion"]
        )
        assert rows(replay)["boss"]["stats"]["volume"] == pytest.approx(8 * math.pi)
        assert resolve(document, replay.result)[1]["descendant_count"] == 4


@pytest.mark.parametrize("version", [2, 3])
def test_partial_deletion_keeps_one_snapshot_without_inventing_stable_identity(version):
    data = chain_document().to_dict()
    feature(data, "slot_2_profile")["params"].update(x=-1, width=7)
    document = Document.from_json(Document.from_dict(data).to_json())
    kernel = OCPKernel()
    replay = regenerate(document, kernel, result_version=version)
    assert replay.ok, replay.result
    result = rows(replay)
    assert result["cut_2"]["stats"]["volume"] == pytest.approx(3640)
    assert kernel.manufacturing_check(replay.shapes["cut_2"])["mesh"]["watertight"]
    first = lineage_faces(replay.result, "cut_1")
    final = lineage_faces(replay.result, "cut_2")
    assert len(first) == 2 and len(final) == 1
    assert final[0]["id"].startswith("snapshot:")
    assert final[0]["provenance"]["semantic_status"] == "split"
    assert final[0]["signature"]["centroid"] != pytest.approx([10, 10, 10])
    deleted = [
        record
        for record in result["cut_2"]["cut_ancestry"]["sources"]
        if record["port"] == "base"
        and record["source_id"] in {face["id"] for face in first}
        and record["deleted"]
        and not record["modified"]
        and not record["unchanged"]
    ]
    assert len(deleted) == 1
    signature, decision = resolve(document, replay.result)
    assert signature["centroid"] == pytest.approx([10, 10, 10])
    assert decision["descendant_count"] == 1 and decision["identity_status"] == "split"
    assert result["attached"]["support_plane"]["origin"] == pytest.approx([10, 10, 10])


@pytest.mark.parametrize("version", [2, 3])
def test_complete_plane_deletion_fails_even_when_solid_and_new_top_survive(version, client):
    data = chain_document().to_dict()
    feature(data, "slot_2_profile")["params"].update(x=-1, width=22)
    document = Document.from_dict(data)
    kernel = OCPKernel()
    replay = regenerate(document, kernel, result_version=version)
    result = rows(replay)
    assert not replay.ok
    assert result["cut_2"]["status"] == "ok"
    assert result["cut_2"]["stats"]["volume"] == pytest.approx(2800)
    assert kernel.manufacturing_check(replay.shapes["cut_2"])["mesh"]["watertight"]
    assert lineage_faces(replay.result, "cut_2") == []
    assert result["attached"]["status"] == "failed"
    assert result["attached"]["support_plane"] is None
    assert "no surviving fragments" in result["attached"]["error"]["message"]
    assert result["boss"]["status"] == "blocked"
    with pytest.raises(ValueError, match="no surviving fragments"):
        resolve(document, replay.result)
    request = {
        "protocol_version": 1,
        "action": "replay",
        "document": data,
        "result_version": version,
    }
    client.validate_response(request, process_request(request))


@pytest.mark.parametrize("count,legacy_ok", [(1, True), (2, False), (3, False)])
def test_legacy_intent_is_not_silently_rebound_and_strict_still_refuses(count, legacy_ok):
    legacy = chain_document(count, bound=False)
    canonical = legacy.to_json()
    replay = regenerate(Document.from_json(canonical), OCPKernel(), result_version=3)
    assert replay.ok is legacy_ok, replay.result
    assert "source_feature" not in canonical
    assert legacy.to_json() == canonical
    strict = regenerate(chain_document(count, strict=True), OCPKernel(), result_version=3)
    assert not strict.ok
    assert rows(strict)["attached"]["status"] == "failed"
    assert rows(strict)["boss"]["status"] == "blocked"


def test_saved_document_replays_in_fresh_process_without_transient_ancestry(tmp_path, client):
    document = chain_document(3)
    path = tmp_path / "source_bound_chain.mcad.json"
    path.write_text(document.to_json(), encoding="utf-8")
    restored = Document.from_json(path.read_text(encoding="utf-8"))
    request = {
        "protocol_version": 1,
        "result_version": 3,
        "action": "replay",
        "document": restored.to_dict(),
    }
    process = subprocess.run(
        [sys.executable, "-m", "mechanical_cad.sidecar"],
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        timeout=60,
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert process.returncode == 0, process.stderr
    response = json.loads(process.stdout)
    assert response["ok"], response
    client.validate_response(request, response)
    assert feature(response["result"], "attached")["support_plane"]["origin"] == pytest.approx(
        [10, 10, 10]
    )
    assert feature(response["result"], "cut_3")["stats"]["volume"] == pytest.approx(3640)
    assert resolve(restored, response["result"])[1]["cut_count"] == 3
    saved = path.read_text(encoding="utf-8")
    assert "snapshot:" not in saved and "cut_ancestry" not in saved
    assert saved == restored.to_json()


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("action", ["replay", "solve_sketch"])
def test_independent_client_accepts_real_chain_and_refuses_changed_plane(version, action, client):
    request = {
        "protocol_version": 1,
        "action": action,
        "document": chain_document(3).to_dict(),
        "result_version": version,
    }
    if action == "solve_sketch":
        request["feature_id"] = "attached"
    response = process_request(request)
    assert response["ok"], response
    client.validate_response(request, response)
    forged = copy.deepcopy(response)
    if action == "replay":
        plane = feature(forged["result"], "attached")["support_plane"]
    else:
        context = forged["result"]["support_context"]
        assert context["document"]["active_feature"] == "cut_3"
        assert "attached" not in {row["id"] for row in context["document"]["features"]}
        plane = context["plane"]
    assert plane["origin"] == pytest.approx([10, 10, 10])
    plane["origin"][0] += 1
    with pytest.raises(ValueError):
        client.validate_response(request, forged)


@pytest.fixture(
    scope="module", params=[(2, "replay"), (3, "replay"), (2, "solve_sketch"), (3, "solve_sketch")]
)
def validated_chain_response(request, client):
    version, action = request.param
    operation = {
        "protocol_version": 1,
        "action": action,
        "result_version": version,
        "document": chain_document(3).to_dict(),
    }
    if action == "solve_sketch":
        operation["feature_id"] = "attached"
    response = process_request(operation)
    assert response["ok"], response
    client.validate_response(operation, response)
    return operation, response


def support_result(operation, response):
    if operation["action"] == "solve_sketch":
        return response["result"]["support_context"]["replay"]
    return response["result"]


def corrupt_ancestry(result, corruption):
    cut = feature(result, "cut_2")
    sources = cut["cut_ancestry"]["sources"]
    descendant = lineage_faces(result, "cut_2")[0]
    record = next(
        row
        for row in sources
        if row["port"] == "base" and row["source_id"] == descendant["provenance"]["source_id"]
    )
    relation = next(key for key in ("modified", "unchanged") if descendant["id"] in record[key])
    if corruption == "missing_ledger":
        cut["cut_ancestry"] = None
    elif corruption == "missing_source":
        sources.remove(record)
    elif corruption == "missing_image":
        record[relation].remove(descendant["id"])
    elif corruption == "unknown_image":
        record[relation].append("snapshot:cut_2:face:99999")
    elif corruption == "duplicate_image":
        record[relation].append(descendant["id"])
    elif corruption == "duplicate_source":
        sources.append(copy.deepcopy(record))
    elif corruption == "generated_source":
        record["generated"].append(descendant["id"])
    elif corruption == "competing_generated":
        other = next(row for row in sources if row["port"] == "tool")
        other["generated"].append(descendant["id"])
    elif corruption == "competing_modified":
        other = next(row for row in sources if row["port"] == "base" and row is not record)
        other["modified"].append(descendant["id"])
    elif corruption == "aliased_output":
        cut["topology"].append(copy.deepcopy(descendant))
    elif corruption == "missing_output":
        cut["topology"].remove(descendant)
    elif corruption == "stale_operation":
        descendant["provenance"]["operation_id"] = "cut_1"
    elif corruption == "forged_stable":
        descendant["provenance"]["semantic_status"] = "stable"
    elif corruption == "off_plane":
        descendant["signature"]["centroid"][2] += 0.5
    elif corruption == "opposite_normal":
        descendant["signature"]["normal"][2] *= -1
    elif corruption == "stale_ledger":
        cut["cut_ancestry"] = copy.deepcopy(feature(result, "cut_1")["cut_ancestry"])
    else:
        raise AssertionError(corruption)


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_ledger",
        "missing_source",
        "missing_image",
        "unknown_image",
        "duplicate_image",
        "duplicate_source",
        "generated_source",
        "competing_generated",
        "competing_modified",
        "aliased_output",
        "missing_output",
        "stale_operation",
        "forged_stable",
        "off_plane",
        "opposite_normal",
        "stale_ledger",
    ],
)
def test_core_and_full_client_reject_incomplete_stale_or_forged_chain(
    corruption,
    validated_chain_response,
    client,
):
    operation, response = validated_chain_response
    forged = copy.deepcopy(response)
    result = support_result(operation, forged)
    corrupt_ancestry(result, corruption)
    document = Document.from_dict(operation["document"])
    with pytest.raises(ValueError):
        resolve(document, result)
    with pytest.raises(ValueError):
        client.validate_response(operation, forged)


def test_reordering_and_consistent_snapshot_relabeling_does_not_change_workplane(
    validated_chain_response,
    client,
):
    operation, response = validated_chain_response
    reordered = copy.deepcopy(response)
    result = support_result(operation, reordered)
    document = Document.from_dict(operation["document"])
    expected = resolve(document, result)
    renamed = {}
    for row in result["features"]:
        if row["kind"] != "cut":
            continue
        row["topology"].reverse()
        for index, face in enumerate(row["topology"]):
            if face["id"].startswith("snapshot:"):
                renamed[face["id"]] = f"snapshot:{row['id']}:face:{index}"

    def rename(value):
        if isinstance(value, dict):
            return {key: rename(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rename(item) for item in value]
        return renamed.get(value, value) if isinstance(value, str) else value

    rewritten = rename(reordered)
    assert resolve(document, support_result(operation, rewritten)) == expected
    client.validate_response(operation, rewritten)


def test_new_authoring_binds_earliest_source_and_review_reset_strict_are_explicit(client):
    edit = importlib.import_module(client.__package__ + ".support_intent_edit")
    data = chain_document(3, strict=True).to_dict()
    for index in range(1, 4):
        feature(data, f"slot_{index}_profile")["params"]["height"] = 10
    original = Document.from_dict(data)
    before = regenerate(original, OCPKernel(), result_version=3)
    assert before.ok, before.result
    selected = next(face for face in rows(before)["cut_3"]["topology"] if face["id"] == FACE)
    assert selected["provenance"]["semantic_status"] == "stable"
    intent = edit.capture_support_intent(before.result, "cut_3", FACE)
    assert intent["source_feature"] == "block"
    assert intent["signature"] == selected["signature"]
    baseline = next(
        face["signature"] for face in rows(before)["block"]["topology"] if face["id"] == FACE
    )
    assert intent["source_signature"] == baseline
    assert math.dist(intent["signature"]["centroid"], baseline["centroid"]) > 0.1
    saved = original.to_dict()
    captured = edit.edit_support_candidate(
        saved, "attached", "PRESERVE_PLANE", "cut_3", FACE, before.result
    )
    assert saved == original.to_dict()
    assert feature(captured, "attached")["support_intent"] == intent
    assert feature(captured, "attached")["sketch"] == feature(saved, "attached")["sketch"]
    strict = edit.edit_support_candidate(
        captured, "attached", "STRICT", "cut_3", FACE, before.result
    )
    assert strict == saved
    assert (
        edit.support_decision(feature(captured, "attached"), before.result)["identity_status"]
        == "stable"
    )

    for index in range(1, 4):
        feature(captured, f"slot_{index}_profile")["params"]["height"] = 22
    feature(captured, "footprint")["params"]["width"] = 24
    captured["parameters"]["depth"] = 11
    document = Document.from_json(Document.from_dict(captured).to_json())
    replay = regenerate(document, OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    saved = document.to_dict()
    attached = feature(saved, "attached")
    delta = [intent["signature"]["centroid"][i] - baseline["centroid"][i] for i in range(3)]
    plane = rows(replay)["attached"]["support_plane"]
    assert plane["origin"] == pytest.approx([12 + delta[0], 10 + delta[1], 11])
    decision = edit.support_decision(attached, replay.result)
    assert decision["cut_count"] == 3 and decision["identity_status"] == "split"
    assert "No fragment was chosen" in decision["reason"]
    reviewed = edit.edit_support_candidate(
        saved, "attached", "PRESERVE_PLANE", "cut_3", FACE, replay.result
    )
    assert reviewed == saved
    reset = edit.edit_support_candidate(
        saved,
        "attached",
        "PRESERVE_PLANE",
        "cut_3",
        FACE,
        replay.result,
        orientation="MINIMAL_TWIST",
        reset_frame=True,
    )
    assert saved == document.to_dict()
    reset_intent = feature(reset, "attached")["support_intent"]
    assert reset_intent["source_feature"] == "block"
    assert reset_intent["signature"]["centroid"] == pytest.approx(plane["origin"])
    restored = regenerate(Document.from_dict(reset), OCPKernel(), result_version=3)
    assert restored.ok, restored.result
    assert rows(restored)["attached"]["support_plane"]["origin"] == pytest.approx(plane["origin"])
    # Strict cannot bless a snapshot face. Changing explicitly to the unchanged
    # bottom face succeeds and does not modify the user's local sketch placement.
    with pytest.raises(ValueError):
        edit.edit_support_candidate(saved, "attached", "STRICT", "cut_3", FACE, replay.result)
    strict_bottom = edit.edit_support_candidate(
        saved,
        "attached",
        "STRICT",
        "cut_3",
        "block/face/cap.start",
        replay.result,
    )
    assert "support_intent" not in feature(strict_bottom, "attached")
    assert feature(strict_bottom, "attached")["sketch"] == attached["sketch"]
    fixed = regenerate(Document.from_dict(strict_bottom), OCPKernel(), result_version=3)
    assert fixed.ok, fixed.result
    assert rows(fixed)["attached"]["support_plane"]["origin"][2] == pytest.approx(0)
    assert saved == document.to_dict()


@pytest.mark.parametrize("gap", ["transform_gap", "cloned_tool"])
def test_non_cut_gap_or_cloned_solid_operand_refuses_source_chain(gap, client):
    data = chain_document().to_dict()
    cut_index = next(index for index, row in enumerate(data["features"]) if row["id"] == "cut_2")
    data["features"].insert(
        cut_index,
        {
            "id": "copy",
            "kind": "transform",
            "params": {"x": 10 if gap == "cloned_tool" else 0},
            "inputs": {"base": "block" if gap == "cloned_tool" else "cut_1"},
        },
    )
    feature(data, "cut_2")["inputs"]["tool" if gap == "cloned_tool" else "base"] = "copy"
    document = Document.from_dict(data)
    replay = regenerate(document, OCPKernel(), result_version=3)
    assert rows(replay)["cut_2"]["status"] == "ok", replay.result
    assert rows(replay)["attached"]["status"] == "failed"
    assert rows(replay)["boss"]["status"] == "blocked"
    with pytest.raises(ValueError, match="aliased|continuous ordinary Cut"):
        resolve(document, replay.result)
    request = {"protocol_version": 1, "action": "replay", "document": data, "result_version": 3}
    client.validate_response(request, process_request(request))


@pytest.mark.parametrize("version", [2, 3])
def test_independent_cutter_extruded_from_attached_sketch_is_not_a_cloned_solid(version, client):
    data = chain_document().to_dict()
    cutter = copy.deepcopy(feature(data, "attached"))
    cutter["id"] = "cutter_sketch"
    cutter["inputs"]["support"] = "cut_1"
    tool_index = next(
        index for index, row in enumerate(data["features"]) if row["id"] == "slot_2_tool"
    )
    data["features"].insert(tool_index, cutter)
    feature(data, "slot_2_tool")["inputs"]["profile"] = "cutter_sketch"
    feature(data, "slot_2_tool")["params"]["length"] = -3
    document = Document.from_dict(data)
    replay = regenerate(document, OCPKernel(), result_version=version)
    assert replay.ok, replay.result
    assert rows(replay)["cut_2"]["stats"]["volume"] == pytest.approx(3880 - 12 * math.pi)
    assert rows(replay)["boss"]["stats"]["volume"] == pytest.approx(8 * math.pi)
    assert rows(replay)["attached"]["support_plane"]["origin"] == pytest.approx([10, 10, 10])
    assert resolve(document, replay.result)[1]["descendant_count"] == 2
    for action in ("replay", "solve_sketch"):
        request = {
            "protocol_version": 1,
            "action": action,
            "result_version": version,
            "document": data,
        }
        if action == "solve_sketch":
            request["feature_id"] = "attached"
        response = process_request(request)
        assert response["ok"], response
        client.validate_response(request, response)


@pytest.mark.parametrize("source", ["missing", "footprint", "slot_1_tool", "attached"])
def test_saved_binding_cannot_fall_back_to_another_available_source(source):
    data = chain_document().to_dict()
    feature(data, "attached")["support_intent"]["source_feature"] = source
    document = Document.from_dict(data)
    replay = regenerate(document, OCPKernel(), result_version=3)
    assert rows(replay)["cut_2"]["status"] == "ok"
    assert rows(replay)["attached"]["status"] == "failed"
    assert rows(replay)["boss"]["status"] == "blocked"
    with pytest.raises(ValueError):
        resolve(document, replay.result)
    assert feature(document.to_dict(), "attached")["support_intent"]["source_feature"] == source


def test_full_chain_validation_runs_without_native_kernel_or_site_packages(
    validated_chain_response,
):
    operation, response = validated_chain_response
    script = f"""
import importlib
import json
import sys
import types
package = types.ModuleType('isolated_cut_chain_client')
package.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules[package.__name__] = package
contracts = importlib.import_module(package.__name__ + '.operation_contracts')
operation, response = json.load(sys.stdin)
contracts.validate_response(operation, response)
assert not any(name == 'OCP' or name.startswith('OCP.') for name in sys.modules)
assert not any(name == 'mechanical_cad' or name.startswith('mechanical_cad.') for name in sys.modules)
print('native-free-chain-validated')
"""
    process = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", script],
        input=json.dumps([operation, response]),
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "native-free-chain-validated"


@pytest.mark.parametrize(
    "count,immediate_base_stable,expected_source",
    [(1, False, "block"), (2, True, "cut_1"), (3, False, "block")],
)
def test_explicit_strict_split_repair_creates_bound_intent_without_changing_saved_document(
    count,
    immediate_base_stable,
    expected_source,
    client,
):
    edit = importlib.import_module(client.__package__ + ".support_intent_edit")
    data = chain_document(count, strict=True).to_dict()
    if immediate_base_stable:
        feature(data, "slot_1_profile")["params"]["height"] = 10
    document = Document.from_dict(data)
    before = regenerate(document, OCPKernel(), result_version=3)
    assert rows(before)[f"cut_{count}"]["status"] == "ok"
    assert rows(before)["attached"]["status"] == "failed"
    saved = document.to_dict()
    repaired = edit.edit_support_candidate(
        saved,
        "attached",
        "PRESERVE_PLANE",
        f"cut_{count}",
        FACE,
        before.result,
    )
    assert saved == document.to_dict()
    intent = feature(repaired, "attached")["support_intent"]
    assert intent["source_feature"] == expected_source
    baseline = next(
        face["signature"]
        for face in rows(before)[expected_source]["topology"]
        if face["id"] == FACE
    )
    assert intent["signature"] == intent["source_signature"] == baseline
    if immediate_base_stable:
        assert baseline["centroid"] != pytest.approx([10, 10, 10])
    restored = Document.from_json(Document.from_dict(repaired).to_json())
    replay = regenerate(restored, OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    assert rows(replay)["attached"]["support_plane"]["origin"] == pytest.approx(
        baseline["centroid"]
    )
    assert resolve(restored, replay.result)[1]["source_feature"] == expected_source
    assert feature(repaired, "attached")["sketch"] == feature(saved, "attached")["sketch"]
    request = {"protocol_version": 1, "action": "replay", "result_version": 3, "document": repaired}
    client.validate_response(request, process_request(request))
    assert not regenerate(document, OCPKernel(), result_version=3).ok  # Undo restores Strict.


@pytest.mark.parametrize("count", [1, 2, 3])
def test_unchanged_review_never_upgrades_a_saved_unbound_intent(count, client):
    edit = importlib.import_module(client.__package__ + ".support_intent_edit")
    document = chain_document(count, bound=False)
    replay = regenerate(document, OCPKernel(), result_version=3)
    saved = document.to_dict()
    if count == 1:
        assert replay.ok, replay.result
        reviewed = edit.edit_support_candidate(
            saved,
            "attached",
            "PRESERVE_PLANE",
            "cut_1",
            FACE,
            replay.result,
        )
        assert reviewed == saved
        assert "source_feature" not in feature(reviewed, "attached")["support_intent"]
    else:
        assert not replay.ok
        with pytest.raises(ValueError):
            edit.edit_support_candidate(
                saved,
                "attached",
                "PRESERVE_PLANE",
                f"cut_{count}",
                FACE,
                replay.result,
            )
    assert saved == document.to_dict()
    assert "source_feature" not in document.to_json()


def test_exact_strict_to_preserve_rejects_native_alias_without_weaker_intent_fallback(client):
    edit = importlib.import_module(client.__package__ + ".support_intent_edit")
    data = chain_document(2, strict=True).to_dict()
    # A finite notch retains the exact top face. A translated copy of the same
    # solid removes its right half, still leaving a unique stable top descriptor.
    feature(data, "slot_1_profile")["params"]["height"] = 10
    cut_index = next(index for index, row in enumerate(data["features"]) if row["id"] == "cut_2")
    data["features"].insert(
        cut_index,
        {"id": "copy", "kind": "transform", "params": {"x": 10}, "inputs": {"base": "block"}},
    )
    feature(data, "cut_2")["inputs"]["tool"] = "copy"
    document = Document.from_dict(data)
    replay = regenerate(document, OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    top = next(face for face in rows(replay)["cut_2"]["topology"] if face["id"] == FACE)
    assert top["provenance"]["semantic_status"] == "stable"
    assert rows(replay)["cut_2"]["stats"]["volume"] == pytest.approx(1946)
    with pytest.raises(ValueError, match="aliased"):
        edit.capture_support_intent(replay.result, "cut_2", FACE)
    saved = document.to_dict()
    with pytest.raises(ValueError, match="aliased"):
        edit.edit_support_candidate(
            saved, "attached", "PRESERVE_PLANE", "cut_2", FACE, replay.result
        )
    assert saved == document.to_dict()
    assert "support_intent" not in feature(saved, "attached")
    assert regenerate(document, OCPKernel(), result_version=3).ok


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("width,cut_volume", [(20, 3760), (24, 4560)])
def test_gui_two_cut_fixture_follows_named_width_without_rebinding(
    width, cut_volume, version, client
):
    path = ROOT / "examples/topology_support/two_cut_source_bound.mcad.json"
    saved = path.read_text(encoding="utf-8")
    assert "snapshot:" not in saved and "cut_ancestry" not in saved
    data = Document.from_json(saved).to_dict()
    data["parameters"]["plate_width"] = width
    document = Document.from_json(Document.from_dict(data).to_json())
    canonical = document.to_json()
    attached = feature(document.to_dict(), "attached")
    assert attached["support_intent"]["source_feature"] == "block"
    assert attached["support_face"] == FACE
    request = {
        "protocol_version": 1,
        "action": "replay",
        "result_version": version,
        "document": document.to_dict(),
    }
    response = process_request(request)
    assert response["ok"], response
    client.validate_response(request, response)
    result = response["result"]
    plane = feature(result, "attached")["support_plane"]
    assert plane["origin"] == pytest.approx([width / 2, 10, 10])
    assert rotate(plane["quaternion"], [0, 0, 1]) == pytest.approx([0, 0, 1])
    solved_center = feature(result, "attached")["sketch"]["solved"]["points"][0]
    assert solved_center == {"id": "center", "u": 6.0, "v": 0.0}
    boss = feature(result, "boss")
    boss_base = next(face for face in boss["topology"] if face["id"] == "boss/face/cap.start")
    assert boss_base["signature"]["centroid"] == pytest.approx([width / 2 + 6, 10, 10])
    assert boss["stats"]["volume"] == pytest.approx(8 * math.pi)
    assert feature(result, "cut_2")["stats"]["volume"] == pytest.approx(cut_volume)
    final = feature(result, "finished_part")
    assert final["stats"]["valid"] and final["stats"]["solids"] == 1
    assert final["stats"]["volume"] == pytest.approx(cut_volume + 8 * math.pi)
    descendants = lineage_faces(result, "cut_2")
    assert len(descendants) == 3
    assert all(face["id"].startswith("snapshot:") for face in descendants)
    assert all(face["provenance"]["semantic_status"] == "split" for face in descendants)
    signature, decision = resolve(document, result)
    assert signature["centroid"] == pytest.approx([width / 2, 10, 10])
    assert decision["source_feature"] == "block" and decision["cut_count"] == 2
    assert document.to_json() == canonical
    assert "snapshot:" not in canonical and "cut_ancestry" not in canonical
    assert path.read_text(encoding="utf-8") == saved
