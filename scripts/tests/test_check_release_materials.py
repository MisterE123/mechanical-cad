"""Synthetic review records and inert archives; no licenses or binaries qualified."""

import copy
import importlib.util
import json
import stat
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


g = load("release_materials_gate_tests", ROOT / "scripts/check_release_materials.py")
f = load(
    "release_materials_builder_fixtures", ROOT / "scripts/tests/test_build_release_candidate.py"
)


def review_for(value, digest):
    # This is fictional accounting, never a review of real recipient materials.
    def paths(c):
        return c["source_paths"] + c["notice_paths"] + c["provenance_paths"]

    components = value["components"]
    return {
        "schema_version": 1,
        "source_commit": value["source_commit"],
        "platform": value["platform"],
        "materials_map_sha256": digest,
        "project_source_path": next(
            c["source_paths"][0] for c in components if c["kind"] == "project_package"
        ),
        "components": [
            {
                "id": c["id"],
                "selected_license_route": "SYNTHETIC-TEST-ONLY",
                "source_status": "reviewed_present",
                "notice_status": "reviewed_present",
                "evidence_paths": paths(c),
                "rationale": "Synthetic fixture rationale.",
            }
            for c in components
        ],
        "issues": [
            {
                "id": i["id"],
                "disposition": "blocks_distribution",
                "evidence_paths": sorted(
                    {
                        p
                        for c in components
                        if i["id"] in c["unresolved_issue_ids"]
                        for p in paths(c)
                    }
                ),
                "rationale": "Synthetic issue remains a distribution blocker.",
            }
            for i in value["unresolved_issues"]
        ],
    }


def write_project_source(path, source_root, source_manifest):
    with zipfile.ZipFile(path, "w") as archive:
        for item in source_manifest:
            data = (source_root / item["path"]).read_bytes()
            assert len(data) == item["size"] and g.A.digest(data) == item["sha256"]
            info = zipfile.ZipInfo(item["path"])
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | item["mode"]) << 16
            archive.writestr(info, data)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    manifests = []
    export = f.adapter.export_source

    def capture_manifest(*args, **kwargs):
        result = export(*args, **kwargs)
        manifests.append(copy.deepcopy(result))
        return result

    monkeypatch.setattr(f.adapter, "export_source", capture_manifest)
    original = f.prepared.__wrapped__(tmp_path)
    assert len(manifests) == 1
    data = (original.inputs_root / "metadata/materials-map.json").read_bytes()
    value = json.loads(data)
    material_root = original.inputs_root / "materials"
    project = next(c for c in value["components"] if c["kind"] == "project_package")
    old_path = project["source_paths"][0]
    (material_root / old_path).unlink()  # Synthetic fixture only.
    project["source_paths"] = ["sources/project.zip"]
    source_files = json.loads(
        (original.inputs_root / "metadata/materials-inventory.json").read_bytes()
    )
    exported = tmp_path / "source-export"
    assert {p.relative_to(exported).as_posix() for p in exported.rglob("*") if p.is_file()} == {
        item["path"] for item in manifests[0]
    }
    write_project_source(material_root / "sources/project.zip", exported, manifests[0])
    source_files = [item for item in source_files if item["path"] != old_path]
    archive_bytes = (material_root / "sources/project.zip").read_bytes()
    source_files.append(
        {
            "path": "sources/project.zip",
            "mode": 420,
            "size": len(archive_bytes),
            "sha256": g.A.digest(archive_bytes),
        }
    )
    source_files.sort(key=lambda item: item["path"])
    inventory_bytes = g.A.canonical(source_files)
    (original.inputs_root / "metadata/materials-inventory.json").write_bytes(inventory_bytes)
    value["materials_inventory_sha256"] = g.A.digest(inventory_bytes)
    data = g.A.canonical(value)
    (original.inputs_root / "metadata/materials-map.json").write_bytes(data)
    original.materials_map_sha256 = g.A.digest(data)
    review = tmp_path / "review.json"
    review.write_bytes(g.A.canonical(review_for(value, g.A.digest(data))))
    args = SimpleNamespace(
        **vars(original),
        review=review,
        review_sha256=g.A.digest(review.read_bytes()),
        work_parent=tmp_path,
    )
    return args


def rewrite(args, mutate):
    value = json.loads(args.review.read_bytes())
    mutate(value)
    args.review.write_bytes(g.A.canonical(value))
    args.review_sha256 = g.A.digest(args.review.read_bytes())


def test_exact_source_and_materials_report_retained_blockers_without_building(prepared):
    before = prepared.review.read_bytes()
    result = g.check(prepared)
    assert result["status"] == "MATERIALS_REVIEW_BLOCKED"
    assert result["blocked_issue_ids"] == ["rebuild", "rights"]
    assert result["retained_issue_ids"] == ["rebuild", "rights"]
    assert result["retained_issue_count"] == 2
    assert result["source_commit"] == prepared.source_commit
    assert result["review_sha256"] == prepared.review_sha256
    assert result["native_qualification"] == "NOT_RUN"
    assert (
        result["legal_clearance"] == result["release_admission"] == "NOT_ESTABLISHED_BY_THIS_TOOL"
    )
    assert prepared.review.read_bytes() == before
    assert not prepared.output.exists() and not prepared.receipt.exists()
    assert not (prepared.work_parent / "EXECUTED").exists()
    assert str(prepared.work_parent) not in json.dumps(result)


def test_nonblocking_review_preserves_issues_and_no_release_claim(prepared):
    def update(value):
        for issue in value["issues"]:
            issue["disposition"] = "reviewed_nonblocking"
            issue["rationale"] = "Fictional test finding only; no real legal conclusion."

    rewrite(prepared, update)
    result = g.check(prepared)
    assert result["status"] == "MATERIALS_REVIEW_RECORDED"
    assert (
        result["reviewed_nonblocking_issue_ids"]
        == result["retained_issue_ids"]
        == ["rebuild", "rights"]
    )
    assert result["release_admission"] == "NOT_ESTABLISHED_BY_THIS_TOOL"
    assert result == g.check(prepared)


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "platform",
        "map",
        "extra",
        "bool_schema",
        "missing_component",
        "duplicate_component",
        "missing_issue",
        "unknown_issue",
        "duplicate_issue",
        "unknown_evidence",
        "duplicate_evidence",
        "no_evidence",
        "missing_notice_evidence",
        "missing_source_evidence",
        "unknown_status",
        "unknown_disposition",
        "empty_route",
        "empty_reason",
    ],
)
def test_review_rejects_stale_incomplete_or_unsupported_declarations(prepared, change):
    def mutate(value):
        row = value["components"][0]
        if change in ("source", "platform", "map"):
            value[
                {"source": "source_commit", "platform": "platform", "map": "materials_map_sha256"}[
                    change
                ]
            ] = "wrong"
        elif change == "extra":
            value["approved"] = True
        elif change == "bool_schema":
            value["schema_version"] = True
        elif change == "missing_component":
            value["components"].pop()
        elif change == "duplicate_component":
            value["components"][1] = copy.deepcopy(row)
        elif change == "missing_issue":
            value["issues"].pop()
        elif change == "unknown_issue":
            value["issues"][0]["id"] = "unknown"
        elif change == "duplicate_issue":
            value["issues"][1] = copy.deepcopy(value["issues"][0])
        elif change == "unknown_evidence":
            row["evidence_paths"] = ["sources/not-in-map.zip"]
        elif change == "duplicate_evidence":
            row["evidence_paths"] += row["evidence_paths"][:1]
        elif change == "no_evidence":
            row["evidence_paths"] = []
        elif change == "missing_notice_evidence":
            row["evidence_paths"] = [
                p for p in row["evidence_paths"] if not p.startswith("licenses/")
            ]
        elif change == "missing_source_evidence":
            row["evidence_paths"] = [
                p for p in row["evidence_paths"] if not p.startswith("sources/")
            ]
        elif change == "unknown_status":
            row["source_status"] = "approved"
        elif change == "unknown_disposition":
            value["issues"][0]["disposition"] = "ignore"
        elif change == "empty_route":
            row["selected_license_route"] = " "
        elif change == "empty_reason":
            row["rationale"] = ""

    rewrite(prepared, mutate)
    with pytest.raises(g.ReviewError):
        g.check(prepared)


@pytest.mark.parametrize(
    "change",
    [
        "review_hash",
        "map_hash",
        "lock_hash",
        "materials_mutation",
        "runtime_mutation",
        "extra_material",
        "stale_inventory",
        "not_main",
        "wrong_tag",
        "symlink_review",
    ],
)
def test_real_input_verification_is_not_replaced_by_review(prepared, change):
    if change.endswith("_hash"):
        setattr(
            prepared,
            {
                "review_hash": "review_sha256",
                "map_hash": "materials_map_sha256",
                "lock_hash": "runtime_lock_sha256",
            }[change],
            "0" * 64,
        )
    elif change == "materials_mutation":
        (prepared.inputs_root / "materials/licenses/NOTICE.txt").write_bytes(b"changed")
    elif change == "runtime_mutation":
        (prepared.inputs_root / "runtime/packages/OCP/inert.so").write_bytes(b"changed")
    elif change == "extra_material":
        (prepared.inputs_root / "materials/licenses/extra.txt").write_bytes(b"extra")
    elif change == "stale_inventory":
        (prepared.inputs_root / "metadata/materials-inventory.json").write_bytes(b"[]")
    elif change == "not_main":
        prepared.main_ref = "refs/heads/other"
    elif change == "wrong_tag":
        prepared.tag = "v999.0.0"
    elif change == "symlink_review":
        link = prepared.work_parent / "linked-review.json"
        link.symlink_to(prepared.review)
        prepared.review = link
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        g.check(prepared)
    assert not prepared.output.exists()


def test_blocked_components_remain_blockers_even_with_nonblocking_issues(prepared):
    def mutate(value):
        for issue in value["issues"]:
            issue["disposition"] = "reviewed_nonblocking"
        value["components"][0]["source_status"] = "blocked"

    rewrite(prepared, mutate)
    result = g.check(prepared)
    assert result["status"] == "MATERIALS_REVIEW_BLOCKED"
    assert result["blocked_component_ids"]


def test_review_mutation_during_check_is_refused(prepared, monkeypatch):
    original = g.evaluate

    def mutate(*args):
        result = original(*args)
        prepared.review.write_bytes(b"{}")
        return result

    monkeypatch.setattr(g, "evaluate", mutate)
    with pytest.raises(g.ReviewError, match="changed"):
        g.check(prepared)


@pytest.mark.parametrize(
    "change",
    [
        "stale",
        "missing",
        "extra",
        "duplicate",
        "symlink",
        "mode",
        "absolute",
        "directory",
        "comment",
        "wrong_path",
    ],
)
def test_exact_project_source_archive_controls(tmp_path, change):
    path = tmp_path / "source.zip"
    expected = [{"path": "src/main.py", "size": 3, "sha256": g.A.digest(b"abc"), "mode": 420}]
    with zipfile.ZipFile(path, "w") as archive:
        name = "src/main.py"
        if change == "absolute":
            name = "/src/main.py"
        elif change == "directory":
            name = "src/"
        elif change == "wrong_path":
            name = "old/main.py"
        info = zipfile.ZipInfo(name)
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 420) << 16
        if change == "symlink":
            info.external_attr = (stat.S_IFLNK | 420) << 16
        elif change == "mode":
            info.external_attr = (stat.S_IFREG | 493) << 16
        if change != "missing":
            archive.writestr(info, b"old" if change == "stale" else b"abc")
        if change == "extra":
            archive.writestr("private.txt", b"no")
        elif change == "duplicate":
            with pytest.warns(UserWarning):
                archive.writestr(info, b"abc")
        elif change == "comment":
            archive.comment = b"unreviewed extra"
    with pytest.raises((g.ReviewError, g.A.CandidateError)):
        g.verify_project_source(path, expected)


def test_project_source_cannot_be_waived(prepared):
    def change(value):
        next(c for c in value["components"] if c["id"] == "project")["source_status"] = (
            "reviewed_not_required"
        )

    rewrite(prepared, change)
    with pytest.raises(g.ReviewError, match="cannot be waived"):
        g.check(prepared)


@pytest.mark.parametrize(
    "status,code", [("MATERIALS_REVIEW_BLOCKED", 2), ("MATERIALS_REVIEW_RECORDED", 0)]
)
def test_cli_exits_distinguish_recorded_review_from_blockers(monkeypatch, capsys, status, code):
    argv = ["check_release_materials"]
    for name in (
        "source-repo",
        "source-commit",
        "tag",
        "inputs-root",
        "platform",
        "review",
        "runtime-lock-sha256",
        "materials-map-sha256",
        "review-sha256",
        "work-parent",
    ):
        argv += ["--" + name, "fixture"]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(g, "check", lambda args: {"status": status})
    assert g.main() == code
    assert json.loads(capsys.readouterr().out)["status"] == status


@pytest.mark.parametrize("method", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_project_source_verifies_utf8_and_executable_modes(tmp_path, method):
    expected = [
        {"path": "src/café.py", "size": 3, "sha256": g.A.digest(b"abc"), "mode": 420},
        {"path": "run.sh", "size": 0, "sha256": g.A.digest(b""), "mode": 493},
    ]
    path = tmp_path / "project.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for item, data in zip(expected, (b"abc", b""), strict=True):
            info = zipfile.ZipInfo(item["path"])
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | item["mode"]) << 16
            info.compress_type = method
            archive.writestr(info, data)
    assert g.verify_project_source(path, expected) == g.A.digest(path.read_bytes())


@pytest.mark.parametrize(
    "mode,wrong", [(0o644, 0o755), (0o755, 0o644)], ids=["regular", "executable"]
)
def test_fixture_source_modes_follow_manifest_and_reject_mismatched_metadata(tmp_path, mode, wrong):
    source = tmp_path / "source"
    source.mkdir()
    data = b"unchanged source bytes\n"
    (source / "file.py").write_bytes(data)
    expected = [{"path": "file.py", "mode": mode, "size": len(data), "sha256": g.A.digest(data)}]
    path = tmp_path / "project.zip"
    write_project_source(path, source, expected)
    with zipfile.ZipFile(path) as archive:
        (info,) = archive.infolist()
        assert info.filename == "file.py" and info.create_system == 3
        assert info.external_attr >> 16 == stat.S_IFREG | mode
        assert archive.read(info) == data
    assert g.verify_project_source(path, expected) == g.A.digest(path.read_bytes())

    # Only the ZIP permission bits change; exact source/hash/member checks stay.
    info.external_attr = (stat.S_IFREG | wrong) << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(info, data)
    with pytest.raises(g.ReviewError, match="member metadata mismatch"):
        g.verify_project_source(path, expected)
    assert (source / "file.py").read_bytes() == data


@pytest.mark.parametrize("where", ["prefix", "suffix", "gap", "local_extra", "local_name"])
def test_project_source_refuses_uninventoried_archive_bytes(tmp_path, where):
    import struct

    path = tmp_path / "project.zip"
    expected = [{"path": "file", "size": 3, "sha256": g.A.digest(b"abc"), "mode": 420}]
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo("file")
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 420) << 16
        archive.writestr(info, b"abc")
    data = path.read_bytes()
    if where == "prefix":
        data = b"private" + data
    elif where == "suffix":
        data += b"private"
    elif where == "gap":
        eocd = list(struct.unpack("<4s4H2LH", data[-22:]))
        offset = eocd[6]
        eocd[6] += 7
        data = data[:offset] + b"private" + data[offset:-22] + struct.pack("<4s4H2LH", *eocd)
    elif where == "local_extra":
        data = data[:28] + b"\x01\x00" + data[30:]
    elif where == "local_name":
        data = data[:30] + b"evil" + data[34:]
    path.write_bytes(data)
    with pytest.raises(g.ReviewError):
        g.verify_project_source(path, expected)
