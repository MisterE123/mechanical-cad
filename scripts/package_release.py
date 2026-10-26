#!/usr/bin/env python3
"""Build source, full Git history and the installable UI add-on without binaries.

Run after tests and a clean commit. This does not publish, upload or create a Git
remote. Native OCCT/Blender/Python dependencies are intentionally excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tomllib
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Developer-only: archives still contain committed files only",
    )
    parser.add_argument(
        "--label", default="workspace-preview", help="Short lowercase release scope label"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.label):
        raise SystemExit("Release label must contain lowercase words/numbers separated by hyphens.")
    if git("status", "--porcelain") and not args.allow_dirty:
        raise SystemExit("Commit the tested changes before packaging a release.")
    commit = git("rev-parse", "HEAD")
    metadata = tomllib.loads(git("show", "HEAD:pyproject.toml"))
    version = metadata["project"]["version"]
    release = metadata["tool"]["mechanical_cad"]["release"]
    prefix = f"mechanical-cad-{version}-{args.label}-{commit[:7]}"
    timestamp = datetime.fromtimestamp(int(git("show", "-s", "--format=%ct", "HEAD")), timezone.utc)
    archive_time = timestamp.timetuple()[:6]
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    source = destination / f"{prefix}-source.zip"
    bundle = destination / f"{prefix}-history.bundle"
    addon = destination / f"{prefix}-blender-addon.zip"
    subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=zip", f"--output={source}", "HEAD"],
        check=True,
    )
    subprocess.run(["git", "-C", str(ROOT), "bundle", "create", str(bundle), "--all"], check=True)
    addon_files = git("ls-files", "blender_addon/mechanical_cad_blender").splitlines()
    if not addon_files:
        raise SystemExit("No committed add-on files to package.")
    with zipfile.ZipFile(addon, "w", zipfile.ZIP_DEFLATED) as archive:

        def add_file(name, data):
            # Committed bytes and commit time, never mutable working-tree data.
            info = zipfile.ZipInfo(name, date_time=archive_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)

        for name in addon_files:
            data = subprocess.check_output(["git", "-C", str(ROOT), "show", f"HEAD:{name}"])
            add_file(str(Path(name).relative_to("blender_addon")), data)
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            data = subprocess.check_output(["git", "-C", str(ROOT), "show", f"HEAD:{name}"])
            add_file(f"mechanical_cad_blender/{name}", data)
    manifest = {
        "version": version,
        "label": args.label,
        "commit": commit,
        "scope": release["scope"],
        "blender_minimum": release["blender_minimum"],
        "qualified_runtime": release["qualified_runtime"],
        "source_history": "Full Git bundle; no Git remote or publication",
        "dependency_binary_policy": "No native dependencies bundled; install pinned PyPI sidecar separately",
        "files": {},
    }
    for path in (source, bundle, addon):
        manifest["files"][path.name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
    manifest_path = destination / f"{prefix}-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "source": str(source),
                "history": str(bundle),
                "addon": str(addon),
                "manifest": str(manifest_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
