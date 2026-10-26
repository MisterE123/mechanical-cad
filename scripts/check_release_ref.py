"""Read-only version/tag check; not standalone release qualification."""
import ast
import os
import re
import subprocess
import tomllib
from pathlib import Path


def check(root, ref):
    if re.fullmatch(r"refs/tags/v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", ref) is None:
        raise ValueError("Select an existing vMAJOR.MINOR.PATCH tag, not a branch")
    version = ref.removeprefix("refs/tags/v")
    actual = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if version != actual:
        raise ValueError(f"Tag version {version} differs from project {actual}")
    tree = ast.parse((root / "src/mechanical_cad/__init__.py").read_text())
    core = next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets))
    if core != version:
        raise ValueError("Core version differs from tag")
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True, env=dict(os.environ, GIT_NO_REPLACE_OBJECTS="1")).strip()
    sha = git("rev-parse", "HEAD")
    if sha != git("rev-parse", ref + "^{commit}"):
        raise ValueError("Checkout differs from tag commit")
    subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", sha, "refs/remotes/origin/main"],
        check=True, capture_output=True, timeout=120,
        env=dict(os.environ, GIT_NO_REPLACE_OBJECTS="1"),
    )
    print(f"Version/tag checked: {version}, source commit {sha}; qualification not established")


if __name__ == "__main__":
    check(Path.cwd(), os.environ["GITHUB_REF"])
