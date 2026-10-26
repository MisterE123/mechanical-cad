"""Normalize only the pinned official Linux Blender 5.2.2 TAR to regular files.

Source/materials archive policy is unchanged. No filesystem link is created.
Archive authentication and the entire link/path/budget plan precede output writes.
"""

from __future__ import annotations

import hashlib
import stat
import tarfile
from pathlib import Path, PurePosixPath

import build_release_candidate as A

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "blender-5.2.2-linux-x64"
ARCHIVE_SHA256 = "84098912789dc450e95697c4184fb8a90acbe5111c2ba4aede3fecb57806a168"
ARCHIVE_BYTES = 383295504
ARCHIVE_URL = "https://download.blender.org/release/Blender5.2/blender-5.2.2-linux-x64.tar.xz"
LINKS_SHA256 = "9dac0e5f05e3a6f1cb2ebc812f5112c2d114c04d92581d86b5f22b392afb3cc7"
MAX_FILES = 100_000
MAX_TOTAL = 8_000_000_000
MAX_MEMBER = 2_000_000_000
MAX_DEPTH = 16


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identity(path):
    A.checked_path(path)
    info = Path(path).lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "Expected single-link regular file")
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest(), info.st_size


def reviewed_links():
    raw = A.read_metadata(ROOT / "release_inputs/blender-5.2.2-linux-x64-links.json")
    require(A.digest(raw) == LINKS_SHA256, "Unreviewed Blender link manifest")
    value = A.strict_json(raw)
    require(
        set(value) == {"schema_version", "archive_sha256", "archive_bytes", "links"}
        and type(value["schema_version"]) is int
        and value["schema_version"] == 1
        and value["archive_sha256"] == ARCHIVE_SHA256
        and value["archive_bytes"] == ARCHIVE_BYTES,
        "Blender link manifest identity mismatch",
    )
    return value["links"]


def plan(
    members,
    links,
    *,
    max_files=MAX_FILES,
    max_total=MAX_TOTAL,
    max_member=MAX_MEMBER,
    max_depth=MAX_DEPTH,
):
    """Pure bounded planner; tests may lower ceilings, never broaden production policy."""
    for value, ceiling in (
        (max_files, MAX_FILES),
        (max_total, MAX_TOTAL),
        (max_member, MAX_MEMBER),
        (max_depth, MAX_DEPTH),
    ):
        require(type(value) is int and 0 < value <= ceiling, "Invalid/rebounded archive budget")
    entries, folded, observed_links, spellings = {}, set(), {}, {}
    for item in members:
        require(len(entries) < max_files, "Blender member count exceeds budget")
        name = item.name.rstrip("/") if item.isdir() else item.name
        require("\\" not in name, "Nonportable Blender member separator")
        parts = A.source_path_parts(name)
        require(parts[0] == PREFIX, "Member outside pinned Blender root")
        for depth in range(1, len(parts) + 1):
            spelling = "/".join(parts[:depth])
            require(
                spellings.setdefault(spelling.casefold(), spelling) == spelling,
                "Case-ambiguous Blender path component",
            )
        require(name not in entries and name.casefold() not in folded, "Duplicate Blender member")
        require(
            item.sparse is None and not any(k.startswith("GNU.sparse") for k in item.pax_headers),
            "Sparse Blender member",
        )
        require(item.isdir() or item.isfile() or item.issym(), "Unsupported Blender member type")
        require(
            type(item.size) is int and 0 <= item.size <= max_member, "Blender member size budget"
        )
        if not item.isfile():
            require(item.size == 0, "Nonregular Blender member payload")
        if item.issym():
            require(
                PurePosixPath(name).parent.as_posix() == PREFIX + "/lib",
                "Blender alias outside reviewed library directory",
            )
            target = A.source_path_parts(item.linkname)
            require(
                len(target) == 1 and "\\" not in item.linkname,
                "Blender alias target must be a relative basename",
            )
            require(links.get(name) == item.linkname, "Unreviewed Blender alias")
            observed_links[name] = item.linkname
        entries[name] = item
        folded.add(name.casefold())
    require(observed_links == links, "Missing or additional reviewed Blender aliases")
    for name in entries:
        for parent in PurePosixPath(name).parents:
            if parent.as_posix() in entries:
                require(entries[parent.as_posix()].isdir(), "Blender file/link used as parent")
            # Implicit parent spelling must not alias an explicit different-case entry.
            if parent.as_posix().casefold() in folded:
                require(parent.as_posix() in entries, "Case-ambiguous Blender parent")
    resolved = {}
    for name, item in entries.items():
        if item.isdir():
            continue
        seen, target = set(), name
        while entries[target].issym():
            require(
                target not in seen and len(seen) < max_depth, "Blender alias cycle/depth budget"
            )
            seen.add(target)
            target = (PurePosixPath(target).parent / entries[target].linkname).as_posix()
            require(target in entries, "Blender alias target is not a reviewed member")
        require(entries[target].isfile(), "Blender alias target is not a regular file")
        resolved[name] = target
    require(
        sum(entries[target].size for target in resolved.values()) <= max_total,
        "Normalized Blender expansion exceeds budget",
    )
    return entries, resolved


def _copy(source, destination, size, expected=None):
    digest, total = hashlib.sha256(), 0
    with destination.open("xb") as output:
        while chunk := source.read(min(1024 * 1024, size - total + 1)):
            total += len(chunk)
            require(total <= size, "Blender member grew during copy")
            digest.update(chunk)
            output.write(chunk)
    require(
        total == size and (expected is None or digest.hexdigest() == expected),
        "Blender member copy identity mismatch",
    )
    return digest.hexdigest()


def normalize(bundle, entries, resolved, destination):
    """Execute a fully validated plan into a fresh private directory, using files only."""
    A.checked_path(destination.parent)
    destination.mkdir(exist_ok=False)
    identities = {}
    # Read regular members in archive order. Avoid repeated backward XZ seeks.
    for name, item in entries.items():
        target = destination / name
        if item.isdir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.isfile():
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(item) as stream:
                sha = _copy(stream, target, item.size)
            target.chmod(0o755 if item.mode & 0o111 else 0o644)
            identities[name] = sha
    aliases = []
    for name, original in resolved.items():
        if name == original:
            continue
        source, target = destination / original, destination / name
        require(
            identity(source) == (identities[original], entries[original].size),
            "Normalized Blender target changed",
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as stream:
            sha = _copy(stream, target, entries[original].size, identities[original])
        target.chmod(0o755 if entries[original].mode & 0o111 else 0o644)
        aliases.append(
            {
                "path": name,
                "regular_source": original,
                "sha256": sha,
                "bytes": entries[original].size,
            }
        )
    return aliases


def extract(archive, destination, record):
    """Only this authenticated official archive may use alias normalization."""
    require(
        record == {"url": ARCHIVE_URL, "sha256": ARCHIVE_SHA256, "bytes": ARCHIVE_BYTES},
        "Only pinned official Blender 5.2.2 Linux archive is admitted",
    )
    require(
        identity(archive) == (ARCHIVE_SHA256, ARCHIVE_BYTES), "Blender archive identity mismatch"
    )
    links = reviewed_links()
    with tarfile.open(archive, "r:xz") as bundle:
        entries, resolved = plan(bundle, links)
        aliases = normalize(bundle, entries, resolved, Path(destination))
    require(identity(archive) == (ARCHIVE_SHA256, ARCHIVE_BYTES), "Blender archive changed")
    return {
        "archive_sha256": ARCHIVE_SHA256,
        "archive_bytes": ARCHIVE_BYTES,
        "members": len(entries),
        "regular_outputs": len(resolved),
        "normalized_aliases": aliases,
        "native_execution": False,
    }
