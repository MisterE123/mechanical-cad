"""Offline Linux preview source refresh; never a review, build or release admission.

Accepts one pinned local seed as data. Exports selected public Git blobs, preserving
external runtime and historical declarations. No download or native execution.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "_linux_refresh_source_check", ROOT / "scripts/check_release_materials.py"
)
R = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(R)
A = R.A


def git_environment():
    # Local object reads only; do not inherit repo/index/worktree/config overrides
    # or silently fetch missing blobs from a partial clone during preparation.
    return {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
            "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
            "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull}


A.git_environment = git_environment  # Private imported adapter; source remains unchanged.
B = A.load_builder(ROOT)  # Trusted sibling validators, NEVER code from the seed/selected source.
STATUS = "CANDIDATE_INPUTS_REQUIRE_REVIEW_AND_NATIVE_QUALIFICATION"
PUBLIC_URL = "https://github.com/MisterE123/mechanical-cad.git"
RESERVE = 5 * 1024**3
MAX_ZIP = 400 * 1024**2
MAX_EXPANDED = 800 * 1024**2
MAX_MEMBER = 200 * 1024**2
MAX_ENTRIES = 20_000
PIN = {
    "size": 359256244,
    "sha256": "488703725d6523088b800ba219f634c4697d01932fe493a264323e641373cda3",
    "source_commit": "8d259b577107eb4556bd2a6c16d1eca41f020c9c",
    "packaged": "de23d94510970d440b08e638e870c5524b809cc91e8affcc2c8c90e9adc0c741",
    "acquisition": "a209e4a2e3f721465d77e68458a7a32802623bd4e25d4ae6c501354cd42d44de",
    "runtime_inventory": "a0edf4bec0050a9f16de7eceb3a91cb358bda29eef1f3c6050f543aea3953a9c",
    "runtime_lock": "bc5a72879cbdeabc4470fb5935bff27c72ffb9be76529a637768acacd180d489",
    "preparation_source": "3b1becf5e56e286a1203db80cae01d86da79ace11700888cc0be29c6999092c9",
    "runtime_count": 1030,
    "component_count": 42,
    "issue_count": 42,
}
IMPLEMENTATION_FILES = (
    "scripts/prepare_linux_preview_inputs.py",
    "scripts/build_release_candidate.py",
    "scripts/check_release_materials.py",
    "scripts/package_standalone_materials.py",
    "scripts/package_standalone_extension.py",
    "blender_addon/mechanical_cad_blender/runtime_bundle_manifest.py",
    "release_inputs/linux-x64/acquisition-lock.json",
    "docs/LINUX_PREVIEW_INPUT_REFRESH.md",
)


class RefreshError(ValueError):
    """Unsupported or mismatching input; no approval is implied."""


def require(condition, message):
    if not condition:
        raise RefreshError(message)


def file_record(path, relative):
    A.checked_path(path)
    with B.BUILDER._open(path) as stream:
        info = os.fstat(stream.fileno())
        return {"path": relative, "mode": stat.S_IMODE(info.st_mode),
                "size": info.st_size, "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}


def allocation_bytes(parent, size):
    block = max(4096, os.statvfs(parent).f_frsize)
    return ((size + block - 1) // block) * block


def reserve_space(parent, needed=0):
    require(shutil.disk_usage(parent).free >= RESERVE + allocation_bytes(parent, needed),
            "5 GiB free-disk reserve required")


def make_directory(path):
    ancestor, missing = path, 0
    while not ancestor.exists():
        missing += 1
        ancestor = ancestor.parent
    reserve_space(ancestor, (missing + 1) * max(4096, os.statvfs(ancestor).f_frsize))
    path.mkdir(parents=True, exist_ok=True)


def zip_budget(records):
    # Conservative raw DEFLATE expansion plus both ZIP headers, UTF-8 names,
    # filesystem allocation and central-directory bookkeeping.
    return sum(r["size"] + (r["size"] // 16384 + 1) * 8
               + 1024 + 2 * len(r["path"].encode("utf-8")) for r in records) + 4096


def write_new(path, data):
    reserve_space(path.parent, len(data) + 4096)
    with path.open("xb") as stream:
        stream.write(data)
    path.chmod(0o644)


@contextmanager
def checked_archive(raw):
    """Bound directory allocation first; require contiguous regular-only classic ZIP.

    No extractall, implicit directory entries, ZIP64, links, extras, encryption,
    trailing data, aliases or descriptors. Expanded byte ceilings replace unsafe
    compression-ratio heuristics (the real seed legitimately reaches 493:1).
    """
    raw.seek(0, 2)
    size = raw.tell()
    require(22 <= size <= MAX_ZIP, "Archive size outside bound")
    raw.seek(size - 22)
    sig, disk, cd_disk, disk_count, count, cd_size, offset, comment = struct.unpack(
        "<4s4H2LH", raw.read(22))
    require(sig == b"PK\x05\x06" and not disk and not cd_disk and not comment
            and 0 < count == disk_count <= MAX_ENTRIES and count < 65535
            and cd_size <= 8 * 1024**2 and offset + cd_size == size - 22,
            "Unbounded or unsupported ZIP directory")
    with zipfile.ZipFile(raw) as archive:
        infos = archive.infolist()
        require(len(infos) == count, "ZIP entry count mismatch")
        seen, prefixes, total, local_end = {}, {}, 0, 0
        for info in infos:
            name = info.filename
            parts = A.source_path_parts(name)
            key = name.casefold()
            require(key not in seen and info.orig_filename == name, "Duplicate or aliased ZIP path")
            seen[key] = info
            for index in range(1, len(parts) + 1):
                prefix = "/".join(parts[:index])
                require(prefixes.setdefault(prefix.casefold(), prefix) == prefix,
                        "Aliased ZIP directory")
            mode = info.external_attr >> 16
            require(not info.is_dir() and info.create_system == 3
                    and mode in {stat.S_IFREG | 0o644, stat.S_IFREG | 0o755}
                    and not info.external_attr & 0x10
                    and not info.flag_bits & ~0x800 and info.extract_version <= 20
                    and info.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    and not info.extra and not info.comment and not info.volume
                    and 0 <= info.file_size <= MAX_MEMBER, "Unsupported ZIP member")
            total += info.file_size
            require(total <= MAX_EXPANDED, "Expanded ZIP budget exceeded")
            require(info.header_offset == local_end, "ZIP gap, prefix or overlap")
            raw.seek(local_end)
            header = raw.read(30)
            require(len(header) == 30, "Truncated ZIP local header")
            sig, ver, flags, method, _, _, crc, compressed, expanded, namesize, extra = (
                struct.unpack("<4s5H3L2H", header))
            encoded = name.encode("utf-8" if flags & 0x800 else "cp437")
            require(sig == b"PK\x03\x04" and ver == info.extract_version
                    and flags == info.flag_bits and method == info.compress_type
                    and crc == info.CRC and compressed == info.compress_size
                    and expanded == info.file_size and namesize == len(encoded)
                    and not extra and raw.read(namesize) == encoded, "ZIP local metadata mismatch")
            local_end += 30 + namesize + compressed
            require(local_end <= offset, "ZIP overlaps directory")
        require(local_end == offset, "ZIP trailing local data")
        for name in seen:
            parts = name.split("/")
            require(not any("/".join(parts[:i]) in seen for i in range(1, len(parts))),
                    "ZIP file/directory collision")
        yield archive, {i.filename: i for i in infos}


def copy_member(archive, info, expected, output=None):
    require(info.filename == expected["path"] and info.file_size == expected["size"]
            and info.external_attr >> 16 == stat.S_IFREG | expected["mode"],
            "Member inventory size/mode/path mismatch")
    digest, length = hashlib.sha256(), 0
    with archive.open(info) as stream:
        while chunk := stream.read(min(1024**2, expected["size"] - length + 1)):
            length += len(chunk)
            require(length <= expected["size"], "Expanded member exceeds inventory")
            digest.update(chunk)
            if output is not None:
                output.write(chunk)
    require(length == expected["size"] and digest.hexdigest() == expected["sha256"],
            "Member inventory digest mismatch")


def json_member(archive, infos, name, expected_sha=None):
    require(name in infos and infos[name].file_size <= A.MAX_METADATA, "Missing/oversize metadata")
    data = archive.read(infos[name])
    if expected_sha is not None:
        require(A.digest(data) == expected_sha, "Pinned metadata identity mismatch: " + name)
    return data, A.strict_json(data)


def preserved_identity(materials_map):
    return {
        "nonproject_components_sha256": A.digest(A.canonical([
            c for c in materials_map["components"] if c["kind"] != "project_package"])),
        "historical_issues_sha256": A.digest(A.canonical(materials_map["unresolved_issues"])),
        "runtime_bindings_sha256": A.digest(A.canonical(materials_map["runtime_bindings"])),
    }


def seed_metadata(archive, infos):
    _, packaged = json_member(archive, infos, "PACKAGED_MATERIALS.json", PIN["packaged"])
    lock, _ = json_member(archive, infos, "runtime-lock.json", PIN["runtime_lock"])
    require(packaged["source_commit"] == PIN["source_commit"]
            and packaged["platform"] == "linux-x64"
            and packaged["runtime_lock_sha256"] == PIN["runtime_lock"]
            and packaged["runtime_inventory_sha256"] == PIN["runtime_inventory"],
            "Seed metadata identity mismatch")
    materials_map, materials = packaged["materials_map"], packaged["materials_inventory"]
    for key, value in (("materials_map", materials_map), ("materials_inventory", materials)):
        require(A.digest(A.canonical(value)) == packaged[key + "_sha256"], "Seed inventory/map mismatch")
    B.C.validate_file_inventory(materials, limits=B.MaterialsLimits())
    acquisition_data = A.read_metadata(ROOT / "release_inputs/linux-x64/acquisition-lock.json")
    require(A.digest(acquisition_data) == PIN["acquisition"], "Acquisition lock pin mismatch")
    acquisition = A.strict_json(acquisition_data)
    runtime = sorted([{"path": r["destination"], "mode": r["mode"], "size": r["size"],
                       "sha256": r["sha256"]} for r in acquisition["files"]], key=lambda r: r["path"])
    B.C.validate_file_inventory(runtime, limits=B.MaterialsLimits())
    require(acquisition["platform"] == "linux-x64"
            and acquisition["inventory_sha256"] == PIN["runtime_inventory"]
            and A.digest(A.canonical(runtime)) == PIN["runtime_inventory"]
            and len(runtime) == PIN["runtime_count"], "Runtime inventory mismatch")
    projects = [c for c in materials_map["components"] if c["kind"] == "project_package"]
    require(len(projects) == 1 and len(materials_map["components"]) == PIN["component_count"] + 1
            and len(materials_map["unresolved_issues"]) == PIN["issue_count"],
            "Unexpected seed declarations")
    prep = next((r for r in materials if r["path"] ==
                 "sources/preparation/candidate-input-preparation.zip"), None)
    require(prep is not None and prep["sha256"] == PIN["preparation_source"],
            "Historical preparation source mismatch")
    manifest_path = "_backend/" + packaged["bundle_id"] + "/bundle-manifest.json"
    _, manifest = json_member(archive, infos, manifest_path)
    require(manifest["bundle_id"] == packaged["bundle_id"]
            and manifest["platform"] == "linux-x64", "Payload identity mismatch")
    B.C.validate_file_inventory(manifest["files"], limits=B.MaterialsLimits())
    payload_records = {r["path"]: r for r in manifest["files"]}
    require(all(payload_records.get(r["path"]) == r for r in runtime), "Runtime lineage mismatch")
    return packaged, lock, runtime, manifest, manifest_path.replace("bundle-manifest.json", "payload.zip")


def export_zip(path, root, records):
    """Verify filesystem bytes/modes against frozen records before and after writing."""
    A.verify_tree(root, records, B)
    require(all(file_record(root / row["path"], row["path"]) == row for row in records),
            "Source filesystem mode/content divergence")
    reserve_space(path.parent, zip_budget(records))
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for row in records:
            info = zipfile.ZipInfo(row["path"], date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | row["mode"]) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with B.BUILDER._open(root / row["path"]) as source, archive.open(info, "w") as target:
                shutil.copyfileobj(source, target, length=1024**2)
    path.chmod(0o644)
    return R.verify_project_source(path, records)


def extract_records(archive, infos, records, destination):
    for row in records:
        require(row["path"] in infos, "Missing declared member")
        target = destination / row["path"]
        make_directory(target.parent)
        reserve_space(destination, row["size"] + 4096)
        with target.open("xb") as stream:
            copy_member(archive, infos[row["path"]], row, stream)
        target.chmod(row["mode"])


def current_notice(commit, version, project_zip, preparer_zip, preparer_sha):
    return f"""# Current project source and reconstruction — candidate inputs only

This notice supersedes the current-source locators and reconstruction instructions
in the named historical documents below, without changing their bytes, license
attribution, limitations or original historical scope. It is NOT a review,
compiler approval, native qualification, public release or admission decision.

## Current project-source locators

- Selected source commit: `{commit}`; version `{version}`.
- Complete current project source: `{project_zip}`.
- Current license: `licenses/project/{commit}/LICENSE`.
- Current notices: `licenses/project/{commit}/THIRD_PARTY_NOTICES.md`.
- Separate refresh implementation: `{preparer_zip}`.
- Separate implementation ZIP SHA-256: `{preparer_sha}`.

The refresh implementation is separate from the selected project source; it may
postdate that commit. Independent public-source verification remains the caller's
responsibility, not something this offline preparer establishes.

## Explicitly superseded historical locators

- `licenses/DISTRIBUTION_NOTICE.md`: references to seed `{PIN['source_commit']}`
  as CURRENT or 'this candidate', its old `sources/project/` ZIP, and its older
  reconstruction instructions describe the seed, NOT these refreshed inputs.
  The old project ZIP is omitted here; use the current source locator above.
- `licenses/INTEGRATED_MATERIALS.md` and its referenced
  `licenses/provenance/project-source-freeze.json`: their 'current' source and
  private-history-era locators are historical, NOT the current source identity.
- `licenses/preparation/REPRODUCE_INPUTS.md`: its pinned predecessor commit and
  metadata hashes apply only to that historical candidate, NOT a newly built one.
- Other retained `licenses/provenance/current-*` or `CURRENT_FEATURE_BUILD.txt`
  names remain original historical evidence, not current-code assertions.

All inherited issue objects, compiler-provenance limitations, runtime bindings,
non-project components and their source/notice requirements remain unchanged.
No issue has been automatically resolved or declared nonblocking.

## A. Reproduce this source refresh

Review the separate refresh implementation ZIP and its checker dependencies.
Obtain the exact fixed predecessor seed (size {PIN['size']}, SHA-256
`{PIN['sha256']}`) through an authorized transfer; no public seed URL is verified.
Use an independently verified public checkout for `{commit}`, then follow the
embedded `docs/LINUX_PREVIEW_INPUT_REFRESH.md` with a fresh output directory.
This route reproduces the refresh and DOES require the predecessor seed.

## B. Reconstruct inputs from a future built refreshed candidate

No refreshed full candidate has been built or qualified by this preparation.
Once such a candidate exists and its actual archive/metadata identities have
been independently verified, reconstruction need NOT require the predecessor
seed or private history. Use the unchanged generic `reconstruct_inputs.py` from
`sources/preparation/candidate-input-preparation.zip`, a verified public checkout
of `{commit}`, the verified extracted NEW candidate, and its exact external
runtime files plus runtime inventory. To obtain those external runtime bytes
without the predecessor seed, follow the selected public checkout's
`docs/RUNTIME_ACQUISITION.md` with its exact
`release_inputs/linux-x64/acquisition-lock.json`; that separate acquisition step
uses the existing checksum-locked public origins, not a guessed seed URL.
Review the retained helper before execution. It uses same-filesystem hardlinks
only: preserve the extracted candidate/runtime and linked reconstructed outputs
unchanged. Cross-filesystem or link denial fails without a copy fallback. These
are the existing helper's constraints, not a hardlink mode in this preparer and
not release-admission evidence.
Invoke the helper with:

    --source-repo PUBLIC_CHECKOUT --source-commit {commit}
    --candidate-root VERIFIED_NEW_CANDIDATE --runtime-root VERIFIED_EXTERNAL_RUNTIME
    --runtime-inventory VERIFIED_RUNTIME_INVENTORY_JSON
    --packaged-materials-sha256 ACTUAL_VERIFIED_NEW_PACKAGED_MATERIALS_SHA256
    --output NEW_DIRECTORY

The generic helper deliberately requires SAME-source candidate reconstruction;
it is not a source-refresh tool. Supply the NEW candidate's verified
PACKAGED_MATERIALS.json hash, never the seed's hash copied from historical
REPRODUCE_INPUTS.md. No future archive URL, metadata hash, qualification result
or trusted review ledger is fabricated here. Substantive materials review and
exact installed/native qualification remain separate mandatory work.
""".encode("utf-8")


def implementation_snapshot(destination):
    records = [file_record(ROOT / name, name) for name in sorted(IMPLEMENTATION_FILES)]
    identity = A.digest(A.canonical(records))
    # Include exact local checker dependencies, not unavailable private history.
    # This is NOT claimed to be present in the selected public project's source ZIP.
    root = destination / "preparer-source"
    make_directory(root)
    for row in records:
        path = root / row["path"]
        make_directory(path.parent)
        write_new(path, (ROOT / row["path"]).read_bytes())
        path.chmod(row["mode"])
    commit = None
    try:
        candidate = A.git(ROOT, "rev-parse", "HEAD")
        modes = {row.split(b"\t", 1)[1].decode(): row.split()[0]
                 for row in subprocess.check_output(
                     ["git", "-C", str(ROOT), "ls-tree", "-rz", candidate],
                     stderr=subprocess.DEVNULL, timeout=120, env=A.git_environment()).split(b"\0")[:-1]}
        if all(modes.get(row["path"]) == (b"100755" if row["mode"] == 0o755 else b"100644")
               and A.digest(subprocess.check_output(
            ["git", "-C", str(ROOT), "show", candidate + ":" + row["path"]],
            stderr=subprocess.DEVNULL, timeout=120, env=A.git_environment())) == row["sha256"]
               for row in records):
            commit = candidate
    except subprocess.CalledProcessError:
        pass  # Exact embedded file identities remain available without a Git checkout.
    return root, records, identity, commit


def prepare(args):
    require(sys.platform == "linux" and os.name == "posix", "Linux builder host required")
    try:
        subprocess.run(["git", "--no-lazy-fetch", "version"], check=True, capture_output=True,
                       timeout=30, env=A.git_environment())
    except subprocess.CalledProcessError as error:
        raise RefreshError("Git with --no-lazy-fetch support is required") from error
    repo, seed = A.checked_path(args.source_repo), A.checked_path(args.seed)
    output = Path(os.path.abspath(args.output))
    A.checked_path(output.parent)
    require(not os.path.lexists(output), "Fresh output directory required; no retry/overwrite")
    require(not (output == repo or repo in output.parents), "Output must be outside source repository")
    require(re.fullmatch(r"[0-9a-f]{40}", args.source_commit) is not None
            and args.source_commit != PIN["source_commit"], "Expected a NEW exact source commit")
    require(A.git(repo, "remote", "get-url", "origin") == PUBLIC_URL, "Expected public source origin")
    require(A.git(repo, "rev-parse", "--verify", args.source_commit + "^{commit}") == args.source_commit,
            "Source commit mismatch")
    subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", args.source_commit,
                    "refs/remotes/origin/main"], check=True, capture_output=True, timeout=120,
                   env=A.git_environment())
    subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor",
                    PIN["source_commit"], args.source_commit], check=True,
                   capture_output=True, timeout=120, env=A.git_environment())
    version = A.validation_identity(SimpleNamespace(candidate_only=True, source_repo=repo,
                                  source_commit=args.source_commit, tag="v" + args.version))
    source_sizes = subprocess.check_output(
        ["git", "-C", str(repo), "ls-tree", "-rlz", "--full-tree", args.source_commit],
        timeout=120, env=A.git_environment()).split(b"\0")[:-1]
    require(0 < len(source_sizes) <= A.MAX_FILES, "Source count exceeds bound")
    block = max(4096, os.statvfs(output.parent).f_frsize)
    source_bytes, source_allocation, directories = 0, 0, set()
    for row in source_sizes:
        header, name = row.split(b"\t", 1)
        mode, kind, _, size = header.split()
        require(mode in {b"100644", b"100755"} and kind == b"blob",
                "Source must contain only regular blobs")
        parts = A.source_path_parts(name.decode("utf-8"))
        size = int(size)
        source_bytes += size
        source_allocation += ((size + block - 1) // block) * block
        directories.update("/".join(parts[:i]) for i in range(1, len(parts)))
    source_allocation += len(directories) * block
    require(source_bytes <= A.MAX_SOURCE, "Source byte budget exceeded")
    with B.BUILDER._open(seed) as raw:
        require(os.fstat(raw.fileno()).st_size == PIN["size"]
                and hashlib.file_digest(raw, "sha256").hexdigest() == PIN["sha256"],
                "Exact seed size/SHA256 mismatch")
        with checked_archive(raw) as (archive, infos):
            packaged, lock, runtime, manifest, payload_path = seed_metadata(archive, infos)
            old_map = packaged["materials_map"]
            materials = packaged["materials_inventory"]
            excluded = [r for r in materials if r["path"].startswith("sources/project/")]
            require(len(excluded) == 1, "Expected one historical current-project source archive")
            retained = [r for r in materials if r not in excluded]
            require(payload_path in infos, "Missing runtime payload")
            # Full seed + bounded directory checks precede any output creation. Capacity
            # accounts for exact runtime/material sizes, temporary payload, two source
            # copies (export + ZIP upper bound), and 32 MiB metadata/directory overhead.
            budget = (sum(r["size"] for r in runtime + retained) + infos[payload_path].file_size
                      + source_allocation + source_bytes + (source_bytes // 16384 + len(source_sizes)) * 8
                      + len(source_sizes) * 2048 + 32 * 1024**2)
            reserve_space(output.parent, budget)
            output.mkdir(mode=0o700)
            try:
                source = output / "source"
                make_directory(source)
                source_files = A.export_source(repo, args.source_commit, source)
                A.version_check(source, version)
                inputs = output / "inputs"
                for sub in ("runtime", "materials", "metadata"):
                    make_directory(inputs / sub)
                mats, meta = inputs / "materials", inputs / "metadata"
                # Hash all materials, including the excluded old source ZIP. No claim
                # that its code or documentary compiler claims have been reviewed.
                for row in excluded:
                    copy_member(archive, infos[row["path"]], row)
                extract_records(archive, infos, retained, mats)
                with tempfile.TemporaryFile(dir=output) as payload:
                    info = infos[payload_path]
                    with archive.open(info) as stream:
                        while chunk := stream.read(min(1024**2, info.file_size - payload.tell() + 1)):
                            require(payload.tell() + len(chunk) <= info.file_size,
                                    "Payload exceeds declared size")
                            reserve_space(output, len(chunk))
                            payload.write(chunk)
                    require(payload.tell() == info.file_size, "Payload length mismatch")
                    with checked_archive(payload) as (inner, inner_infos):
                        require(set(inner_infos) == {r["path"] for r in manifest["files"]},
                                "Payload inventory coverage mismatch")
                        extract_records(inner, inner_infos, runtime, inputs / "runtime")
                project_zip = f"sources/project/mechanical-cad-{args.source_commit}.zip"
                make_directory((mats / project_zip).parent)
                source_zip_sha = export_zip(mats / project_zip, source, source_files)
                impl_root, impl_files, impl_identity, impl_commit = implementation_snapshot(output)
                preparer_zip = f"sources/preparation/linux-preview-source-refresh-{impl_identity}.zip"
                make_directory((mats / preparer_zip).parent)
                preparer_zip_sha = export_zip(mats / preparer_zip, impl_root, impl_files)
                notices = []
                for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
                    relative = f"licenses/project/{args.source_commit}/{name}"
                    make_directory((mats / relative).parent)
                    write_new(mats / relative, (source / name).read_bytes())
                    notices.append(relative)
                recipient_notice = f"licenses/project/{args.source_commit}/CURRENT_SOURCE_AND_RECONSTRUCTION.md"
                write_new(mats / recipient_notice, current_notice(
                    args.source_commit, version, project_zip, preparer_zip, preparer_zip_sha))
                notices.append(recipient_notice)
                provenance = f"licenses/provenance/linux-preview-refresh-{args.source_commit}.json"
                evidence = {
                    "schema_version": 1, "status": STATUS, "source_commit": args.source_commit,
                    "version": version, "seed_sha256": PIN["sha256"], "seed_bytes": PIN["size"],
                    "seed_source_commit": PIN["source_commit"],
                    "seed_packaged_materials_sha256": PIN["packaged"],
                    "acquisition_lock_sha256": PIN["acquisition"],
                    "source_inventory_sha256": A.digest(A.canonical(source_files)),
                    "project_source_zip_sha256": source_zip_sha,
                    "excluded_historical_project_archives": excluded,
                    "retained_material_count": len(retained),
                    "implementation_git_commit": impl_commit,
                    "implementation_source_path": preparer_zip,
                    "implementation_source_sha256": preparer_zip_sha,
                    "implementation_source_inventory_sha256": impl_identity,
                    "implementation_is_separate_from_target_source": True,
                    "public_source_verification": "CALLER_VERIFICATION_REQUIRED_NOT_ESTABLISHED_BY_THIS_TOOL",
                    "current_recipient_notice": recipient_notice,
                    "local_origin_main": A.git(repo, "rev-parse", "refs/remotes/origin/main"),
                    "historical_evidence": "Retained unchanged, not current source or compiler approval.",
                    "review": "NOT_PERFORMED_NO_TRUSTED_REVIEW_LEDGER",
                    "native_qualification": "NOT_RUN", "release_admission": "NOT_ESTABLISHED",
                    **preserved_identity(old_map),
                }
                make_directory((mats / provenance).parent)
                write_new(mats / provenance, A.canonical(evidence))
                updated = copy.deepcopy(old_map)
                project = next(c for c in updated["components"] if c["kind"] == "project_package")
                project["source_paths"] = sorted([p for p in project["source_paths"]
                    if p not in {r["path"] for r in excluded}] + [project_zip, preparer_zip])
                project["notice_paths"] = sorted(project["notice_paths"] + notices)
                project["provenance_paths"] = sorted(project["provenance_paths"] + [provenance, recipient_notice])
                project["declared_identity"] = (
                    f"Mechanical CAD exact public Git source {args.source_commit}; version {version}; "
                    "candidate inputs only. Separate refresh preparer source included. "
                    "Historical provenance, external runtime and unresolved issues retained unchanged.")
                mat_files = sorted([file_record(p, p.relative_to(mats).as_posix())
                                    for p in mats.rglob("*") if p.is_file()], key=lambda r: r["path"])
                updated.update(source_commit=args.source_commit,
                               source_inventory_sha256=evidence["source_inventory_sha256"],
                               materials_inventory_sha256=A.digest(A.canonical(mat_files)))
                require(preserved_identity(updated) == preserved_identity(old_map),
                        "Historical declarations changed")
                B._parse_map(A.canonical(updated), source_commit=args.source_commit,
                    platform="linux-x64", runtime_lock=lock,
                    source=B.C.validate_file_inventory(source_files, limits=B.MaterialsLimits()),
                    runtime=B.C.validate_file_inventory(runtime, limits=B.MaterialsLimits()),
                    materials=B.C.validate_file_inventory(mat_files, limits=B.MaterialsLimits()),
                    limits=B.MaterialsLimits())
                for name, data in (("runtime-lock.json", lock),
                                   ("runtime-inventory.json", A.canonical(runtime)),
                                   ("materials-inventory.json", A.canonical(mat_files)),
                                   ("materials-map.json", A.canonical(updated))):
                    write_new(meta / name, data)
                A.verify_tree(inputs / "runtime", runtime, B)
                A.verify_tree(mats, mat_files, B)
                A.verify_tree(source, source_files, B)
                raw.seek(0)
                require(hashlib.file_digest(raw, "sha256").hexdigest() == PIN["sha256"],
                        "Seed changed during preparation")
                result = dict(evidence, runtime_lock_sha256=PIN["runtime_lock"],
                    runtime_inventory_sha256=PIN["runtime_inventory"], runtime_files=len(runtime),
                    materials_files=len(mat_files),
                    materials_inventory_sha256=updated["materials_inventory_sha256"],
                    materials_map_sha256=A.digest(A.canonical(updated)),
                    issues_retained=len(updated["unresolved_issues"]),
                    nonproject_components_retained=PIN["component_count"])
                reserve_space(output, len(A.canonical(result)))
                write_new(output / "preparation-receipt.json", A.canonical(result))
                return result
            except Exception as error:
                # Keep partial bytes for diagnosis, never retry, delete or overwrite.
                diagnostic = A.canonical({"status": "PREPARATION_FAILED_NOT_READY",
                                          "error_type": type(error).__name__})
                if shutil.disk_usage(output).free >= RESERVE + allocation_bytes(output, len(diagnostic) + 4096):
                    try:
                        write_new(output / "PREPARATION_FAILED.json", diagnostic)
                    except (OSError, RefreshError):
                        pass  # Diagnostic failure must not replace the original failure.
                raise


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in ("seed", "source-repo", "source-commit", "version", "output"):
        result.add_argument("--" + name, required=True)
    return result


def main():
    try:
        print(A.canonical(prepare(parser().parse_args())).decode(), end="")
    except Exception as error:
        reason = str(error) if isinstance(error, RefreshError) else type(error).__name__
        print(f"Linux preview input preparation failed: {reason}; "
              "no review, qualification or release claimed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
