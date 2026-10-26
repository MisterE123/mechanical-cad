"""Captured Linux sidecar selection, without Blender or native CAD imports.

Capture once on the owner thread; a detached transport uses these exact launch
values. Runtime epochs/generations belong to the owner, never canonical data.
Environment values are deliberately omitted from representation and diagnostics.
"""

from __future__ import annotations

import math
import ntpath
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from .runtime_bundle_launch import BundledLaunchPolicy, _windows_path

_DEFAULT_TIMEOUT = object()


def default_timeout_seconds(*, bundled_platform=None):
    """Finite initial default only; explicit or saved preferences always win."""
    return 240.0 if bundled_platform == "windows-x64" else 60.0


class SelectionError(ValueError):
    """The selected backend is unavailable, unsupported, or no longer current."""


def _path(value: str, label: str) -> str:
    if type(value) is not str or not value or len(value) > 4096 or "\0" in value:
        raise SelectionError(f"Invalid {label} path.")
    return value


def lexical_path(value: str) -> str:
    """Linux case-sensitive absolute spelling without resolving venv symlinks."""
    return os.path.abspath(os.path.normpath(_path(value, "executable")))


def resolved_path(value: str) -> str:
    """Fail closed on missing or unresolvable selected/observed identities."""
    try:
        return str(Path(_path(value, "backend")).resolve(strict=True))
    except (OSError, RuntimeError, ValueError) as exc:
        raise SelectionError("Backend identity path cannot be resolved.") from exc


def _expanduser(value: str, environment: Mapping[str, str]) -> str:
    # Path.expanduser() consults live os.environ for bare '~'. Use the already
    # captured environment instead so a selection has one resolution source.
    if value == "~" or value.startswith("~/"):
        home = environment.get("HOME")
        if home is None:
            import pwd

            home = pwd.getpwuid(os.getuid()).pw_dir
        return home.rstrip("/") + value[1:] or "/"
    return str(Path(value).expanduser())


@dataclass(frozen=True, slots=True)
class BackendSelection:
    """Immutable launch values plus a non-persisted owner lifetime/generation.

    Use capture(), not independent preference resolution in each consumer.
    assert_current() compares a newly observed effective selection; launching
    itself must use this captured object and never resolve settings again.
    """

    project_root: str
    python_executable: str
    python_executable_target: str
    timeout: float
    generation: int
    lifetime_id: str
    _environment: tuple[tuple[str, str], ...] = field(repr=False)
    bundled_policy: BundledLaunchPolicy | None = field(default=None, repr=False)

    def __post_init__(self):
        windows = (
            type(self.bundled_policy) is BundledLaunchPolicy
            and self.bundled_policy.constants.PLATFORM == "windows-x64"
        )
        if not windows and sys.platform != "linux":
            raise SelectionError("Guarded sidecar identity is currently qualified for Linux only.")
        for name in ("project_root", "python_executable", "python_executable_target"):
            value = _path(getattr(self, name), name)
            if windows:
                try:
                    _windows_path(value)
                except ValueError as exc:
                    raise SelectionError("Invalid Windows bundled selection path.") from exc
            elif not os.path.isabs(value) or os.path.normpath(value) != value:
                raise SelectionError(f"{name} must be an absolute normalized path.")
        if type(self.generation) is not int or self.generation < 0:
            raise SelectionError("Backend generation must be a nonnegative exact integer.")
        if type(self.lifetime_id) is not str or not 0 < len(self.lifetime_id) <= 256:
            raise SelectionError("Backend lifetime identity must be a nonempty runtime token.")
        if type(self.timeout) not in (int, float) or not math.isfinite(self.timeout):
            raise SelectionError("Backend timeout must be finite.")
        if not 1 <= self.timeout <= 300:
            raise SelectionError("Captured backend timeout must be within 1..300 seconds.")
        if type(self._environment) is not tuple or any(
            type(pair) is not tuple
            or len(pair) != 2
            or any(type(value) is not str or "\0" in value for value in pair)
            or not pair[0]
            or "=" in pair[0]
            for pair in self._environment
        ):
            raise SelectionError("Invalid captured launch environment.")
        if len(dict(self._environment)) != len(self._environment):
            raise SelectionError("Duplicate captured launch environment names.")
        if self.bundled_policy is not None:
            policy = self.bundled_policy
            if (
                type(policy) is not BundledLaunchPolicy
                or self.project_root != policy.descriptor.root
                or self.python_executable != policy.descriptor.python_path
                or self.python_executable_target != policy.descriptor.python_path
                or dict(self._environment) != policy.launch_environment()
            ):
                raise SelectionError("Captured bundled selection violates its launch policy.")
            return
        environment = dict(self._environment)
        if (
            "PYTHONHOME" in environment
            or environment.get("PYTHONPATH") != str(Path(self.project_root) / "src")
            or environment.get("PYTHONNOUSERSITE") != "1"
            or environment.get("PYTHONIOENCODING") != "utf-8"
        ):
            raise SelectionError("Captured environment violates the sidecar launch policy.")

    @classmethod
    def capture(
        cls,
        project_root: str = "",
        python_executable: str = "",
        timeout: float = 60.0,
        *,
        generation: int,
        lifetime_id: str,
        environment: Mapping[str, str] | None = None,
    ) -> BackendSelection:
        """Resolve explicit/default settings once, preserving the venv invocation."""
        if sys.platform != "linux":
            raise SelectionError("Guarded sidecar identity is currently qualified for Linux only.")
        if type(project_root) is not str or type(python_executable) is not str:
            raise SelectionError("Backend root and executable settings must be strings.")
        launch = dict(os.environ if environment is None else environment)
        if any(
            type(key) is not str
            or type(value) is not str
            or not key
            or "=" in key
            or "\0" in key
            or "\0" in value
            for key, value in launch.items()
        ):
            raise SelectionError("Invalid captured launch environment.")
        root_value = project_root or launch.get("MCAD_ROOT", "")
        root = resolved_path(
            _expanduser(root_value, launch)
            if root_value
            else str(Path(__file__).resolve().parents[2])
        )
        if not (Path(root) / "src" / "mechanical_cad").is_dir():
            raise SelectionError("Project Root must contain src/mechanical_cad.")
        executable_value = python_executable or launch.get("MCAD_PYTHON", "")
        invocation = lexical_path(
            _expanduser(executable_value, launch)
            if executable_value
            else str(Path(root) / ".venv" / "bin" / "python")
        )
        target = resolved_path(invocation)
        if not Path(invocation).is_file() or not os.access(invocation, os.X_OK):
            raise SelectionError("Sidecar Python must be a directly executable file.")
        try:
            if type(timeout) is bool:
                raise ValueError("boolean timeout")
            seconds = float(timeout)
            if not math.isfinite(seconds):
                raise ValueError("non-finite timeout")
        except (TypeError, ValueError, OverflowError) as exc:
            raise SelectionError("Backend timeout must be finite.") from exc
        launch.pop("PYTHONHOME", None)
        launch["PYTHONPATH"] = str(Path(root) / "src")
        launch["PYTHONNOUSERSITE"] = "1"
        launch["PYTHONIOENCODING"] = "utf-8"
        return cls(
            root,
            invocation,
            target,
            max(1.0, min(seconds, 300.0)),
            generation,
            lifetime_id,
            tuple(sorted(launch.items())),
        )

    @classmethod
    def capture_bundled(
        cls,
        policy: BundledLaunchPolicy,
        timeout: float | object = _DEFAULT_TIMEOUT,
        *,
        generation: int,
        lifetime_id: str,
    ) -> BackendSelection:
        """Use prepared immutable setup only; no manual settings or ambient environment.

        No filesystem lookup or native work occurs here. Every operation worker
        must reacquire a shared pin and fully verify this exact runtime policy.
        """
        if type(policy) is not BundledLaunchPolicy:
            raise SelectionError("Bundled capture requires an exact immutable launch policy.")
        expected = {("linux", "posix"): "linux-x64", ("win32", "nt"): "windows-x64"}.get(
            (sys.platform, os.name)
        )
        if expected is None or policy.constants.PLATFORM != expected:
            raise SelectionError("Bundled runtime does not match this operating system.")
        if timeout is _DEFAULT_TIMEOUT:
            timeout = default_timeout_seconds(bundled_platform=policy.constants.PLATFORM)
        try:
            if type(timeout) is bool:
                raise ValueError("boolean timeout")
            seconds = float(timeout)
            if not math.isfinite(seconds):
                raise ValueError("non-finite timeout")
        except (TypeError, ValueError, OverflowError) as exc:
            raise SelectionError("Backend timeout must be finite.") from exc
        return cls(
            policy.descriptor.root,
            policy.descriptor.python_path,
            policy.descriptor.python_path,
            max(1.0, min(seconds, 300.0)),
            generation,
            lifetime_id,
            tuple(sorted(policy.launch_environment().items())),
            policy,
        )

    @classmethod
    def _capture_windows_bundled_transport(cls, policy, timeout=60.0, *, generation, lifetime_id):
        """Dormant qualification seam; no production caller or currentness authority."""
        if cls is not BackendSelection or type(policy) is not BundledLaunchPolicy:
            raise SelectionError("Windows transport requires its exact bundled policy.")
        policy = replace(policy)
        if policy.constants.PLATFORM != "windows-x64":
            raise SelectionError("Windows transport requires its exact bundled policy.")
        try:
            if type(timeout) is bool:
                raise ValueError("boolean timeout")
            seconds = float(timeout)
            if not math.isfinite(seconds):
                raise ValueError("non-finite timeout")
        except (TypeError, ValueError, OverflowError) as exc:
            raise SelectionError("Backend timeout must be finite.") from exc
        return cls(
            policy.descriptor.root,
            policy.descriptor.python_path,
            policy.descriptor.python_path,
            max(1.0, min(seconds, 300.0)),
            generation,
            lifetime_id,
            (),
            policy,
        )

    @property
    def core_origin(self) -> str:
        if (
            self.bundled_policy is not None
            and self.bundled_policy.constants.PLATFORM == "windows-x64"
        ):
            return ntpath.join(self.project_root, "src", "mechanical_cad")
        return str(Path(self.project_root) / "src" / "mechanical_cad")

    def launch_environment(self) -> dict[str, str]:
        """A detached copy for Popen; never write these values to saved reports."""
        return dict(self._environment)

    def assert_current(self, current_selection: BackendSelection) -> None:
        """Owner seam for launch/poll/consume/publication and retained-seed use."""
        if type(current_selection) is not BackendSelection or self != current_selection:
            raise SelectionError("Backend settings or runtime lifetime changed; Check again.")
