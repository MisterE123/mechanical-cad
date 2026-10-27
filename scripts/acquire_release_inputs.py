"""Data-only, checksum-locked runtime acquisition. Not release admission."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

MAX_JSON = 4_000_000
MAX_ARCHIVE = 150_000_000
MAX_EXPANDED = 1_000_000_000
MAX_MEMBER = 200_000_000
MAX_ENTRIES = 20000
HOSTS = {
    "www.python.org",
    "files.pythonhosted.org",
    "github.com",
    "release-assets.githubusercontent.com",
    "security.debian.org",
    "deb.debian.org",
}


class AcquisitionError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AcquisitionError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return (
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def read_bounded_bytes(path):
    with open(path, "rb") as stream:
        data = stream.read(MAX_JSON + 1)
    require(len(data) <= MAX_JSON, "oversize JSON")
    return data


def reject_nonfinite(value):
    raise AcquisitionError("nonfinite JSON constant: " + value)


def parse_json(data):
    return json.loads(
        data, object_pairs_hook=no_duplicates, parse_constant=reject_nonfinite
    )


def read_json(path):
    return parse_json(read_bounded_bytes(path))


def safe_path(value, archive=False):
    require(isinstance(value, str) and 0 < len(value) <= 1000, "invalid path")
    if archive and value.startswith("./"):
        value = value[2:]
    value = value.removesuffix("/") if archive else value
    require(
        value and not value.startswith("/") and "\\" not in value,
        "absolute/backslash path",
    )
    require(not any(ord(c) < 32 or ord(c) == 127 for c in value), "control path")
    for part in value.split("/"):
        require(
            part not in ("", ".", "..") and ":" not in part, "traversal/drive/ADS path"
        )
        require(not part.endswith((" ", ".")), "ambiguous Windows path")
        require(
            not re.fullmatch(
                r"(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.IGNORECASE
            ),
            "reserved path",
        )
    return value


def check_paths(names):
    seen = {}
    files = set()
    prefixes = {}
    for name in names:
        path = safe_path(name)
        require(path.casefold() not in seen, "duplicate/case-collision path")
        seen[path.casefold()] = path
        files.add(path.casefold())
        parts = path.split("/")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            previous = prefixes.setdefault(prefix.casefold(), prefix)
            require(previous == prefix, "directory case-collision path")
    for name in files:
        parts = name.split("/")
        require(
            not any("/".join(parts[:i]) in files for i in range(1, len(parts))),
            "file/directory collision",
        )


def validate_lock(lock):
    require(
        set(lock) == {"schema", "platform", "inventory_sha256", "archives", "files"},
        "lock fields",
    )
    require(
        type(lock["schema"]) is int
        and lock["schema"] == 1
        and type(lock["platform"]) is str
        and lock["platform"] in {"linux-x64", "windows-x64"},
        "unsupported lock",
    )
    require(
        isinstance(lock["archives"], list) and 0 < len(lock["archives"]) <= 16,
        "archive count",
    )
    archives = {}
    for a in lock["archives"]:
        require(
            set(a)
            == {
                "filename",
                "url",
                "sha256",
                "size",
                "format",
                "inert_case_alias_prefixes",
            },
            "archive fields",
        )
        name = safe_path(a["filename"])
        require("/" not in name and name not in archives, "archive filename")
        validate_url(a["url"])
        require(re.fullmatch("[0-9a-f]{64}", a["sha256"]) is not None, "archive digest")
        require(type(a["size"]) is int and 0 < a["size"] <= MAX_ARCHIVE, "archive size")
        require(a["format"] in ("zip", "tar", "deb"), "archive format")
        require(isinstance(a["inert_case_alias_prefixes"], list), "inert prefix list")
        for prefix in a["inert_case_alias_prefixes"]:
            safe_path(prefix)
        archives[name] = a
    require(
        isinstance(lock["files"], list) and 0 < len(lock["files"]) <= MAX_ENTRIES,
        "member count",
    )
    member_names = {}
    for row in lock["files"]:
        require(
            set(row) == {"archive", "member", "destination", "mode", "size", "sha256"},
            "member fields",
        )
        require(row["archive"] in archives, "unknown archive")
        member = safe_path(row["member"], archive=True)
        require(
            not any(
                member == p or member.startswith(p + "/")
                for p in archives[row["archive"]]["inert_case_alias_prefixes"]
            ),
            "mapped inert prefix",
        )
        member_names.setdefault(row["archive"], []).append(member)
        safe_path(row["destination"])
        require(
            type(row["size"]) is int and 0 <= row["size"] <= MAX_MEMBER, "member size"
        )
        require(
            type(row["mode"]) is int and row["mode"] in (0o644, 0o755), "member mode"
        )
        require(
            re.fullmatch("[0-9a-f]{64}", row["sha256"]) is not None, "member digest"
        )
    check_paths([r["destination"] for r in lock["files"]])
    for names in member_names.values():
        check_paths(names)
    require(set(member_names) == set(archives), "unused archive")
    inventory = sorted(
        [
            {
                "path": r["destination"],
                "mode": r["mode"],
                "size": r["size"],
                "sha256": r["sha256"],
            }
            for r in lock["files"]
        ],
        key=lambda r: r["path"],
    )
    require(sha(canonical(inventory)) == lock["inventory_sha256"], "inventory binding")
    require(sum(r["size"] for r in lock["files"]) <= MAX_EXPANDED, "output budget")
    return inventory


def validate_url(url):
    p = urllib.parse.urlsplit(url)
    require(
        p.scheme == "https"
        and p.hostname in HOSTS
        and p.username is None
        and p.password is None
        and p.port in (None, 443)
        and not p.fragment,
        "unapproved URL",
    )


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(artifact, cache):
    path = cache / artifact["filename"]
    require(not path.exists() and not path.is_symlink(), "cache target exists")
    opener = urllib.request.build_opener(SafeRedirect)
    total = 0
    digest = hashlib.sha256()
    with (
        opener.open(artifact["url"], timeout=60) as response,
        path.open("xb") as output,
    ):
        validate_url(response.geturl())
        while True:
            chunk = response.read(min(1024 * 1024, artifact["size"] - total + 1))
            if not chunk:
                break
            total += len(chunk)
            require(total <= artifact["size"], "download exceeds locked size")
            digest.update(chunk)
            output.write(chunk)
    require(
        total == artifact["size"] and digest.hexdigest() == artifact["sha256"],
        "download checksum/size mismatch",
    )
    return path


def deb_payload(data):
    require(data.startswith(b"!<arch>\n"), "invalid deb ar")
    pos = 8
    members = {}
    while pos < len(data):
        require(pos + 60 <= len(data), "truncated ar header")
        h = data[pos : pos + 60]
        require(h[58:60] == b"`\n", "ar header magic")
        name = h[:16].decode("ascii").strip().rstrip("/")
        require(
            name
            in (
                "debian-binary",
                "control.tar.gz",
                "control.tar.xz",
                "data.tar.gz",
                "data.tar.xz",
                "data.tar",
            )
            and name not in members,
            "unsupported/duplicate ar member",
        )
        size = int(h[48:58].decode("ascii").strip())
        require(0 <= size <= MAX_ARCHIVE and pos + 60 + size <= len(data), "ar bounds")
        members[name] = data[pos + 60 : pos + 60 + size]
        pos += 60 + size + size % 2
    require(
        pos == len(data) and members.get("debian-binary") == b"2.0\n",
        "deb version/bounds",
    )
    payloads = [v for k, v in members.items() if k.startswith("data.tar")]
    require(len(payloads) == 1, "deb payload count")
    return payloads[0]


def inspect_archive(path, artifact, rows):
    """Verify whole archive hash, names and mapped bytes before creating output files.

    Unselected links are inert metadata (PBS includes normal interpreter aliases).
    Links are NEVER followed/copied; a mapped link fails. All member names checked.
    """
    require(path.is_file() and not path.is_symlink(), "archive is not regular")
    require(path.stat().st_size == artifact["size"], "archive size mismatch")
    data = path.read_bytes()
    require(sha(data) == artifact["sha256"], "archive checksum mismatch")
    iszip = artifact["format"] == "zip"
    with (
        zipfile.ZipFile(io.BytesIO(data))
        if iszip
        else tarfile.open(
            fileobj=io.BytesIO(
                deb_payload(data) if artifact["format"] == "deb" else data
            ),
            mode="r:*",
        )
    ) as archive:
        entries = archive.infolist() if iszip else iter(archive)
        members = {}
        folded = {}
        total = 0
        for index, entry in enumerate(entries):
            require(index < MAX_ENTRIES, "too many archive entries")
            name = entry.filename if iszip else entry.name
            if name in (".", "./") and not iszip and entry.isdir():
                continue
            name = safe_path(name, archive=True)
            require(name not in members, "duplicate archive member")
            if name.casefold() in folded:
                other = folded[name.casefold()]
                prefixes = artifact["inert_case_alias_prefixes"]
                require(
                    any(
                        name.startswith(p + "/") and other.startswith(p + "/")
                        for p in prefixes
                    ),
                    "case-collision archive member",
                )
            folded[name.casefold()] = name
            size = entry.file_size if iszip else entry.size
            require(0 <= size <= MAX_MEMBER, "archive member budget")
            total += size
            require(total <= MAX_EXPANDED, "archive expansion budget")
            members[name] = entry
        nondirectories = {
            name.casefold()
            for name, entry in members.items()
            if not (entry.is_dir() if iszip else entry.isdir())
        }
        for name in folded:
            parts = name.split("/")
            require(
                not any(
                    "/".join(parts[:i]) in nondirectories for i in range(1, len(parts))
                ),
                "archive file/link parent ambiguity",
            )
        output = []
        for row in rows:
            name = safe_path(row["member"], archive=True)
            require(name in members, "missing mapped member")
            entry = members[name]
            if iszip:
                mode = entry.external_attr >> 16
                require(
                    not entry.is_dir()
                    and stat.S_IFMT(mode) in (0, stat.S_IFREG)
                    and not entry.flag_bits & 1,
                    "nonregular/encrypted mapped member",
                )
                stream = archive.open(entry)
            else:
                require(
                    entry.isreg() and not entry.issparse(), "nonregular mapped member"
                )
                stream = archive.extractfile(entry)
            with stream:
                content = stream.read(row["size"] + 1)
            require(
                len(content) == row["size"] and sha(content) == row["sha256"],
                "mapped member checksum/size mismatch",
            )
            output.append((row, content))
        return output


def verify_tree(root, inventory):
    actual = []
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            require(not (Path(base) / name).is_symlink(), "output directory link")
        for name in files:
            path = Path(base) / name
            st = path.lstat()
            require(
                stat.S_ISREG(st.st_mode) and st.st_nlink == 1,
                "output nonregular/multilink",
            )
            actual.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "mode": stat.S_IMODE(st.st_mode),
                    "size": st.st_size,
                    "sha256": sha(path.read_bytes()),
                }
            )
    actual.sort(key=lambda r: r["path"])
    require(actual == inventory, "final inventory mismatch")
    return sha(canonical(actual))


def acquire(lock_path, work_root, download_cache=None):
    lock_bytes = read_bounded_bytes(lock_path)
    lock_digest = sha(lock_bytes)
    lock = parse_json(lock_bytes)
    inventory = validate_lock(lock)  # Before any output mutation or network.
    require(
        sys.platform == "linux" and os.name == "posix",
        "Runtime acquisition requires a Linux builder host.",
    )
    work = Path(work_root).absolute()
    require(not work.exists() and not work.is_symlink(), "work root already exists")
    require(
        work.parent.is_dir() and work.parent.resolve() == work.parent,
        "work parent missing or linked",
    )
    work.mkdir(mode=0o700)
    cache = work / "cache"
    cache.mkdir()
    # Preserve failed downloads/stages for diagnosis; never overwrite or auto-delete.
    if download_cache is None:
        paths = {a["filename"]: download(a, cache) for a in lock["archives"]}
    else:
        source_cache = Path(download_cache).absolute()
        require(
            source_cache.is_dir() and source_cache.resolve() == source_cache,
            "cache missing or linked",
        )
        paths = {a["filename"]: source_cache / a["filename"] for a in lock["archives"]}
    runtime = work / "runtime"
    runtime.mkdir()
    for artifact in lock["archives"]:
        rows = [r for r in lock["files"] if r["archive"] == artifact["filename"]]
        checked = inspect_archive(paths[artifact["filename"]], artifact, rows)
        for row, content in checked:
            destination = runtime / row["destination"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(content)
            destination.chmod(row["mode"])
    digest = verify_tree(runtime, inventory)
    require(read_bounded_bytes(lock_path) == lock_bytes, "acquisition lock changed")
    receipt = {
        "schema": 1,
        "status": "ACQUIRED_RUNTIME_ONLY_NOT_RELEASE_ADMISSION",
        "platform": lock["platform"],
        "acquisition_lock_sha256": lock_digest,
        "runtime_inventory_sha256": digest,
        "runtime_file_count": len(inventory),
        "runtime_bytes": sum(r["size"] for r in inventory),
        "archives": [
            {"filename": a["filename"], "sha256": a["sha256"], "size": a["size"]}
            for a in lock["archives"]
        ],
        "materials_status": (
            "UNCHANGED_43_COMPONENTS_42_RETAINED_ISSUES"
            if lock["platform"] == "linux-x64"
            else "WINDOWS_COMPONENT_MAPPING_NOT_REVIEWED"
        ),
        "native_execution": False,
    }
    with (work / "runtime-inventory.json").open("xb") as stream:
        stream.write(canonical(inventory))
    with (work / "acquisition-receipt.json").open("xb") as stream:
        stream.write(canonical(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument(
        "--download-cache",
        type=Path,
        help="Read-only reuse; every archive size/hash reverified",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            acquire(args.lock, args.work_root, args.download_cache), sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
