"""Official-layout inert TAR fixtures; no runtime execution or filesystem links."""

import importlib.util
import io
import sys
import tarfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = load("blender_release_archive")
P = load("release_pipeline")
LIB = B.PREFIX + "/lib/"


def member(name, kind=tarfile.REGTYPE, target="", size=0):
    item = tarfile.TarInfo(name)
    item.type, item.linkname, item.size = kind, target, size
    item.mode = 0o644
    return item


def layout():
    # Representative real Blender 5.2.2 link chain and direct malloc alias.
    names = {
        LIB + "libMaterialXRender.so": "libMaterialXRender.so.1",
        LIB + "libMaterialXRender.so.1": "libMaterialXRender.so.1.39.4",
        LIB + "libtbbmalloc.so": "libtbbmalloc.so.2",
    }
    rows = [
        member(LIB + "libMaterialXRender.so.1.39.4", size=5),
        member(LIB + "libtbbmalloc.so.2", size=5),
    ]
    rows += [member(name, tarfile.SYMTYPE, target) for name, target in names.items()]
    return rows, names


def test_representative_official_links_become_verified_independent_regular_bytes(tmp_path):
    rows, links = layout()
    archive = tmp_path / "inert.tar"
    with tarfile.open(archive, "w") as bundle:
        for row in rows:
            bundle.addfile(row, io.BytesIO(b"inert") if row.isfile() else None)
    with tarfile.open(archive) as bundle:
        entries, resolved = B.plan(bundle, links)
        aliases = B.normalize(bundle, entries, resolved, tmp_path / "normalized")
    assert len(aliases) == 3
    for name, original in resolved.items():
        output = tmp_path / "normalized" / name
        assert output.read_bytes() == b"inert" and not output.is_symlink()
        assert output.stat().st_nlink == 1
        assert B.identity(output) == B.identity(tmp_path / "normalized" / original)
    assert resolved[LIB + "libMaterialXRender.so"] == LIB + "libMaterialXRender.so.1.39.4"
    assert all(row["bytes"] == 5 for row in aliases)
    # Ordinary source/materials TAR extraction retains its strict no-link policy.
    with pytest.raises(ValueError, match="Nonregular"):
        P.extract(archive, tmp_path / "materials")


@pytest.mark.parametrize(
    "target",
    [
        "/etc/passwd",
        "../target.so",
        "..\\target.so",
        "C:/target.so",
        "subdir/target.so",
        "missing.so",
    ],
)
def test_malicious_or_absent_target_rejects(target):
    name = LIB + "alias.so"
    rows = [member(LIB + "target.so", size=5), member(name, tarfile.SYMTYPE, target)]
    with pytest.raises(ValueError):
        B.plan(rows, {name: target})


@pytest.mark.parametrize(
    "case",
    [
        "cycle",
        "unreviewed",
        "missing_alias",
        "mismatched_alias",
        "duplicate",
        "case_collision",
        "implicit_case_collision",
        "directory_target",
        "link_parent",
        "file_parent",
        "hardlink",
        "fifo",
        "sparse",
        "absolute_member",
        "traversing_member",
    ],
)
def test_invalid_member_and_link_graph_rejects(case):
    rows, links = layout()
    if case == "cycle":
        rows[-3].linkname = "libMaterialXRender.so.1"
        rows[-2].linkname = "libMaterialXRender.so"
        links[rows[-2].name] = rows[-2].linkname
    elif case == "unreviewed":
        links.pop(rows[-1].name)
    elif case == "missing_alias":
        rows.pop()
    elif case == "mismatched_alias":
        links[rows[-1].name] = "other.so"
    elif case == "duplicate":
        rows.append(rows[-1])
    elif case == "case_collision":
        rows.append(member(LIB + "LIBTBBMALLOC.so.2", size=1))
    elif case == "implicit_case_collision":
        rows += [member(LIB + "case/a", size=1), member(LIB + "Case/b", size=1)]
    elif case == "directory_target":
        rows[1] = member(rows[1].name, tarfile.DIRTYPE)
    elif case == "link_parent":
        rows.append(member(rows[-1].name + "/child", size=1))
    elif case == "file_parent":
        rows.append(member(rows[0].name + "/child", size=1))
    elif case in {"hardlink", "fifo"}:
        rows[-1].type = tarfile.LNKTYPE if case == "hardlink" else tarfile.FIFOTYPE
    elif case == "sparse":
        rows[0].sparse = [(0, 5)]
    elif case == "absolute_member":
        rows.append(member("/tmp/escape", size=1))
    else:
        rows.append(member(B.PREFIX + "/lib/../../escape", size=1))
    with pytest.raises(ValueError):
        B.plan(rows, links)


@pytest.mark.parametrize(
    "limits",
    [
        {"max_depth": 1},
        {"max_files": 4},
        {"max_total": 20},
        {"max_member": 4},
        {"max_total": B.MAX_TOTAL + 1},
        {"max_depth": True},
    ],
)
def test_link_copies_count_against_all_budgets(limits):
    rows, links = layout()
    with pytest.raises(ValueError):
        B.plan(rows, links, **limits)


def test_unpinned_blender_archive_is_rejected_before_writes(tmp_path):
    archive = tmp_path / "fake.tar.xz"
    archive.write_bytes(b"untrusted")
    record = {"url": B.ARCHIVE_URL, "sha256": B.ARCHIVE_SHA256, "bytes": B.ARCHIVE_BYTES}
    with pytest.raises(ValueError, match="identity mismatch"):
        B.extract(archive, tmp_path / "output", record)
    assert not (tmp_path / "output").exists()
    record["url"] = "https://example.invalid/substitute"
    with pytest.raises(ValueError, match="Only pinned"):
        B.extract(archive, tmp_path / "output", record)


def test_reviewed_link_manifest_is_exactly_finite():
    links = B.reviewed_links()
    assert len(links) == 79
    assert links[LIB + "libMaterialXRender.so.1"] == "libMaterialXRender.so.1.39.4"
    assert links[LIB + "libtbbmalloc.so"] == "libtbbmalloc.so.2"
