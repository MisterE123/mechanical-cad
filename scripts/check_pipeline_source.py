"""Establish exact workflow source; approved branch pushes validate before main."""

import os
import re
import tomllib
from pathlib import Path
from types import SimpleNamespace

import build_release_candidate as A

CANDIDATE_BRANCH = "refs/heads/techbox/release-pipeline"
RELEASE_REF = r"refs/tags/v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"


def release_event(environment):
    return (
        environment.get("GITHUB_EVENT_NAME") == "push"
        and re.fullmatch(RELEASE_REF, environment.get("GITHUB_REF", "")) is not None
    )


def candidate_event(environment):
    if environment.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return True
    if (
        environment.get("GITHUB_EVENT_NAME") == "push"
        and environment.get("GITHUB_REF") == CANDIDATE_BRANCH
    ):
        return True
    if release_event(environment):
        return False
    raise ValueError("Unsupported release-pipeline event or source ref")


def check(root, environment):
    candidate = candidate_event(environment)
    commit = (
        environment["CANDIDATE_COMMIT"]
        if environment["GITHUB_EVENT_NAME"] == "workflow_dispatch"
        else environment["GITHUB_SHA"]
    )
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None or A.git(root, "rev-parse", "HEAD") != commit:
        raise ValueError("Checkout must equal requested full commit")
    version = tomllib.loads(A.git(root, "show", commit + ":pyproject.toml"))["project"]["version"]
    tag = "v" + version if candidate else environment["GITHUB_REF"].removeprefix("refs/tags/")
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
