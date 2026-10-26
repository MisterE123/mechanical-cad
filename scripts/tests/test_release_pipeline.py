"""Admission mutations and publisher fault injection; no network/native execution."""

import copy
import hashlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("release_pipeline", SCRIPTS / "release_pipeline.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
sys.modules["release_pipeline"] = P
spec = importlib.util.spec_from_file_location(
    "publisher_under_test", SCRIPTS / "publish_release.py"
)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

COMMIT = "a" * 40
TAG = "v1.29.0"


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(P.A, "source_identity", lambda *a: TAG[1:])
    monkeypatch.setattr(P.A, "git", lambda *a: "b" * 40)
    monkeypatch.setattr(P.subprocess, "check_output", lambda *a, **k: b"qualification-source")
    for platform in P.PLATFORMS:
        root = tmp_path / platform
        (root / "native").mkdir(parents=True)
        (root / "candidate.zip").write_bytes(platform.encode())
        row = {
            "prepared": {"url": "https://example.invalid/inputs", "sha256": "c" * 64, "bytes": 1},
            "acquisition_lock": "release_inputs/lock.json",
            "blender": {"url": "https://example.invalid/blender", "sha256": "c" * 64, "bytes": 1},
            "blender_path": "blender",
            "runtime_lock_sha256": "c" * 64,
            "materials_map_sha256": "c" * 64,
            "review_sha256": "c" * 64,
        }
        P.write(
            root / "config.json", {"schema_version": 1, "platforms": {p: row for p in P.PLATFORMS}}
        )
        sha, size = P.identity(root / "candidate.zip")
        common = {
            "source_commit": COMMIT,
            "platform": platform,
            **{
                key: "c" * 64
                for key in (
                    "runtime_lock_sha256",
                    "materials_map_sha256",
                    "source_inventory_sha256",
                    "runtime_inventory_sha256",
                    "materials_inventory_sha256",
                )
            },
        }
        P.write(
            root / "build.json",
            {
                **common,
                "status": P.A.STATUS,
                "qualification": "NOT_RUN",
                "archive": "candidate.zip",
                "tag": TAG,
                "version": TAG[1:],
                "sha256": sha,
                "bytes": size,
                "unresolved_material_issue_ids": ["retained-issue"],
            },
        )
        P.write(
            root / "materials.json",
            {
                **common,
                "status": "MATERIALS_REVIEW_RECORDED",
                "review_sha256": "c" * 64,
                "blocked_component_ids": [],
                "blocked_issue_ids": [],
                "retained_issue_ids": ["retained-issue"],
                "reviewed_nonblocking_issue_ids": ["retained-issue"],
            },
        )
        native = {
            "ok": True,
            "source_commit": COMMIT,
            "version": TAG[1:],
            "archive_sha256": sha,
            "archive_bytes": size,
            "required_blender_version": "5.2.2",
            "modes": [
                {
                    "mode": mode,
                    "ok": True,
                    "returncode": 0,
                    "result": {
                        "ok": True,
                        "mode": mode,
                        "archive_sha256": sha,
                        "source_commit": COMMIT,
                        "version": TAG[1:],
                        "blender": "5.2.2",
                        "interactive_gui": False,
                    },
                }
                for mode in ("install", "write", "read")
            ],
        }
        for key in ("script", "fixture"):
            native[key + "_sha256"] = hashlib.sha256(b"qualification-source").hexdigest()
            native[key + "_bytes"] = len(b"qualification-source")
        P.write(root / "native/summary.json", native)
        P.write(
            root / "native/host.json",
            {
                "platform": platform,
                "sys_platform": "win32" if platform == "windows-x64" else "linux",
            },
        )
    return tmp_path


def replace(path, change):
    value = P.read(path)
    change(value)
    path.write_bytes(P.A.canonical(value))


def test_both_platforms_with_real_retained_issue_accounting_admit(evidence):
    result = P.admit(evidence, COMMIT, TAG)
    assert set(result["platforms"]) == P.PLATFORMS
    assert result["source_tree"] == "b" * 40


@pytest.mark.parametrize("platform", sorted(P.PLATFORMS))
def test_shared_acquisition_uses_actual_reviewed_target_lock(tmp_path, monkeypatch, platform):
    lock = P.ROOT / "release_inputs" / platform / "acquisition-lock.json"
    adapter = P.load("acquire_release_inputs")
    inventory = adapter.validate_lock(P.read(lock))
    assert len(inventory) == (1050 if platform == "windows-x64" else 1030)
    calls = []

    def acquire(path, work):
        calls.append((path, work))
        return {
            "platform": platform,
            "native_execution": False,
            "acquisition_lock_sha256": P.identity(lock)[0],
        }

    def load(name):
        assert name == "acquire_release_inputs"
        return SimpleNamespace(acquire=acquire)

    monkeypatch.setattr(P, "load", load)
    result = P.acquire_runtime(platform, lock, tmp_path / "new")
    assert result["native_execution"] is False
    assert calls == [(lock, tmp_path / "new")]


def test_wrong_target_lock_fails_before_acquisition(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "load", lambda *a: pytest.fail("Wrong target reached acquisition"))
    with pytest.raises(ValueError, match="target mismatch"):
        P.acquire_runtime(
            "windows-x64",
            P.ROOT / "release_inputs/linux-x64/acquisition-lock.json",
            tmp_path / "new",
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_platform",
        "archive",
        "source",
        "version",
        "missing_read",
        "returncode_bool",
        "mode_failure",
        "stale_result",
        "native_script",
        "native_host",
        "materials",
        "map",
        "unreviewed_issue",
    ],
)
def test_admission_fails_closed(evidence, mutation):
    root = evidence / "windows-x64"
    if mutation == "missing_platform":
        (root / "native/summary.json").unlink()
    elif mutation == "archive":
        (root / "candidate.zip").write_bytes(b"replacement")
    elif mutation in {
        "source",
        "version",
        "missing_read",
        "returncode_bool",
        "mode_failure",
        "stale_result",
        "native_script",
    }:

        def change(value):
            if mutation == "source":
                value["source_commit"] = "f" * 40
            elif mutation == "version":
                value["version"] = "1.0.0"
            elif mutation == "missing_read":
                value["modes"].pop()
            elif mutation == "returncode_bool":
                value["modes"][0]["returncode"] = False
            elif mutation == "mode_failure":
                value["modes"][0]["ok"] = False
            elif mutation == "native_script":
                value["script_sha256"] = "f" * 64
            else:
                value["modes"][0]["result"]["source_commit"] = "f" * 40

        replace(root / "native/summary.json", change)
    elif mutation == "native_host":
        replace(root / "native/host.json", lambda v: v.update(sys_platform="linux"))
    elif mutation == "materials":
        replace(root / "materials.json", lambda v: v.update(blocked_issue_ids=["retained-issue"]))
    elif mutation == "map":
        replace(root / "materials.json", lambda v: v.update(materials_map_sha256="f" * 64))
    else:
        replace(root / "materials.json", lambda v: v.update(reviewed_nonblocking_issue_ids=[]))
    with pytest.raises((ValueError, FileNotFoundError)):
        P.admit(evidence, COMMIT, TAG)


class FakeGitHub:
    def __init__(self, fault=None):
        self.fault = fault
        self.release = None
        self.assets = []
        self.writes = []

    def call(self, method, path, data=None, **kwargs):
        if path.startswith("git/ref/"):
            return {"object": {"type": "commit", "sha": COMMIT}}
        if method == "GET":
            if path.startswith("releases?"):
                return [copy.deepcopy(self.release)] if self.release else []
            return copy.deepcopy(self.assets if "/assets?" in path else self.release)
        self.writes.append((method, path))
        name = path.split("name=")[1]
        asset = {
            "name": name,
            "state": "uploaded",
            "size": len(data),
            "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
        }
        self.assets.append(asset)
        if self.fault == "upload":
            raise TimeoutError()
        return asset

    def write(self, method, path, value):
        self.writes.append((method, path))
        if method == "POST":
            self.release = {**value, "id": 17, "assets": []}
            if self.fault == "create":
                raise TimeoutError()
        else:
            self.release.update(value)
            if self.fault == "publish":
                raise TimeoutError()
        return copy.deepcopy(self.release)


@pytest.mark.parametrize("fault", [None, "create", "upload", "publish"])
def test_publisher_reconciles_each_uncertain_write_without_retry(evidence, fault):
    admission = P.admit(evidence, COMMIT, TAG)
    P.write(evidence / "admission.json", admission)
    api = FakeGitHub(fault)
    assert publisher.publish(api, evidence, admission, "run:1")["draft"] is False
    assert len(api.writes) == 5  # create + three assets + final publish, exactly once each


def test_publisher_refuses_existing_release_without_writes(evidence):
    api = FakeGitHub()
    api.release = {"draft": True, "id": 17, "tag_name": TAG}
    with pytest.raises(ValueError, match="Existing release"):
        publisher.publish(api, evidence, P.admit(evidence, COMMIT, TAG), "run:1")
    assert api.writes == []


def test_candidate_validation_receipt_never_admits(evidence):
    replace(
        evidence / "linux-x64/build.json",
        lambda value: value.update(candidate_validation_only=True),
    )
    with pytest.raises(ValueError, match="Candidate validation"):
        P.admit(evidence, COMMIT, TAG)


def test_remote_digest_mismatch_retains_draft_and_never_publishes(evidence):
    api = FakeGitHub()
    original = api.call

    def corrupt(method, path, *args, **kwargs):
        result = original(method, path, *args, **kwargs)
        if method == "POST":
            result["digest"] = "sha256:" + "f" * 64
        return result

    api.call = corrupt
    admission = P.admit(evidence, COMMIT, TAG)
    P.write(evidence / "admission.json", admission)
    with pytest.raises(ValueError, match="identity unconfirmed"):
        publisher.publish(api, evidence, admission, "run:1")
    assert api.release["draft"] is True
    assert not any(method == "PATCH" for method, _ in api.writes)


def test_unreconciled_create_never_retries_or_uploads(evidence):
    api = FakeGitHub()

    def denied(method, path, value):
        api.writes.append((method, path))
        raise TimeoutError()

    api.write = denied
    with pytest.raises(ValueError, match="uncertain"):
        publisher.publish(api, evidence, P.admit(evidence, COMMIT, TAG), "run:1")
    assert api.writes == [("POST", "releases")]


def test_draft_listing_blocks_even_when_published_by_tag_returns_404(evidence):
    api = FakeGitHub()
    api.release = {"id": 17, "tag_name": TAG, "draft": True, "assets": []}
    original = api.call

    def call(method, path, *args, **kwargs):
        if path.startswith("releases/tags/"):
            return None  # Published-by-tag endpoint does not disclose this draft.
        return original(method, path, *args, **kwargs)

    api.call = call
    assert api.call("GET", "releases/tags/" + TAG) is None
    with pytest.raises(ValueError, match="Existing release/draft"):
        publisher.publish(api, evidence, P.admit(evidence, COMMIT, TAG), "run:1")
    assert api.writes == []


def test_uncertain_create_reconciles_matching_empty_draft_beyond_first_page(evidence):
    api = FakeGitHub("create")
    original = api.call
    pages = []

    def call(method, path, *args, **kwargs):
        if path.startswith("releases?"):
            pages.append(path)
            if path.endswith("page=1"):
                return [{"id": 1000 + i, "tag_name": "older-" + str(i)} for i in range(100)]
            return [copy.deepcopy(api.release)] if api.release else []
        return original(method, path, *args, **kwargs)

    api.call = call
    admission = P.admit(evidence, COMMIT, TAG)
    P.write(evidence / "admission.json", admission)
    assert publisher.publish(api, evidence, admission, "run:1")["draft"] is False
    assert any(path.endswith("page=2") for path in pages)
    assert len(api.writes) == 5


@pytest.mark.parametrize("case", ["other_run", "nonempty", "ambiguous"])
def test_uncertain_create_cannot_adopt_conflicting_draft(evidence, case):
    api = FakeGitHub("create")
    original = api.call

    def call(method, path, *args, **kwargs):
        if path.startswith("releases?") and api.release:
            drafts = [copy.deepcopy(api.release)]
            if case == "other_run":
                drafts[0]["body"] = "another run"
            elif case == "nonempty":
                drafts[0]["assets"] = [{"id": 3}]
            else:
                drafts.append({**drafts[0], "id": 18})
            return drafts
        return original(method, path, *args, **kwargs)

    api.call = call
    with pytest.raises(ValueError, match="uncertain"):
        publisher.publish(api, evidence, P.admit(evidence, COMMIT, TAG), "run:1")
    assert api.writes == [("POST", "releases")]


def test_incomplete_listing_fails_without_create(evidence):
    api = FakeGitHub()
    pages = []
    original = api.call

    def call(method, path, *args, **kwargs):
        if path.startswith("releases?"):
            pages.append(path)
            page = int(path.rsplit("=", 1)[1])
            return [{"id": page * 100 + i, "tag_name": "old"} for i in range(100)]
        return original(method, path, *args, **kwargs)

    api.call = call
    with pytest.raises(ValueError, match="completeness limit"):
        publisher.publish(api, evidence, P.admit(evidence, COMMIT, TAG), "run:1")
    assert len(pages) == 10 and api.writes == []


def test_repeated_release_ids_during_pagination_fail_without_create(evidence):
    api = FakeGitHub()
    original = api.call

    def call(method, path, *args, **kwargs):
        if path.startswith("releases?"):
            return [{"id": i + 1, "tag_name": "old"} for i in range(100)]
        return original(method, path, *args, **kwargs)

    api.call = call
    with pytest.raises(ValueError, match="ambiguous or changed"):
        publisher.publish(api, evidence, P.admit(evidence, COMMIT, TAG), "run:1")
    assert api.writes == []


@pytest.mark.parametrize("name", ["../escape", "C:/escape", "a/../../escape", "CON", "a\\b"])
def test_input_archive_traversal_rejected(tmp_path, name):
    import zipfile

    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(name.replace("\\", "/"), b"bad")
    if "\\" in name:
        # Windows ZipInfo normalizes backslashes while writing; mutate stored
        # header names so this tests the actual hostile archive input.
        archive.write_bytes(
            archive.read_bytes().replace(name.replace("\\", "/").encode(), name.encode())
        )
    with pytest.raises(ValueError):
        P.extract(archive, tmp_path / "extracted")


@pytest.mark.parametrize("format", ["zip", "tar"])
@pytest.mark.parametrize(
    "names",
    [
        ["Case/a.txt", "case/b.txt"],
        ["dir", "dir/child"],
        ["dir/child", "dir"],
        ["dir/a", "DIR/b"],
        ["same", "same"],
    ],
)
def test_portable_archive_collisions_fail_during_plan_before_output(tmp_path, format, names):
    import io
    import tarfile
    import zipfile

    archive = tmp_path / ("input." + format)
    if format == "zip":
        with zipfile.ZipFile(archive, "w") as bundle:
            for name in names:
                bundle.writestr(name, b"data")
    else:
        with tarfile.open(archive, "w") as bundle:
            for name in names:
                item = tarfile.TarInfo(name)
                item.size = 4
                bundle.addfile(item, io.BytesIO(b"data"))
    with pytest.raises(ValueError, match="collision|ambiguous|Duplicate"):
        P.extract(archive, tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("format", ["zip", "tar"])
def test_portable_archive_preserves_consistent_official_style_directories(tmp_path, format):
    import io
    import tarfile
    import zipfile

    names = [
        "blender-5.2.2-windows-x64/",
        "blender-5.2.2-windows-x64/lib/",
        "blender-5.2.2-windows-x64/lib/a.dll",
        "blender-5.2.2-windows-x64/lib/b.dll",
    ]
    archive = tmp_path / ("official-layout." + format)
    if format == "zip":
        with zipfile.ZipFile(archive, "w") as bundle:
            for name in names:
                bundle.writestr(name, b"" if name.endswith("/") else b"inert")
    else:
        with tarfile.open(archive, "w") as bundle:
            for name in names:
                item = tarfile.TarInfo(name)
                item.type = tarfile.DIRTYPE if name.endswith("/") else tarfile.REGTYPE
                item.size = 0 if item.isdir() else 5
                bundle.addfile(item, None if item.isdir() else io.BytesIO(b"inert"))
    P.extract(archive, tmp_path / "output")
    assert (tmp_path / "output" / names[-1]).read_bytes() == b"inert"
