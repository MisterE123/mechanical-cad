"""Pre-main candidate execution and publication event/permission boundaries."""

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


source = load("event_source_under_test", "check_pipeline_source.py")
publisher = load("event_publisher_under_test", "publish_release.py")


@pytest.fixture
def candidate_repo(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n')

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    git("init", "-b", "development")
    git("add", ".")
    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "candidate",
    )
    return repo, git("rev-parse", "HEAD"), git


def environment(event, ref, commit="a" * 40):
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": event,
        "GITHUB_REF": ref,
        "GITHUB_SHA": commit,
        "CANDIDATE_COMMIT": commit,
    }


@pytest.mark.parametrize(
    "event,ref",
    [
        ("push", "refs/heads/techbox/release-pipeline"),
        ("workflow_dispatch", "refs/heads/main"),
        ("workflow_dispatch", "refs/tags/v1.2.3"),
    ],
)
def test_candidate_runs_without_tag_or_main_and_binds_exact_checkout(candidate_repo, event, ref):
    repo, commit, git = candidate_repo
    assert git("for-each-ref", "refs/tags", "refs/heads/main", "refs/remotes/origin/main") == ""
    result = source.check(repo, environment(event, ref, commit))
    assert result == {
        "SOURCE_COMMIT": commit,
        "RELEASE_TAG": "v1.2.3",
        "CANDIDATE_FLAG": "--candidate-only",
    }


@pytest.mark.parametrize("bad", ["abcd1234", "f" * 40, "HEAD", "a\nSOURCE_COMMIT=b"])
def test_candidate_rejects_inexact_or_mismatched_source(candidate_repo, bad):
    repo, commit, _ = candidate_repo
    env = environment("push", source.CANDIDATE_BRANCH, commit)
    env["GITHUB_SHA"] = bad
    with pytest.raises(ValueError, match="exact|full"):
        source.check(repo, env)


def test_release_still_requires_existing_tag_and_main_membership(candidate_repo):
    repo, commit, git = candidate_repo
    env = environment("push", "refs/tags/v1.2.3", commit)
    with pytest.raises(subprocess.CalledProcessError):
        source.check(repo, env)
    git("tag", "v1.2.3")
    with pytest.raises(subprocess.CalledProcessError):
        source.check(repo, env)
    git("update-ref", "refs/remotes/origin/main", commit)
    assert source.check(repo, env)["CANDIDATE_FLAG"] == ""


@pytest.mark.parametrize(
    "event,ref",
    [
        ("push", "refs/heads/main"),
        ("push", "refs/heads/source-validation"),
        ("push", "refs/heads/techbox/unapproved"),
        ("pull_request", source.CANDIDATE_BRANCH),
        ("pull_request_target", source.CANDIDATE_BRANCH),
        ("workflow_run", "refs/tags/v1.2.3"),
        ("push", "refs/tags/v01.2.3"),
        ("push", "refs/tags/v1.2.3-extra"),
    ],
)
def test_unapproved_events_and_refs_fail_before_source_lookup(event, ref):
    with pytest.raises(ValueError, match="Unsupported"):
        source.candidate_event(environment(event, ref))


@pytest.mark.parametrize(
    "event,ref",
    [
        ("push", source.CANDIDATE_BRANCH),
        ("workflow_dispatch", "refs/tags/v1.2.3"),
        ("workflow_dispatch", source.CANDIDATE_BRANCH),
        ("pull_request", "refs/tags/v1.2.3"),
    ],
)
def test_candidate_events_cannot_reach_api_or_token_even_with_admission(
    tmp_path, monkeypatch, event, ref
):
    admission = {"source_commit": "a" * 40, "tag": "v1.2.3"}
    monkeypatch.setattr(publisher.P, "read", lambda *a: admission)
    monkeypatch.setattr(publisher.P, "admit", lambda *a: admission)
    monkeypatch.setattr(publisher, "GitHub", lambda *a: pytest.fail("Candidate reached API"))
    monkeypatch.setattr(sys, "argv", ["publish_release.py", "--work", str(tmp_path)])
    for key, value in environment(event, ref).items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(ValueError, match="matching tag"):
        publisher.main()


def test_only_exact_tag_push_can_pass_publisher_event_gate():
    admission = {"source_commit": "a" * 40, "tag": "v1.2.3"}
    env = environment("push", "refs/tags/v1.2.3")
    publisher.require_publication_event(env, admission)
    env["GITHUB_SHA"] = "b" * 40
    with pytest.raises(ValueError):
        publisher.require_publication_event(env, admission)


def test_workflow_trigger_and_write_permission_policy():
    # Guard the checked-in workflow's intentionally simple event/job structure.
    # Behavioral event/source/publication checks above execute the real scripts.
    text = (ROOT / ".github/workflows/release.yml").read_text()
    events, jobs = text.split("jobs:\n", 1)
    assert "    branches: ['techbox/release-pipeline']\n" in events
    assert "    tags: ['v[0-9]*.[0-9]*.[0-9]*']\n" in events
    assert "pull_request_target:" not in events
    assert "permissions:\n  contents: read\n" in events
    before_publish, publish = jobs.split("  publish:\n", 1)
    assert "contents: write" not in before_publish and "GH_TOKEN:" not in before_publish
    assert "if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')" in publish
    assert publish.count("contents: write") == 1 and text.count("contents: write") == 1
    assert publish.count("GH_TOKEN: ${{ github.token }}") == 1


def test_supported_core_python_matrix_is_an_actual_publish_dependency():
    core = (ROOT / ".github/workflows/tests.yml").read_text()
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    regression, remainder = workflow.split("  regression:\n", 1)[1].split("  build:\n", 1)
    core_versions = ast.literal_eval(core.split("        python: ", 1)[1].splitlines()[0])
    release_versions = ast.literal_eval(regression.split("        python: ", 1)[1].splitlines()[0])
    assert release_versions == core_versions == ["3.11", "3.12", "3.13"]
    assert "os: [ubuntu-24.04, windows-2022]" in regression
    assert "python-version: ${{ matrix.python }}" in regression
    assert "python -m pytest -q" in regression
    assert "continue-on-error" not in regression
    assert "needs: regression" in remainder.split("  native:\n", 1)[0]
    assert "needs: [regression, build, native]" in remainder.split("  publish:\n", 1)[1]
