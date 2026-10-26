"""Offline, tag-bound candidate builder. Does not qualify or publish a release.

All materials and dependency inputs must already be audited and inventoried.
No downloads, input-map rewriting, private-history export or runtime execution.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import unicodedata
from pathlib import Path

STATUS = "UNQUALIFIED_CONTRACT_ARTIFACT"
METADATA = frozenset({
    "runtime-inventory.json", "materials-inventory.json", "runtime-lock.json", "materials-map.json",
})
MAX_METADATA = 16 * 1024 * 1024
MAX_SOURCE = 512 * 1024 * 1024
MAX_FILES = 50_000


class CandidateError(ValueError):
    """Fail-closed candidate input or output error."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def checked_path(value):
    path = Path(os.path.abspath(value))
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise CandidateError("Symlink/reparse input or output ancestry is unsupported")
    return path


def strict_json(data):
    if not 0 < len(data) <= MAX_METADATA:
        raise CandidateError("Metadata size exceeds limit")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CandidateError("Duplicate metadata key")
            result[key] = value
        return result

    def constant(_value):
        raise CandidateError("Nonfinite JSON constant")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def read_metadata(path):
    checked_path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags | getattr(os, "O_BINARY", 0))
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise CandidateError("Metadata must be a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(MAX_METADATA + 1)
    finally:
        os.close(descriptor)
    strict_json(data)
    return data


def git_environment():
    return dict(os.environ, GIT_NO_REPLACE_OBJECTS="1")


def git(repo, *args):
    # Arguments are separate, shell-free, and revisions are validated before use.
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], stderr=subprocess.PIPE, timeout=120, env=git_environment()
    ).decode().strip()


def source_identity(repo, commit, tag, main_ref):
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise CandidateError("Source commit must be a full lowercase SHA-1")
    if re.fullmatch(r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", tag) is None:
        raise CandidateError("Expected a plain vMAJOR.MINOR.PATCH tag")
    if main_ref not in {"refs/heads/main", "refs/remotes/origin/main"}:
        raise CandidateError("Main ref must name main or origin/main")
    if git(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}") != commit:
        raise CandidateError("Tag differs from requested source commit")
    subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, main_ref],
        check=True, capture_output=True, timeout=120, env=git_environment(),
    )
    return tag[1:]


def validation_identity(args):
    """Explicit candidate path never fabricates main or creates a version tag."""
    if not getattr(args, "candidate_only", False):
        return source_identity(args.source_repo, args.source_commit, args.tag, args.main_ref)
    if re.fullmatch(r"[0-9a-f]{40}", args.source_commit) is None:
        raise CandidateError("Candidate must name a full exact commit")
    if git(args.source_repo, "rev-parse", "--verify", args.source_commit + "^{commit}") != args.source_commit:
        raise CandidateError("Candidate commit identity mismatch")
    metadata = strict_json(canonical(tomllib.loads(git(
        args.source_repo, "show", args.source_commit + ":pyproject.toml"))))
    version = metadata["project"]["version"]
    if re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version) is None:
        raise CandidateError("Candidate requires a plain project version")
    if args.tag != "v" + version:
        raise CandidateError("Candidate version label mismatch")
    return version


def source_path_parts(name):
    """Validate portable spelling BEFORE any export filesystem operation."""
    if not name or unicodedata.normalize("NFC", name) != name:
        raise CandidateError("Invalid source path normalization")
    parts = name.split("/")
    if len(name.encode("utf-8")) > 240 or len(parts) > 16:
        raise CandidateError("Source path exceeds portable bounds")
    for part in parts:
        if not part or part in {".", ".."} or part.casefold() == ".git" or part.endswith((".", " ")):
            raise CandidateError("Invalid source path component")
        if any(unicodedata.category(c).startswith("C") or c in '\\:<>"|?*' for c in part):
            raise CandidateError("Unsafe source path character")
        stem = part.split(".", 1)[0].rstrip(" ").upper()
        if stem in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", stem):
            raise CandidateError("Reserved Windows source path")
    return parts


def export_source(repo, commit, root):
    """Export exact Git blobs/modes, independent of working tree and Git attributes."""
    listing = subprocess.check_output(
        ["git", "-C", str(repo), "ls-tree", "-rz", "--full-tree", commit], timeout=120, env=git_environment()
    )
    records = listing.split(b"\0")[:-1]
    if not 0 < len(records) <= MAX_FILES:
        raise CandidateError("Source file count exceeds limit")
    plan, spellings, prefixes = [], set(), {}
    for entry in records:
        header, raw_name = entry.split(b"\t", 1)
        mode, kind, oid = header.split()
        if kind != b"blob" or mode not in {b"100644", b"100755"}:
            raise CandidateError("Source symlinks/submodules/special modes are unsupported")
        name = raw_name.decode("utf-8", errors="strict")
        parts = source_path_parts(name)
        if name.casefold() in spellings:
            raise CandidateError("Case-colliding source paths are unsupported")
        spellings.add(name.casefold())
        for length in range(1, len(parts) + 1):
            prefix = "/".join(parts[:length])
            if prefixes.setdefault(prefix.casefold(), prefix) != prefix:
                raise CandidateError("Case-colliding source directory spellings are unsupported")
        plan.append((mode, oid, name, parts))
    files, total = [], 0
    # cat-file batch avoids Git archive export-ignore/export-subst transformations.
    with subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=git_environment(),
    ) as child:
        try:
            for mode, oid, name, parts in plan:
                target = root.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                child.stdin.write(oid + b"\n")
                child.stdin.flush()
                returned, blob_kind, size_raw = child.stdout.readline(256).split()
                size = int(size_raw)
                total += size
                if returned != oid or blob_kind != b"blob" or size < 0 or total > MAX_SOURCE:
                    raise CandidateError("Invalid or oversized source blob")
                sha, remaining = hashlib.sha256(), size
                with target.open("xb") as out:
                    while remaining:
                        data = child.stdout.read(min(1024 * 1024, remaining))
                        if not data:
                            raise CandidateError("Truncated Git blob")
                        sha.update(data)
                        out.write(data)
                        remaining -= len(data)
                if child.stdout.read(1) != b"\n":
                    raise CandidateError("Invalid Git batch boundary")
                bits = 0o755 if mode == b"100755" else 0o644
                target.chmod(bits)
                files.append({"path": name, "size": size, "sha256": sha.hexdigest(), "mode": bits})
            child.stdin.close()
            if child.wait(timeout=120) != 0:
                raise CandidateError("Git blob export failed")
        except BaseException:
            child.kill()
            child.wait()
            raise
    return sorted(files, key=lambda item: item["path"])


def version_check(root, expected):
    metadata = tomllib.loads((root / "pyproject.toml").read_text())
    tree = ast.parse((root / "src/mechanical_cad/__init__.py").read_text())
    versions = [ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)]
    if metadata["project"]["version"] != expected or versions != [expected]:
        raise CandidateError("Tag, project and core versions must agree")


def load_builder(source):
    path = source / "scripts/package_standalone_materials.py"
    spec = importlib.util.spec_from_file_location("_release_candidate_materials", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    prior_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = prior_bytecode
    if module.STATUS != STATUS:
        raise CandidateError("Unexpected contract builder status")
    return module


def verify_tree(root, records, builder):
    inventory = builder.C.validate_file_inventory(records, limits=builder.MaterialsLimits())
    if builder.BUILDER._tree_files(root, builder.MaterialsLimits()) != {i.path for i in inventory}:
        raise CandidateError("Input tree differs from declared inventory")
    for item in inventory:
        builder._verify_file(root / item.path, item, builder.MaterialsLimits())


def build(args):
    repo, inputs = checked_path(args.source_repo), checked_path(args.inputs_root)
    output, receipt = Path(os.path.abspath(args.output)), Path(os.path.abspath(args.receipt))
    if output == receipt or output.suffix != ".zip" or receipt.suffix != ".json":
        raise CandidateError("Expected distinct .zip candidate and .json receipt")
    for path in (output, receipt):
        checked_path(path.parent)
        if os.path.lexists(path):
            raise CandidateError("Output/receipt already exists; no overwrite or retry")
        if any(path == root or root in path.parents for root in (repo, inputs)):
            raise CandidateError("Outputs must be outside source and input trees")
    version = validation_identity(args)
    if args.platform not in {"linux-x64", "windows-x64"}:
        raise CandidateError("Unsupported platform")
    if {p.name for p in inputs.iterdir()} != {"runtime", "materials", "metadata"}:
        raise CandidateError("Input root must contain only runtime/materials/metadata")
    for name in ("runtime", "materials", "metadata"):
        checked_path(inputs / name)
    metadata = inputs / "metadata"
    if {p.name for p in metadata.iterdir()} != METADATA:
        raise CandidateError("Unexpected/missing input metadata")
    values = {name: read_metadata(metadata / name) for name in METADATA}
    for name, expected in (("runtime-lock.json", args.runtime_lock_sha256),
                           ("materials-map.json", args.materials_map_sha256)):
        if re.fullmatch(r"[0-9a-f]{64}", expected) is None or digest(values[name]) != expected:
            raise CandidateError("Audited input metadata hash mismatch")
    with tempfile.TemporaryDirectory(prefix="candidate-source-", dir=output.parent) as directory:
        source = Path(directory)
        source_files = export_source(repo, args.source_commit, source)
        version_check(source, version)
        builder = load_builder(source)
        runtime_files = strict_json(values["runtime-inventory.json"])
        materials_files = strict_json(values["materials-inventory.json"])
        verify_tree(inputs / "runtime", runtime_files, builder)
        verify_tree(inputs / "materials", materials_files, builder)
        materials_map = strict_json(values["materials-map.json"])
        # Deliberately DO NOT rewrite declarations to make stale inputs appear current.
        builder._parse_map(
            values["materials-map.json"], source_commit=args.source_commit,
            platform=args.platform, runtime_lock=values["runtime-lock.json"],
            source=builder.C.validate_file_inventory(source_files, limits=builder.MaterialsLimits()),
            runtime=builder.C.validate_file_inventory(runtime_files, limits=builder.MaterialsLimits()),
            materials=builder.C.validate_file_inventory(materials_files, limits=builder.MaterialsLimits()),
            limits=builder.MaterialsLimits(),
        )
        # Reserve receipt before irreversible candidate publication; failures retain a
        # bounded diagnostic. Do not rerun blindly if either destination now exists.
        with receipt.open("xb") as receipt_stream:
            try:
                built = builder.build_materials_extension(
                    source_root=source, source_commit=args.source_commit, source_files=source_files,
                    runtime_root=inputs / "runtime", runtime_files=runtime_files,
                    runtime_lock=values["runtime-lock.json"], platform=args.platform,
                    python_path=builder.BUILDER.PYTHON_PATHS[args.platform], destination=output,
                    materials_root=inputs / "materials", materials_files=materials_files,
                    materials_map=values["materials-map.json"],
                )
                with output.open("rb") as stream:
                    actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
                if (built.get("status") != STATUS or built.get("published") is not True
                        or built.get("receipt_phase") != "after_publication"
                        or built.get("sha256") != actual_hash or built.get("bytes") != output.stat().st_size):
                    raise CandidateError("Candidate publication/receipt unconfirmed; inspect, do not retry")
                validation_identity(args)
                result = {
                    "schema_version": 1, "status": STATUS, "qualification": "NOT_RUN",
                    "source_commit": args.source_commit, "tag": args.tag, "version": version,
                    "platform": args.platform, "archive": output.name,
                    "bytes": output.stat().st_size, "sha256": actual_hash,
                    "runtime_lock_sha256": digest(values["runtime-lock.json"]),
                    "materials_map_sha256": digest(values["materials-map.json"]),
                    "source_inventory_sha256": digest(canonical(source_files)),
                    "runtime_inventory_sha256": builder._inventory_digest(
                        builder.C.validate_file_inventory(runtime_files, limits=builder.MaterialsLimits())),
                    "materials_inventory_sha256": builder._inventory_digest(
                        builder.C.validate_file_inventory(materials_files, limits=builder.MaterialsLimits())),
                    "unresolved_material_issue_ids": sorted(i["id"] for i in materials_map["unresolved_issues"]),
                }
                if getattr(args, "candidate_only", False):
                    result["candidate_validation_only"] = True
            except Exception as error:
                receipt_stream.write(canonical({"schema_version": 1, "status": "BUILD_UNCONFIRMED",
                    "error_type": type(error).__name__, "candidate_exists": os.path.lexists(output)}))
                raise
            receipt_stream.write(canonical(result))
            receipt_stream.flush()
            os.fsync(receipt_stream.fileno())
    return result


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in ("source-repo", "source-commit", "tag", "inputs-root", "platform", "output",
                 "receipt", "runtime-lock-sha256", "materials-map-sha256"):
        result.add_argument("--" + name, required=True)
    result.add_argument("--main-ref", default="refs/remotes/origin/main",
                        choices=("refs/heads/main", "refs/remotes/origin/main"))
    result.add_argument("--candidate-only", action="store_true",
                        help="Nonpublishing exact-commit validation; no main/tag admission")
    return result


def main():
    try:
        print(canonical(build(parser().parse_args())).decode(), end="")
    except Exception as error:
        # Avoid leaking local paths, subprocess stderr or private materials content.
        print(f"Candidate build failed ({type(error).__name__}); no qualification claimed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
