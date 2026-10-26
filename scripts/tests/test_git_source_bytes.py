"""Exact-byte Git round trips, using tiny local repositories and no user config."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def git(tmp_path):
    # Isolate inherited repository/config overrides without changing global Git
    # settings. All repositories and clones are temporary and strictly local.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_ATTR_NOSYSTEM="1")
    empty = tmp_path / "empty"
    empty.mkdir()

    def run(directory, *args):
        return subprocess.run(
            [
                "git",
                "-c",
                "core.autocrlf=true",
                "-c",
                "core.safecrlf=false",
                "-c",
                f"core.attributesFile={os.devnull}",
                "-c",
                f"core.hooksPath={empty}",
                "-c",
                f"init.templateDir={empty}",
                "-c",
                "commit.gpgSign=false",
                "-c",
                "user.name=Byte preservation test",
                "-c",
                "user.email=test@example.invalid",
                *args,
            ],
            cwd=directory,
            env=env,
            check=True,
            capture_output=True,
        ).stdout

    return run


@pytest.mark.parametrize("payload", [b"first\nsecond\n", b"first\r\nsecond\r\n"])
def test_repository_attributes_preserve_add_clone_and_checkout_bytes(tmp_path, git, payload):
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init")
    (source / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
    relative = "fixtures/hash-pinned.py.txt"
    fixture = source / relative
    fixture.parent.mkdir()
    fixture.write_bytes(payload)
    git(source, "add", ".gitattributes", relative)
    git(source, "commit", "-m", "Local byte fixture")
    assert git(source, "cat-file", "blob", f"HEAD:{relative}") == payload
    assert git(source, "cat-file", "--filters", f"HEAD:{relative}") == payload

    clone = tmp_path / "clone"
    git(tmp_path, "clone", "--no-hardlinks", str(source), str(clone))
    assert (clone / relative).read_bytes() == payload
    (clone / relative).unlink()
    git(clone, "checkout", "HEAD", "--", relative)
    assert (clone / relative).read_bytes() == payload
    assert git(clone, "status", "--porcelain") == b""
    # Unlike the binary macro, -text must not disable readable text diffs.
    attributes = git(clone, "check-attr", "text", "diff", "merge", "--", relative)
    assert b"text: unset" in attributes
    assert b"diff: unspecified" in attributes
    assert b"merge: unspecified" in attributes
    (clone / relative).write_bytes(payload.replace(b"second", b"changed"))
    diff = git(clone, "diff", "--", relative)
    assert b"+changed" in diff
    assert b"Binary files" not in diff


def test_autocrlf_control_reproduces_unprotected_lf_conversion(tmp_path, git):
    git(tmp_path, "init")
    payload = b"first\nsecond\n"
    (tmp_path / "fixture.txt").write_bytes(payload)
    git(tmp_path, "add", "fixture.txt")
    git(tmp_path, "commit", "-m", "Unprotected local fixture")
    assert git(tmp_path, "cat-file", "blob", "HEAD:fixture.txt") == payload
    assert git(tmp_path, "cat-file", "--filters", "HEAD:fixture.txt") == payload.replace(
        b"\n", b"\r\n"
    )
