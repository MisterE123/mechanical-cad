"""Call-local projection sharing must not cache authority or mutable scene state."""

import json
from dataclasses import replace

import pytest
from test_geometry3_owner import host as _host
from test_geometry3_owner import run

host = _host


@pytest.mark.parametrize(
    "reader", ["current_part_result", "current_part_evidence", "part_is_current"]
)
def test_current_read_validates_one_projection(host, monkeypatch, reader):
    assert run(host)
    calls = []
    original = host.doc._evidence_projection

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(host.doc, "_evidence_projection", counted)
    assert getattr(host.doc, reader)(host.context)
    assert calls == [1]


@pytest.mark.parametrize(
    "reader", ["current_part_result", "current_part_evidence", "part_is_current"]
)
@pytest.mark.parametrize(
    "mutation",
    [
        "document",
        "owner",
        "scale",
        "generation",
        "lifetime",
        "status",
        "record",
        "owner_token",
        "removed_record",
        "scene",
        "retained_bytes",
        "prepared_payload",
        "evidence_owner",
        "revoked_publication",
    ],
)
def test_change_during_projection_refuses_current_authority(host, monkeypatch, reader, mutation):
    assert run(host)
    original = host.doc._evidence_projection
    state = host.context.scene.mechanical_cad

    def changed(*args, **kwargs):
        response = original(*args, **kwargs)
        if mutation == "document":
            state.document_json += " "
        elif mutation == "owner":
            state.owner_id += "-changed"
        elif mutation == "scale":
            host.context.scene.unit_settings.scale_length *= 2
        elif mutation == "generation":
            host.current[0] = replace(host.current[0], generation=host.current[0].generation + 1)
        elif mutation == "lifetime":
            host.current[0] = replace(host.current[0], lifetime_id="reopened")
        elif mutation == "status":
            state.status = "DIRTY"
        elif mutation == "revoked_publication":
            key = host.doc._scene_key(host.context.scene)
            host.doc._RUNTIME[key]["evidence"].publication._state = "cancelled"
        elif mutation in {"retained_bytes", "prepared_payload", "evidence_owner"}:
            key = host.doc._scene_key(host.context.scene)
            evidence = host.doc._RUNTIME[key]["evidence"]
            if mutation == "retained_bytes":
                object.__setattr__(evidence, "_response_payload", b"{}")
            elif mutation == "prepared_payload":
                object.__setattr__(evidence._prepared, "payload", b"{}")
            else:
                object.__setattr__(evidence, "_owner_token", object())
        elif mutation == "scene":
            from types import SimpleNamespace

            host.context.scene = SimpleNamespace(mechanical_cad=state)
        else:
            key = host.doc._scene_key(host.context.scene)
            if mutation == "owner_token":
                host.doc._RUNTIME[key]["owner_token"] = object()
            elif mutation == "removed_record":
                host.doc._RUNTIME.pop(key)
            else:
                host.doc._RUNTIME[key] = dict(host.doc._RUNTIME[key])
        return response

    monkeypatch.setattr(host.doc, "_evidence_projection", changed)
    assert not getattr(host.doc, reader)(host.context)


def test_each_read_detaches_and_rechecks_retained_evidence(host):
    assert run(host)
    result = host.doc.current_part_result(host.context)
    result["status"] = "forged"
    result["features"].clear()
    fresh = host.doc.current_part_result(host.context)
    assert fresh["status"] == "ok" and fresh["features"]
    record = host.doc._RUNTIME[host.doc._scene_key(host.context.scene)]
    evidence = record["evidence"]
    response = evidence.response_snapshot()
    response["result"]["features"][0]["status"] = "forged"
    object.__setattr__(evidence, "_response_payload", json.dumps(response).encode())
    assert host.doc.current_part_result(host.context) is None
    assert host.doc.current_part_evidence(host.context) is None
    assert not host.doc.part_is_current(host.context)


def test_read_then_backend_change_cannot_restore_authority_from_old_record(host):
    assert run(host)
    key = host.doc._scene_key(host.context.scene)
    prior = host.doc._RUNTIME[key]
    assert host.doc.current_part_result(host.context)
    host.current[0] = replace(host.current[0], generation=host.current[0].generation + 1)
    host.doc._RUNTIME[key] = prior  # Model/display rollback cannot roll back the runtime epoch.
    host.context.scene.mechanical_cad.status = "READY"
    assert host.doc.current_part_result(host.context) is None
    assert host.doc.current_part_evidence(host.context) is None


@pytest.mark.parametrize(
    "reader", ["current_part_result", "current_part_evidence", "part_is_current"]
)
@pytest.mark.parametrize("mutation", ["solver_removed", "solver_repointed", "core_removed"])
def test_filesystem_origin_change_during_proof_refuses_authority(
    host, monkeypatch, tmp_path, reader, mutation
):
    import sys

    root = tmp_path / "backend"
    core = root / "src" / "mechanical_cad"
    core.mkdir(parents=True)
    source = core / "sketch_solver.py"
    source.write_text("# Synthetic identity fixture, never imported.\n")
    outside = tmp_path / "other_solver.py"
    outside.write_text("# Outside the selected core.\n")
    host.current[0] = host.modules.backend_selection.BackendSelection.capture(
        str(root), sys.executable, generation=2, lifetime_id="origin-test", environment={}
    )
    assert run(host)
    original = host.doc._evidence_projection

    def changed(*args, **kwargs):
        response = original(*args, **kwargs)
        source.unlink()
        if mutation == "solver_repointed":
            source.symlink_to(outside)
        elif mutation == "core_removed":
            core.rmdir()
        return response

    monkeypatch.setattr(host.doc, "_evidence_projection", changed)
    assert not getattr(host.doc, reader)(host.context)
