"""Native typed Part publication and two-process open-sketch persistence.

Run with Blender 5.2.2 --background --factory-startup --python-exit-code 1,
MCAD_ROOT pointing to this repository and MCAD_PYTHON to its sidecar Python.
No native CAD modules are imported into Blender; no general editor is claimed.
"""

import copy
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import bridge, display, guarded_transport  # noqa: E402
from mechanical_cad_blender import document_state as state_api  # noqa: E402
from mechanical_cad_blender.geometry_operations import run_geometry_action  # noqa: E402

checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)


def state():
    return bpy.context.scene.mechanical_cad


def owned():
    return addon._owned_objects(bpy.context.scene)


def assert_wire():
    obj = owned()[0]
    check(state().status == "READY" and state().volume == 0, "Open data is ready without volume")
    check(
        not state().error and state().features[0].status == "ok",
        "Open output is not solver failure",
    )
    check("open_profile" in state().sketch_notice, "Precise profile-unavailable notice is visible")
    check("solving succeeded" in state().sketch_notice, "Notice separates successful solving")
    check(
        len(obj.data.vertices) == 3 and len(obj.data.edges) == 2, "All solved entities form a wire"
    )
    check(not obj.data.polygons and not obj.data.loop_triangles, "Wire has no faces or triangles")
    check(obj.hide_render and obj.display_type == "WIRE", "Wire makes no renderable-solid claim")
    check(
        obj["mechanical_cad_output_kind"] == "sketch", "Disposable display is explicitly a sketch"
    )
    check(
        obj["mechanical_cad_profile_state"] == "unavailable", "Profile state is disposable metadata"
    )
    check(not obj["mechanical_cad_stale"], "Supported open data is current")
    check(not state().last_good_mesh.polygons, "Private cache is also a wire")
    check(
        state().features[0].sketch_report_status == "CURRENT",
        "Actual native solver evidence is current",
    )
    report = json.loads(state().features[0].sketch_report_json)
    check(report["status"] in {"okay", "redundant_okay"}, "Native solve actually succeeded")
    check(report["remaining_dof"] == 0, "Native remaining DoF is preserved")


def rejected(callable_, match):
    try:
        callable_()
    except bridge.BridgeError as exc:
        check(match in str(exc), "Rejection explains " + match)
    else:
        raise AssertionError("Expected rejection: " + match)


addon.register()
reopen_path = os.environ.get("MCAD_TYPED_REOPEN")
if reopen_path:
    bpy.ops.wm.open_mainfile(filepath=reopen_path)
    saved = state().document_json
    check(state().status == "DIRTY", "Reopen invalidates saved runtime trust")
    check(state_api.regenerate(bpy.context), "Fresh native replay restores saved open sketch")
    check(state().document_json == saved, "Reopen/replay preserves exact authored JSON")
    assert_wire()
    check(
        not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
        "Blender remains native-CAD-free",
    )
    print(json.dumps({"marker": "TYPED_SKETCH_REOPEN_OK", "checks": checks}))
else:
    context = bpy.context
    with tempfile.TemporaryDirectory(prefix="mcad-typed-display-") as folder:
        directory = Path(folder)
        # The tooling API retains frozen legacy defaults. Production explicitly
        # requests guarded result 2 without migrating the legacy document.
        legacy = json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
        raw_exchange = bridge._exchange_raw
        requests = []

        def record_request(request, **kwargs):
            requests.append(copy.deepcopy(request))
            return raw_exchange(request, **kwargs)

        with patch.object(bridge, "_exchange_raw", record_request):
            check(bridge.replay(legacy)["status"] == "ok", "Legacy tooling replay still succeeds")
        check(
            "result_version" not in requests[-1], "Ordinary legacy wire request bytes omit version"
        )
        native_execute = guarded_transport.execute

        def record_guarded(prepared, selection, **kwargs):
            requests.append(prepared.guarded_request())
            return native_execute(prepared, selection, **kwargs)

        with patch.object(guarded_transport, "execute", record_guarded):
            check(state_api._commit_candidate(context, legacy), "Legacy document still commits")
        check(
            requests[-1]["result_version"] == 2 and "backend_contract" in requests[-1],
            "Production legacy-data replay requires guarded typed evidence",
        )
        with patch.object(guarded_transport, "execute", record_guarded):
            check(
                state_api._commit_candidate(context, legacy, result_version=2),
                "Explicit v2 accepts closed legacy data",
            )
        check(requests[-1]["result_version"] == 2, "Explicit typed capability is retained")
        check(
            json.loads(state().document_json) == legacy,
            "Opt-in does not migrate authored legacy bytes",
        )

        check(
            bpy.ops.mcad.load_document(filepath=str(ROOT / "examples/open_line_sketch.mcad.json"))
            == {"FINISHED"},
            "Actual Load accepts an independent open sketch",
        )
        assert_wire()
        open_document = json.loads(state().document_json)
        open_document["features"][0]["sketch"]["plane"].update(
            origin=[1_000_000.0, -1_000_000.0, 500_000.0],
            quaternion=[0.5, 0.5, 0.5, 0.5],
        )
        context.scene.unit_settings.scale_length = 0.01
        with patch.object(guarded_transport, "execute", record_guarded):
            check(
                state_api._commit_candidate(context, open_document),
                "Arbitrary-plane far-origin open sketch commits",
            )
        check(requests[-1]["result_version"] == 2, "Embedded schema 2 negotiates typed replay")
        assert_wire()
        obj = owned()[0]
        extents = [
            max(v.co[i] for v in obj.data.vertices) - min(v.co[i] for v in obj.data.vertices)
            for i in range(3)
        ]
        check(
            all(math.isclose(a, b, abs_tol=2e-6) for a, b in zip(extents, (0, 3, 2), strict=True)),
            "Normalized WXYZ rotation and scene units preserve dimensions",
        )
        check(
            all(math.isfinite(value) for value in obj.location),
            "Far-origin display uses a finite recentered object origin",
        )

        portable = directory / "open.mcad.json"
        check(
            bpy.ops.mcad.save_document(filepath=str(portable)) == {"FINISHED"},
            "Open data saves as portable CAD",
        )
        check(
            json.loads(portable.read_text()) == open_document,
            "Portable save contains exact authored data only",
        )
        check(
            bpy.ops.mcad.load_document(filepath=str(portable)) == {"FINISHED"},
            "Saved open CAD reopens",
        )
        assert_wire()
        blend_path = directory / "open.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        child = subprocess.run(
            [
                bpy.app.binary_path,
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python-expr",
                "import sys; sys.dont_write_bytecode = True",
                "--python",
                str(Path(__file__).resolve()),
            ],
            env={**os.environ, "MCAD_TYPED_REOPEN": str(blend_path)},
            capture_output=True,
            text=True,
            timeout=120,
        )
        check(
            child.returncode == 0 and "TYPED_SKETCH_REOPEN_OK" in child.stdout,
            "Separate native Blender process reopens and freshly replays the open sketch: "
            + child.stdout[-2000:]
            + child.stderr[-1000:],
        )
        print("TYPED_SKETCH_SAVE_REOPEN_OK", flush=True)

        for action in ("check_geometry", "export_step", "export_stl"):
            destination = None if action == "check_geometry" else str(directory / (action + ".out"))
            if destination:
                Path(destination).write_bytes(b"preserve previous export")
            with patch.object(guarded_transport, "execute", record_guarded):
                check(
                    not run_geometry_action(context, action, destination=destination),
                    "Open output rejects " + action,
                )
            check(requests[-1]["result_version"] == 2, "Geometry action uses negotiated version")
            report = json.loads(state().geometry_report_json)
            check(
                report["error"]["code"] == "not_a_solid" and report["export"] is None,
                "Action reports not_a_solid without false write",
            )
            check(report["geometry_check"] is None, "No solid statistics are manufactured")
            if destination:
                check(
                    Path(destination).read_bytes() == b"preserve previous export",
                    "Rejected export preserves its destination",
                )
            assert_wire()

        # Preserve exact, deliberately noncanonical JSON formatting on late display failure.
        state().document_json = json.dumps(open_document, indent=3) + "\n "
        formatted_source = state().document_json
        check(
            state_api.regenerate(context),
            "Exact formatted source establishes fresh guarded evidence before rollback",
        )
        check(
            state().document_json == formatted_source,
            "Fresh replay does not rewrite noncanonical source formatting",
        )
        before = state_api._snapshot_fields(state())
        old_obj, old_mesh, old_cache = owned()[0], owned()[0].data, state().last_good_mesh
        candidate = copy.deepcopy(open_document)
        candidate["name"] = "Display failure candidate"
        real_display = state_api._display_feature

        def late_display_failure(*args, **kwargs):
            real_display(*args, **kwargs)
            raise RuntimeError("Injected late wire display failure")

        with patch.object(state_api, "_display_feature", late_display_failure):
            try:
                state_api._commit_candidate(context, candidate)
            except RuntimeError as exc:
                check("Injected" in str(exc), "Late display failure propagated")
            else:
                raise AssertionError("Display failure must reject")
        check(
            state_api._snapshot_fields(state()) == before,
            "Late display failure rolls back exact canonical bytes, history and UI evidence",
        )
        check(
            owned() == [old_obj]
            and old_obj.data == old_mesh
            and state().last_good_mesh == old_cache,
            "Late failure restores untouched original display and cache",
        )

        # Late owner/tag/cache edits cannot change which exact datablocks the
        # transaction created. In particular, never delete a foreign cache mesh.
        for initially_empty in (False, True):
            original_scene = context.scene
            if initially_empty:
                target = bpy.data.scenes.new("Empty publication owner")
                context.window.scene = target
            else:
                target = original_scene
            for fault in ("owner", "object_tag", "foreign_cache"):
                previous = state_api._snapshot_fields(state())
                original_objects = set(target.objects)
                original_meshes = set(bpy.data.meshes)
                foreign = bpy.data.meshes.new("Unrelated untagged mesh " + fault)
                real_apply = state_api._apply_result

                def mutate_after_apply(
                    *args,
                    real_apply=real_apply,
                    fault=fault,
                    foreign=foreign,
                    target=target,
                    original_objects=original_objects,
                    **kwargs,
                ):
                    value = real_apply(*args, **kwargs)
                    if fault == "foreign_cache":
                        state().last_good_mesh = foreign
                        raise bridge.BridgeError("Injected foreign cache pointer")
                    if fault == "object_tag":
                        for item in set(target.objects) - original_objects:
                            item[display.OWNER_KEY] = "externally edited object tag"
                    state().owner_id = "externally edited scene owner"
                    return value

                with patch.object(state_api, "_apply_result", mutate_after_apply):
                    rejected(
                        lambda: state_api._commit_candidate(context, candidate),
                        "cache pointer" if fault == "foreign_cache" else "changed",
                    )
                check(
                    state_api._snapshot_fields(state()) == previous,
                    "Late metadata failure restores exact accepted fields",
                )
                check(
                    set(target.objects) == original_objects,
                    "Rejected candidate identities removed regardless of mutable tags",
                )
                check(
                    foreign.name in bpy.data.meshes,
                    "Rollback never deletes an unrelated cache pointer",
                )
                check(
                    set(bpy.data.meshes) == original_meshes | {foreign},
                    "Exact candidate meshes and cache are reclaimed without leaks",
                )
                check(
                    display._PUBLICATION.get() is None,
                    "Rejected publication releases its creation tracker",
                )
                bpy.data.meshes.remove(foreign)
            if initially_empty:
                context.window.scene = original_scene
                bpy.data.scenes.remove(target)

        for failed_candidate in (
            candidate,
            json.loads((ROOT / "examples/circle_sketch_part.mcad.json").read_text()),
        ):
            original_scene = context.scene
            target = bpy.data.scenes.new("Empty owner cleanup refusal")
            context.window.scene = target
            real_apply = state_api._apply_result
            unrelated = bpy.data.objects.new("Unrelated callback object", None)
            target.collection.objects.link(unrelated)

            def fail_after_publication(*args, real_apply=real_apply, **kwargs):
                real_apply(*args, **kwargs)
                state().owner_id = "late owner edit before failed cleanup"
                raise RuntimeError("Injected rejected candidate")

            with (
                patch.object(state_api, "_apply_result", fail_after_publication),
                patch.object(
                    display,
                    "_unlink_owned_object",
                    side_effect=RuntimeError("Injected unlink refusal"),
                ),
            ):
                rejected(
                    lambda failed_candidate=failed_candidate: state_api._commit_candidate(
                        context, failed_candidate
                    ),
                    "Recovery is incomplete",
                )
            rejected_objects = [item for item in target.objects if item != unrelated]
            check(
                state().status == "FAILED" and not state().document_json and not state().owner_id,
                "Empty-owner compound failure restores canonical emptiness without READY",
            )
            check(
                bool(rejected_objects)
                and all(
                    item.hide_viewport and item.hide_render and item.get("mechanical_cad_stale")
                    for item in rejected_objects
                ),
                "Exact rejected wire/solid identities are hidden after cleanup refusal",
            )
            check(
                not unrelated.hide_viewport and not unrelated.hide_render,
                "Unrelated object visibility survives incomplete recovery",
            )
            check(
                display._PUBLICATION.get() is None, "Compound failure releases the creation tracker"
            )
            context.window.scene = original_scene
            bpy.data.scenes.remove(target)
            for item in [unrelated, *rejected_objects]:
                mesh = item.data if item.type == "MESH" else None
                bpy.data.objects.remove(item)
                if mesh is not None and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)

        # A partial canonical write and a second cleanup failure must not skip
        # restoring old links/JSON or falsely reassert the old READY status.
        candidate_binding = state_api._capture_binding(context)
        with state_api.replay_guard(context):
            candidate_evidence = state_api._run_sidecar(
                context,
                candidate,
                binding=candidate_binding,
            )
        candidate_result = state_api._evidence_projection(
            context,
            candidate,
            candidate_evidence,
            candidate_binding,
        )["result"]
        candidate_feature = candidate_result["features"][0]

        def partial_population(scene, document, path=""):
            scene.mechanical_cad.document_json = json.dumps(document)
            scene.mechanical_cad.document_name = "Partially written candidate"
            scene.mechanical_cad.features.clear()
            real_display(context, document, candidate_feature)
            raise RuntimeError("Injected partial canonical write")

        with (
            patch.object(state_api, "_populate_document", partial_population),
            patch.object(
                display,
                "_unlink_owned_object",
                side_effect=RuntimeError("Injected cleanup failure"),
            ),
        ):
            rejected(
                lambda: state_api._commit_candidate(context, candidate), "Recovery is incomplete"
            )
        check(
            state().document_json == before["document_json"]
            and state().document_name == before["document_name"]
            and [row.feature_id for row in state().features]
            == [row["feature_id"] for row in before["features"]],
            "Compound failure still restores exact canonical bytes and history",
        )
        check(
            old_obj in owned() and old_obj.data == old_mesh and state().last_good_mesh == old_cache,
            "Cleanup failure does not skip restoring original links and cache",
        )
        check(
            state().status == "FAILED"
            and all(obj.hide_viewport and obj.hide_render for obj in owned())
            and state().features[0].sketch_report_status == "OUTDATED",
            "Incomplete recovery revokes current evidence and hides all owned displays",
        )
        check(
            "Injected partial canonical write" in state().error
            and "Injected cleanup failure" in state().error,
            "Both primary and cleanup diagnostics survive",
        )
        check(
            state_api.regenerate(context),
            "Fresh replay recovers after cleanup injection is removed",
        )
        assert_wire()
        before = state_api._snapshot_fields(state())
        old_obj, old_mesh, old_cache = owned()[0], owned()[0].data, state().last_good_mesh

        # Scene/revision guards reject before publication and preserve the other scene.
        original_scene = context.scene
        other = bpy.data.scenes.new("Unrelated typed-test scene")
        replay = state_api._run_sidecar

        def switch_scene(*args, **kwargs):
            result = replay(*args, **kwargs)
            context.window.scene = other
            return result

        try:
            with patch.object(state_api, "_run_sidecar", switch_scene):
                rejected(
                    lambda: state_api._commit_candidate(context, candidate),
                    "scene or window changed",
                )
            check(
                not other.mechanical_cad.document_json and not addon._owned_objects(other),
                "Late result never publishes into replacement scene",
            )
        finally:
            context.window.scene = original_scene
        check(
            state_api._snapshot_fields(state()) == before and owned() == [old_obj],
            "Original scene stays exact after late scene switch",
        )
        bpy.data.scenes.remove(other)

        unknown = copy.deepcopy(open_document)
        unknown["features"][0]["sketch"]["schema_version"] = 4
        with patch.object(guarded_transport, "execute") as transport:
            rejected(
                lambda: state_api._commit_candidate(context, unknown), "unsupported sketch schema"
            )
            check(
                not transport.called,
                "Unknown future schema fails before native transport and never falls back",
            )
        malformed_v3 = copy.deepcopy(open_document)
        malformed_v3["features"][0]["sketch"]["schema_version"] = 3
        with patch.object(guarded_transport, "execute") as transport:
            rejected(
                lambda: state_api._commit_candidate(context, malformed_v3),
                "unknown or missing fields",
            )
            check(
                not transport.called,
                "Malformed schema 3 fails before native transport and never falls back",
            )
        rejected(
            lambda: state_api._commit_candidate(context, open_document, result_version=1),
            "Requested Part result version differs from the complete candidate.",
        )

        closed = copy.deepcopy(open_document)
        closed["features"][0]["sketch"]["lines"].append(
            {"id": "closing_leg", "start": "end_v", "end": "corner"}
        )
        closed["features"].append(
            {
                "id": "pad",
                "kind": "extrude",
                "label": "Same sketch extrusion",
                "params": {"length": 5},
                "inputs": {"profile": "profile"},
            }
        )
        closed["active_feature"] = "pad"
        with patch.object(state_api, "_run_sidecar", wraps=replay) as fresh:
            check(
                state_api._commit_candidate(context, closed),
                "Closing the reopened same IDs enables fresh extrusion",
            )
        check(fresh.call_count == 1, "Commit always replays the whole candidate exactly once")
        check(
            math.isclose(state().volume, 1500, rel_tol=1e-5),
            "Actual closed triangular prism has expected volume",
        )
        check(
            owned()[0].data.polygons and not owned()[0].hide_render,
            "Only actual solid output acquires solid display",
        )
        check(not state().sketch_notice, "Closed solid clears the old unavailable-profile notice")
        check(
            run_geometry_action(context, "check_geometry"),
            "Fresh solid passes real native geometry checks",
        )
        solid_json = state().document_json
        consumed_open = copy.deepcopy(closed)
        consumed_open["features"][0]["sketch"]["lines"].pop()
        # Simulate the future general editor's recoverable UI payload, then use
        # the already-owned private commit transaction, not public draft bypass.
        state().sketch_draft_json = '{"recoverable_test_draft": "unaltered"}'
        before = state_api._snapshot_fields(state())
        old_obj, old_mesh, old_cache = owned()[0], owned()[0].data, state().last_good_mesh
        with state_api.replay_guard(context):
            rejected(lambda: state_api._commit_candidate_locked(context, consumed_open), "pad:")
        check(
            state().document_json == solid_json and state_api._snapshot_fields(state()) == before,
            "Blocked downstream extrusion preserves canonical bytes, history and recoverable draft",
        )
        check(
            owned() == [old_obj]
            and old_obj.data == old_mesh
            and state().last_good_mesh == old_cache,
            "Blocked extrusion preserves exact last-good geometry",
        )
        state().sketch_draft_json = ""
        check(
            not any(
                name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules
            ),
            "Native CAD stayed outside Blender throughout",
        )
        check(
            not state_api._REPLAY_RUNNING,
            "Transaction lock is released after success and every rejection",
        )
    print(json.dumps({"marker": "TYPED_SKETCH_DISPLAY_OK", "checks": checks}))
addon.unregister()
