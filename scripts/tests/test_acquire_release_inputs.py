import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

P = Path(__file__).parents[1] / "acquire_release_inputs.py"
spec = importlib.util.spec_from_file_location("acquire_release_inputs", P)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


@pytest.mark.parametrize(
    "name",
    [
        "../x",
        "a/../x",
        "/x",
        "C:/x",
        "a:b",
        "a\\b",
        "a//b",
        "NUL",
        "x/COM1.txt",
        "a.",
        "a ",
        "x\x00a",
    ],
)
def test_hostile_paths(name):
    with pytest.raises(a.AcquisitionError):
        a.safe_path(name)


@pytest.mark.parametrize(
    "names", [["A", "a"], ["a", "a"], ["a", "a/b"], ["A/x", "a/y"]]
)
def test_collisions(names):
    with pytest.raises(a.AcquisitionError):
        a.check_paths(names)


def fixture(tmp_path, kind="zip", member="a", body=b"hello", link=False):
    path = tmp_path / ("input." + kind)
    if kind == "zip":
        with zipfile.ZipFile(path, "w") as z:
            i = zipfile.ZipInfo(member)
            if link:
                i.external_attr = 0o120777 << 16
            z.writestr(i, body)
    else:
        with tarfile.open(path, "w") as t:
            i = tarfile.TarInfo(member)
            i.size = len(body)
            if link:
                i.type = tarfile.SYMTYPE
                i.linkname = "outside"
                i.size = 0
            t.addfile(i, io.BytesIO(body))
    data = path.read_bytes()
    artifact = {
        "filename": path.name,
        "size": len(data),
        "sha256": a.sha(data),
        "format": kind,
        "inert_case_alias_prefixes": [],
        "url": "https://files.pythonhosted.org/" + path.name,
    }
    row = {
        "archive": path.name,
        "member": member,
        "destination": "runtime/a",
        "size": len(body),
        "sha256": a.sha(body),
        "mode": 420,
    }
    return path, artifact, row


@pytest.mark.parametrize("kind", ["zip", "tar"])
def test_valid_data_only(tmp_path, kind):
    path, artifact, row = fixture(tmp_path, kind)
    assert a.inspect_archive(path, artifact, [row]) == [(row, b"hello")]


@pytest.mark.parametrize("kind", ["zip", "tar"])
def test_mapped_links_rejected(tmp_path, kind):
    path, artifact, row = fixture(tmp_path, kind, link=True)
    with pytest.raises(a.AcquisitionError):
        a.inspect_archive(path, artifact, [row])


@pytest.mark.parametrize("kind", ["zip", "tar"])
def test_archive_traversal_rejected(tmp_path, kind):
    path, artifact, row = fixture(tmp_path, kind, member="../outside")
    with pytest.raises(a.AcquisitionError):
        a.inspect_archive(path, artifact, [row])
    assert not (tmp_path.parent / "outside").exists()


def test_hash_before_parse(tmp_path):
    path, artifact, row = fixture(tmp_path)
    artifact["sha256"] = "0" * 64
    with pytest.raises(a.AcquisitionError, match="checksum"):
        a.inspect_archive(path, artifact, [row])


def test_duplicate_zip(tmp_path):
    path, artifact, row = fixture(tmp_path)
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("A", b"hello")
    artifact.update(size=path.stat().st_size, sha256=a.sha(path.read_bytes()))
    with pytest.raises(a.AcquisitionError, match="collision"):
        a.inspect_archive(path, artifact, [row])


def test_bad_lock_no_write(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"schema":1}')
    with pytest.raises(a.AcquisitionError):
        a.acquire(path, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_duplicate_json(tmp_path):
    p = tmp_path / "a.json"
    p.write_text('{"x":1,"x":2}')
    with pytest.raises(a.AcquisitionError):
        a.read_json(p)


def test_unknown_hosts():
    for u in [
        "http://files.pythonhosted.org/x",
        "https://user:pass@github.com/x",
        "https://example.com/x",
        "file:///tmp/x",
        "https://github.com:444/x",
    ]:
        with pytest.raises(a.AcquisitionError):
            a.validate_url(u)


def test_missing_member(tmp_path):
    path, artifact, row = fixture(tmp_path)
    row["member"] = "missing"
    with pytest.raises(a.AcquisitionError, match="missing"):
        a.inspect_archive(path, artifact, [row])


def test_member_digest(tmp_path):
    path, artifact, row = fixture(tmp_path)
    row["sha256"] = "0" * 64
    with pytest.raises(a.AcquisitionError, match="checksum"):
        a.inspect_archive(path, artifact, [row])


def test_invalid_deb():
    with pytest.raises(a.AcquisitionError):
        a.deb_payload(b"garbage")


def make_lock(artifact, row):
    inv = [
        {
            "path": row["destination"],
            "mode": row["mode"],
            "size": row["size"],
            "sha256": row["sha256"],
        }
    ]
    return {
        "schema": 1,
        "platform": "linux-x64",
        "inventory_sha256": a.sha(a.canonical(inv)),
        "archives": [artifact],
        "files": [row],
    }


def test_offline_acquisition_and_no_clobber(tmp_path, monkeypatch):
    path, artifact, row = fixture(tmp_path)
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps(make_lock(artifact, row)))
    monkeypatch.setattr(a, "download", lambda artifact, cache: path)
    work = tmp_path / "new"
    receipt = a.acquire(lock, work)
    assert receipt["runtime_file_count"] == 1
    assert (work / "runtime/runtime/a").read_bytes() == b"hello"
    before = (work / "acquisition-receipt.json").read_bytes()
    with pytest.raises(a.AcquisitionError, match="exists"):
        a.acquire(lock, work)
    assert (work / "acquisition-receipt.json").read_bytes() == before


def test_bad_inventory_binding_no_write(tmp_path):
    _path, artifact, row = fixture(tmp_path)
    data = make_lock(artifact, row)
    data["inventory_sha256"] = "0" * 64
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps(data))
    with pytest.raises(a.AcquisitionError, match="inventory"):
        a.acquire(lock, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_archive_expansion_budget(tmp_path, monkeypatch):
    path, artifact, row = fixture(tmp_path)
    monkeypatch.setattr(a, "MAX_EXPANDED", 4)
    with pytest.raises(a.AcquisitionError, match="expansion"):
        a.inspect_archive(path, artifact, [row])


def test_parent_link_rejected(tmp_path):
    path, artifact, row = fixture(tmp_path)
    with zipfile.ZipFile(path, "a") as z:
        i = zipfile.ZipInfo("parent")
        i.external_attr = 0o120777 << 16
        z.writestr(i, b"outside")
        z.writestr("parent/child", b"hello")
    artifact.update(size=path.stat().st_size, sha256=a.sha(path.read_bytes()))
    with pytest.raises(a.AcquisitionError, match="parent"):
        a.inspect_archive(path, artifact, [row])


def test_wrong_output_modes_and_extra_file(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    f = root / "a"
    f.write_bytes(b"hello")
    f.chmod(0o600)
    inv = [{"path": "a", "mode": 420, "size": 5, "sha256": a.sha(b"hello")}]
    with pytest.raises(a.AcquisitionError, match="inventory"):
        a.verify_tree(root, inv)
    f.chmod(0o644)
    (root / "extra").write_bytes(b"")
    with pytest.raises(a.AcquisitionError, match="inventory"):
        a.verify_tree(root, inv)


def test_preserve_inert_unselected_link(tmp_path):
    path, artifact, row = fixture(tmp_path, "tar")
    with tarfile.open(path, "a") as t:
        i = tarfile.TarInfo("alias")
        i.type = tarfile.SYMTYPE
        i.linkname = "a"
        t.addfile(i)
    artifact.update(size=path.stat().st_size, sha256=a.sha(path.read_bytes()))
    assert a.inspect_archive(path, artifact, [row]) == [(row, b"hello")]


def test_inert_case_aliases_are_explicit_and_unmapped(tmp_path):
    path, artifact, row = fixture(tmp_path)
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("inert/A", b"a")
        z.writestr("inert/a", b"b")
    artifact.update(size=path.stat().st_size, sha256=a.sha(path.read_bytes()))
    with pytest.raises(a.AcquisitionError, match="collision"):
        a.inspect_archive(path, artifact, [row])
    artifact["inert_case_alias_prefixes"] = ["inert"]
    assert a.inspect_archive(path, artifact, [row]) == [(row, b"hello")]
    row["member"] = "inert/A"
    with pytest.raises(a.AcquisitionError, match="inert"):
        a.validate_lock(make_lock(artifact, row))


def test_reused_cache_is_rehashed(tmp_path):
    path, artifact, row = fixture(tmp_path)
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps(make_lock(artifact, row)))
    path.write_bytes(b"corrupt")
    with pytest.raises(a.AcquisitionError, match="size"):
        a.acquire(lock, tmp_path / "new", tmp_path)
    assert not (tmp_path / "new/acquisition-receipt.json").exists()
    assert not (tmp_path / "new/runtime/runtime/a").exists()


def test_work_parent_symlink_no_write(tmp_path):
    _path, artifact, row = fixture(tmp_path)
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps(make_lock(artifact, row)))
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(a.AcquisitionError, match="linked"):
        a.acquire(lock, alias / "new")
    assert not (target / "new").exists()


def test_lock_mutation_cannot_emit_misbound_receipt(tmp_path, monkeypatch):
    path, artifact, row = fixture(tmp_path)
    lock = tmp_path / "lock.json"
    original = json.dumps(make_lock(artifact, row)).encode()
    lock.write_bytes(original)

    def mutating_download(artifact, cache):
        lock.write_bytes(original + b"\n")
        return path

    monkeypatch.setattr(a, "download", mutating_download)
    work = tmp_path / "new"
    with pytest.raises(a.AcquisitionError, match="lock changed"):
        a.acquire(lock, work)
    assert not (work / "acquisition-receipt.json").exists()
    assert not (work / "runtime-inventory.json").exists()
    assert (work / "runtime/runtime/a").read_bytes() == b"hello"


def test_receipt_binds_exact_original_lock_bytes(tmp_path, monkeypatch):
    path, artifact, row = fixture(tmp_path)
    lock = tmp_path / "lock.json"
    original = json.dumps(make_lock(artifact, row), indent=3).encode() + b"\n\n"
    lock.write_bytes(original)
    monkeypatch.setattr(a, "download", lambda artifact, cache: path)
    receipt = a.acquire(lock, tmp_path / "new")
    assert receipt["acquisition_lock_sha256"] == a.sha(original)


@pytest.mark.parametrize("schema", [True, False, 1.0])
def test_schema_strict_integer_no_write(tmp_path, schema):
    _path, artifact, row = fixture(tmp_path)
    data = make_lock(artifact, row)
    data["schema"] = schema
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps(data))
    with pytest.raises(a.AcquisitionError, match="unsupported lock"):
        a.acquire(lock, tmp_path / "new")
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_no_write(tmp_path, constant):
    lock = tmp_path / "lock.json"
    lock.write_text('{"schema":' + constant + "}")
    with pytest.raises(a.AcquisitionError, match="nonfinite"):
        a.acquire(lock, tmp_path / "new")
    assert not (tmp_path / "new").exists()
