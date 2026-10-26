"""Single no-clobber GitHub publisher; reconcile uncertain writes, never retry them."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import release_pipeline as P
from check_pipeline_source import release_event


class GitHub:
    def __init__(self, repository, token):
        P.require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository), "Repository")
        self.repository = repository
        self.token = token

    def call(self, method, path, data=None, *, upload=False):
        host = "uploads.github.com" if upload else "api.github.com"
        request = urllib.request.Request(
            f"https://{host}/repos/{self.repository}/{path}",
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/octet-stream" if upload else "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if method == "GET" and error.code == 404:
                return None
            raise

    def write(self, method, path, value):
        return self.call(method, path, P.A.canonical(value))


def publish(api, root, admission, run):
    tag, commit = admission["tag"], admission["source_commit"]
    # Never create/move a tag implicitly. Resolve annotated tags without trusting target_commitish.
    ref = api.call("GET", "git/ref/tags/" + tag)
    P.require(ref is not None, "Missing existing release tag")
    obj = ref["object"]
    for _ in range(8):
        if obj["type"] == "commit":
            break
        P.require(obj["type"] == "tag", "Unexpected tag target")
        obj = api.call("GET", "git/tags/" + obj["sha"])["object"]
    P.require(obj.get("type") == "commit" and obj.get("sha") == commit, "Tag changed")
    tag_path = "releases/tags/" + tag
    P.require(api.call("GET", tag_path) is None, "Existing release: never overwrite or adopt")
    body = (
        "Mechanical CAD release admission\nRun: " + run + "\n" + P.A.canonical(admission).decode()
    )

    def same(release):
        return (
            release
            and release.get("tag_name") == tag
            and release.get("body") == body
            and release.get("target_commitish") == commit
        )

    try:
        release = api.write(
            "POST",
            "releases",
            {
                "tag_name": tag,
                "target_commitish": commit,
                "name": tag,
                "body": body,
                "draft": True,
                "prerelease": False,
            },
        )
    except (OSError, ValueError):
        # One read reconciliation; no second create, deletion or blanket adoption.
        release = api.call("GET", tag_path)
        P.require(
            same(release) and release.get("draft") is True,
            "Release creation uncertain; inspect remote state before any further write",
        )
    P.require(
        same(release) and release.get("draft") is True and not release.get("assets"),
        "Unexpected draft state; stop",
    )
    release_id = release["id"]
    files = {
        f"mechanical-cad-{tag[1:]}-{platform}.zip": root / platform / "candidate.zip"
        for platform in sorted(P.PLATFORMS)
    }
    files["admission.json"] = root / "admission.json"
    expected = {}
    for name, path in files.items():
        sha, size = P.identity(path)
        expected[name] = (sha, size)
        try:
            asset = api.call(
                "POST",
                f"releases/{release_id}/assets?name=" + urllib.parse.quote(name, safe=""),
                path.read_bytes(),
                upload=True,
            )
        except (OSError, ValueError):
            assets = api.call("GET", f"releases/{release_id}/assets?per_page=100")
            matches = [a for a in assets if a["name"] == name]
            P.require(len(matches) == 1, "Upload uncertain; inspect draft, do not rerun")
            asset = matches[0]
        P.require(
            asset.get("state") == "uploaded"
            and asset.get("name") == name
            and asset.get("digest") == "sha256:" + sha
            and asset.get("size") == size,
            "Remote asset identity unconfirmed; retain draft for reconciliation",
        )
    assets = api.call("GET", f"releases/{release_id}/assets?per_page=100")
    P.require(
        len(assets) == len(expected)
        and {a["name"]: (a.get("digest", "").removeprefix("sha256:"), a["size"]) for a in assets}
        == expected,
        "Final asset set differs",
    )
    # Tag identity is rechecked immediately before publication as well.
    P.require(api.call("GET", "git/ref/tags/" + tag) == ref, "Tag changed during uploads")
    try:
        final = api.write("PATCH", f"releases/{release_id}", {"draft": False})
    except (OSError, ValueError):
        final = api.call("GET", f"releases/{release_id}")
    P.require(
        same(final) and final.get("draft") is False,
        "Publication uncertain; reconcile remote state, never blindly retry",
    )
    return final


def require_publication_event(environment, admission):
    P.require(
        environment.get("GITHUB_ACTIONS") == "true"
        and release_event(environment)
        and environment.get("GITHUB_REF") == "refs/tags/" + admission["tag"]
        and environment.get("GITHUB_SHA") == admission["source_commit"],
        "Publication requires the matching tag workflow",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    stored = P.read(args.work / "admission.json")
    admission = P.admit(args.work, stored["source_commit"], stored["tag"])
    P.require(admission == stored, "Admission changed")
    require_publication_event(os.environ, admission)
    api = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"])
    result = publish(
        api,
        args.work,
        admission,
        os.environ["GITHUB_RUN_ID"] + ":" + os.environ["GITHUB_RUN_ATTEMPT"],
    )
    print("Published release id", result["id"])


if __name__ == "__main__":
    main()
