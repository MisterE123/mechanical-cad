"""Establish exact workflow source; dispatch is always nonpublishing candidate mode."""

import os
import re
import tomllib
from pathlib import Path
from types import SimpleNamespace

import build_release_candidate as A


def check(root, environment):
    candidate = environment["GITHUB_EVENT_NAME"] == "workflow_dispatch"
    commit = environment["CANDIDATE_COMMIT"] if candidate else environment["GITHUB_SHA"]
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None or A.git(root, "rev-parse", "HEAD") != commit:
        raise ValueError("Checkout must equal requested full commit")
    version = tomllib.loads(A.git(root, "show", commit + ":pyproject.toml"))["project"]["version"]
    tag = "v" + version if candidate else environment["GITHUB_REF_NAME"]
    A.validation_identity(
        SimpleNamespace(
            source_repo=root,
            source_commit=commit,
            tag=tag,
            main_ref="refs/remotes/origin/main",
            candidate_only=candidate,
        )
    )
    return {
        "SOURCE_COMMIT": commit,
        "RELEASE_TAG": tag,
        "CANDIDATE_FLAG": "--candidate-only" if candidate else "",
    }


if __name__ == "__main__":
    values = check(Path.cwd(), os.environ)
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(key + "=" + value + "\n")
