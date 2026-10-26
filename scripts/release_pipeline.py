"""Release orchestration. Missing reviewed inputs or native evidence fails closed."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = {"linux-x64", "windows-x64"}


def require(value, message):
    if not value:
        raise ValueError(message)


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load("build_release_candidate")


def read(path):
    return A.strict_json(A.read_metadata(Path(path)))


def write(path, value):
    with Path(path).open("xb") as stream:
        stream.write(A.canonical(value))


def identity(path):
    A.checked_path(path)
    require(Path(path).is_file(), "Expected regular artifact")
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest(), Path(path).stat().st_size


def fetch(record, target):
    require(set(record) == {"url", "sha256", "bytes"}, "Unexpected download fields")
    url = urllib.parse.urlsplit(record["url"])
    require(
        url.scheme == "https"
        and url.hostname
        and not url.username
        and not url.password
        and not url.fragment,
        "Expected HTTPS download",
    )
    require(
        type(record["bytes"]) is int and 0 < record["bytes"] <= 4_000_000_000, "Download size limit"
    )
    digest = hashlib.sha256()
    total = 0
    with (
        urllib.request.urlopen(record["url"], timeout=120) as source,
        Path(target).open("xb") as out,
    ):
        require(urllib.parse.urlsplit(source.url).scheme == "https", "Insecure redirect")
        while chunk := source.read(1024 * 1024):
            total += len(chunk)
            require(total <= record["bytes"], "Download exceeds pinned size")
            digest.update(chunk)
            out.write(chunk)
    require(
        (digest.hexdigest(), total) == (record["sha256"], record["bytes"]),
        "Download identity mismatch; retain failed input",
    )


def archive_plan(rows):
    """Validate all explicit/implicit path components before any extraction write."""
    entries, spellings, kinds, total = {}, {}, {}, 0
    for name, directory, mode, size, item in rows:
        require(len(entries) < 100_000, "Archive entry count exceeds budget")
        require("\\" not in name, "Nonportable archive separator")
        parts = A.source_path_parts(name)
        require(name not in entries, "Duplicate archive member")
        for depth in range(1, len(parts) + 1):
            prefix = "/".join(parts[:depth])
            require(
                spellings.setdefault(prefix.casefold(), prefix) == prefix,
                "Case-ambiguous archive path component",
            )
            kind = "directory" if depth < len(parts) or directory else "file"
            require(
                prefix not in kinds or kinds[prefix] == kind, "Archive file/directory collision"
            )
            kinds[prefix] = kind
        require(type(size) is int and 0 <= size <= 2_000_000_000, "Member size budget")
        require(not directory or size == 0, "Directory payload is unsupported")
        total += size
        require(total <= 8_000_000_000, "Archive expansion exceeds budget")
        entries[name] = (directory, mode, size, item)
    return entries


def extract(archive, destination):
    """Strict file-only input extraction; Blender link normalization is separate."""

    def output(bundle, rows):
        entries = archive_plan(rows)
        A.checked_path(destination.parent)
        destination.mkdir(exist_ok=False)
        for name, (directory, mode, size, item) in entries.items():
            path = destination / name
            if directory:
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            source = (
                bundle.open(item)
                if isinstance(bundle, zipfile.ZipFile)
                else bundle.extractfile(item)
            )
            total = 0
            with source, path.open("xb") as target:
                while chunk := source.read(min(1024 * 1024, size - total + 1)):
                    total += len(chunk)
                    require(total <= size, "Archive member grew during extraction")
                    target.write(chunk)
            require(total == size, "Extracted size mismatch")
            path.chmod(0o755 if mode & 0o111 else 0o644)

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:

            def rows():
                for item in bundle.infolist():
                    require(
                        item.orig_filename == item.filename and "\\" not in item.orig_filename,
                        "Normalized ZIP member name is not authoritative",
                    )
                    mode, directory = item.external_attr >> 16, item.is_dir()
                    require(
                        stat.S_IFMT(mode)
                        in ({0, stat.S_IFDIR} if directory else {0, stat.S_IFREG}),
                        "Nonregular ZIP entry",
                    )
                    yield (
                        item.filename.rstrip("/") if directory else item.filename,
                        directory,
                        mode,
                        item.file_size,
                        item,
                    )

            output(bundle, rows())
    else:
        with tarfile.open(archive) as bundle:

            def rows():
                for item in bundle:
                    require(item.isdir() or item.isfile(), "Nonregular TAR entry")
                    require(
                        item.sparse is None
                        and not any(k.startswith("GNU.sparse") for k in item.pax_headers),
                        "Sparse TAR entry",
                    )
                    yield (
                        item.name.rstrip("/") if item.isdir() else item.name,
                        item.isdir(),
                        item.mode,
                        item.size,
                        item,
                    )

            output(bundle, rows())


def config(path):
    value = read(path)
    require(
        set(value) == {"schema_version", "platforms"}
        and type(value["schema_version"]) is int
        and value["schema_version"] == 1,
        "Unknown pipeline configuration",
    )
    require(set(value["platforms"]) == PLATFORMS, "Both platform inputs required")
    for row in value["platforms"].values():
        require(
            set(row)
            == {
                "prepared",
                "acquisition_lock",
                "blender",
                "blender_path",
                "runtime_lock_sha256",
                "materials_map_sha256",
                "review_sha256",
            },
            "Unknown platform configuration",
        )
        A.source_path_parts(row["acquisition_lock"])
        require(
            row["acquisition_lock"].startswith("release_inputs/"), "Lock outside release inputs"
        )
        A.source_path_parts(row["blender_path"])
    return value


def acquire_runtime(platform, acquisition_lock, work):
    """Use the same reviewed data-only adapter for both Linux-built target locks."""
    require(read(acquisition_lock)["platform"] == platform, "Acquisition lock target mismatch")
    acquired = load("acquire_release_inputs").acquire(acquisition_lock, work)
    require(
        acquired["platform"] == platform and acquired["native_execution"] is False,
        "Acquisition platform mismatch",
    )
    require(
        acquired["acquisition_lock_sha256"] == identity(acquisition_lock)[0],
        "Acquisition lock receipt mismatch",
    )
    return acquired


def build(platform, configuration, work, commit, tag, candidate_only=False):
    require(sys.platform == "linux", "Both targets are assembled on Linux")
    row = config(configuration)["platforms"][platform]
    work.mkdir()
    fetch(row["prepared"], work / "prepared.zip")
    extract(work / "prepared.zip", work / "inputs")
    inputs = work / "inputs"
    require(
        {p.name for p in inputs.iterdir()} == {"materials", "metadata", "review.json"},
        "Prepared inputs must supply materials, metadata and review only",
    )
    acquisition_lock = ROOT / row["acquisition_lock"]
    acquire_runtime(platform, acquisition_lock, work / "acquired")
    shutil.move(work / "acquired/runtime", inputs / "runtime")
    require(
        read(work / "acquired/runtime-inventory.json")
        == read(inputs / "metadata/runtime-inventory.json"),
        "Reviewed inventory differs",
    )
    review = inputs / "review.json"
    # The builder requires the input root to contain only its three defined trees.
    review.rename(work / "review.json")
    common = dict(
        source_repo=ROOT,
        source_commit=commit,
        tag=tag,
        platform=platform,
        inputs_root=inputs,
        main_ref="refs/remotes/origin/main",
        runtime_lock_sha256=row["runtime_lock_sha256"],
        materials_map_sha256=row["materials_map_sha256"],
    )
    if candidate_only:
        common["candidate_only"] = True
    materials = load("check_release_materials").check(
        argparse.Namespace(
            **common,
            review=work / "review.json",
            review_sha256=row["review_sha256"],
            work_parent=work,
        )
    )
    require(materials["status"] == "MATERIALS_REVIEW_RECORDED", "Materials review blocks release")
    write(work / "materials.json", materials)
    A.build(
        argparse.Namespace(**common, output=work / "candidate.zip", receipt=work / "build.json")
    )


def qualify(platform, configuration, work, commit, tag, candidate_only=False):
    require(
        sys.platform == ("win32" if platform == "windows-x64" else "linux"), "Native OS mismatch"
    )
    row = config(configuration)["platforms"][platform]
    fetch(row["blender"], work / "blender.archive")
    if platform == "linux-x64":
        archive_policy = load("blender_release_archive")
        require(
            row["blender_path"] == archive_policy.PREFIX + "/blender",
            "Unexpected pinned Linux Blender executable",
        )
        normalized = archive_policy.extract(
            work / "blender.archive", work / "blender", row["blender"]
        )
        write(work / "blender-normalization.json", normalized)
    else:
        extract(work / "blender.archive", work / "blender")
    summary = load("qualify_standalone_candidate").qualify(
        blender=work / "blender" / row["blender_path"],
        archive=work / "candidate.zip",
        source_commit=commit,
        version=tag[1:],
        work_root=work / "native",
    )
    require(summary["ok"] is True, "Native qualification failed")
    write(work / "native/host.json", {"platform": platform, "sys_platform": sys.platform})


def admit(root, commit, tag):
    """Consume actual stage outputs, binding every platform to the same source."""
    A.source_identity(ROOT, commit, tag, "refs/remotes/origin/main")
    platforms = {}
    configuration_bytes = []
    source_inventories = set()
    for platform in sorted(PLATFORMS):
        work = root / platform
        configuration_bytes.append(A.read_metadata(work / "config.json"))
        row = config(work / "config.json")["platforms"][platform]
        host = read(work / "native/host.json")
        require(
            host
            == {
                "platform": platform,
                "sys_platform": "win32" if platform == "windows-x64" else "linux",
            },
            "Native host mismatch",
        )
        built, materials, native = (
            read(work / name) for name in ("build.json", "materials.json", "native/summary.json")
        )
        require(
            "candidate_validation_only" not in built
            and "candidate_validation_only" not in materials,
            "Candidate validation cannot authorize release publication",
        )
        require(
            built["status"] == A.STATUS and built["qualification"] == "NOT_RUN",
            "Unexpected build status",
        )
        require(
            built["platform"] == platform
            and built["source_commit"] == commit
            and built["tag"] == tag
            and built["version"] == tag[1:],
            "Build identity mismatch",
        )
        require(built["archive"] == "candidate.zip", "Unexpected archive basename")
        source_inventories.add(built["source_inventory_sha256"])
        for field in ("runtime_lock_sha256", "materials_map_sha256", "review_sha256"):
            require(materials[field] == row[field], "Reviewed configuration binding mismatch")
        sha, size = identity(work / "candidate.zip")
        require(
            (sha, size)
            == (built["sha256"], built["bytes"])
            == (native["archive_sha256"], native["archive_bytes"]),
            "Archive identity mismatch",
        )
        require(
            native["ok"] is True
            and native["source_commit"] == commit
            and native["version"] == tag[1:]
            and native["required_blender_version"] == "5.2.2",
            "Native source identity mismatch",
        )
        for field, relative in (
            ("script", "tests/blender_standalone_release_smoke.py"),
            ("fixture", "tests/fixtures/standalone_constrained_plate.mcad.json"),
        ):
            raw = subprocess.check_output(
                ["git", "-C", str(ROOT), "show", commit + ":" + relative],
                env=A.git_environment(),
                timeout=120,
            )
            require(
                (native[field + "_sha256"], native[field + "_bytes"])
                == (hashlib.sha256(raw).hexdigest(), len(raw)),
                "Qualification code mismatch",
            )
        require(
            [mode["mode"] for mode in native["modes"]] == ["install", "write", "read"],
            "Incomplete native modes",
        )
        for mode in native["modes"]:
            require(
                mode["ok"] is True
                and type(mode["returncode"]) is int
                and mode["returncode"] == 0
                and mode["result"]["ok"] is True,
                "Native mode did not pass",
            )
            for key, expected in {
                "mode": mode["mode"],
                "archive_sha256": sha,
                "source_commit": commit,
                "version": tag[1:],
                "blender": "5.2.2",
                "interactive_gui": False,
            }.items():
                require(
                    type(mode["result"].get(key)) is type(expected)
                    and mode["result"].get(key) == expected,
                    "Native result binding mismatch",
                )
        require(
            materials["status"] == "MATERIALS_REVIEW_RECORDED"
            and materials["blocked_component_ids"] == materials["blocked_issue_ids"] == []
            and materials["source_commit"] == commit
            and materials["platform"] == platform,
            "Materials admission failed",
        )
        for field in (
            "runtime_lock_sha256",
            "materials_map_sha256",
            "source_inventory_sha256",
            "runtime_inventory_sha256",
            "materials_inventory_sha256",
        ):
            require(materials[field] == built[field], "Materials/build binding mismatch")
        require(
            materials["retained_issue_ids"] == built["unresolved_material_issue_ids"]
            and materials["reviewed_nonblocking_issue_ids"] == materials["retained_issue_ids"],
            "Unaccounted materials issues",
        )
        platforms[platform] = {"sha256": sha, "bytes": size}
    require(
        len(source_inventories) == 1 and configuration_bytes[0] == configuration_bytes[1],
        "Platforms were built against different source/input configurations",
    )
    return {
        "schema_version": 1,
        "source_commit": commit,
        "tag": tag,
        "source_tree": A.git(ROOT, "rev-parse", commit + "^{tree}"),
        "platforms": platforms,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("configure", "build", "qualify", "admit"))
    parser.add_argument("--platform", choices=sorted(PLATFORMS))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--candidate-only", action="store_true")
    args = parser.parse_args()
    A.validation_identity(
        argparse.Namespace(
            source_repo=ROOT,
            source_commit=args.commit,
            tag=args.tag,
            main_ref="refs/remotes/origin/main",
            candidate_only=args.candidate_only,
        )
    )
    if args.stage == "configure":
        fetch(
            {
                "url": os.environ["RELEASE_INPUTS_URL"],
                "sha256": os.environ["RELEASE_INPUTS_SHA256"],
                "bytes": int(os.environ["RELEASE_INPUTS_BYTES"]),
            },
            args.work,
        )
        config(args.work)
    elif args.stage == "admit":
        require(not args.candidate_only, "Candidate mode cannot admit a release")
        write(args.work / "admission.json", admit(args.work, args.commit, args.tag))
    else:
        require(args.platform and args.config, "Platform/config required")
        globals()[args.stage](
            args.platform, args.config, args.work, args.commit, args.tag, args.candidate_only
        )


if __name__ == "__main__":
    main()
