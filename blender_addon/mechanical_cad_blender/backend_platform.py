"""Unselected process contracts; none of these records grants CAD authority.

This development leaf does not change selection, SidecarJob, receipts or leases.
Windows identity validation and cross-process pin implementations are separate
integration gates. A setup-only bundle descriptor is never an operation receipt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .runtime_bundle_manifest import BundleDescriptor

MAX_INPUT_BYTES = 2 * 1024 * 1024 + 4096
MAX_DESCRIPTOR_BYTES = 16 * 1024
MAX_BOOTSTRAP_CHARS = 4096
MAX_STDOUT_BYTES = 64 * 1024 * 1024
MAX_STDERR_BYTES = 64 * 1024


class ProcessError(RuntimeError):
    """Bounded local diagnostic; never copies model data or environment values."""

    def __init__(self, code: str, *, operation: str = "", winerror: int | None = None):
        self.code = code[:80]
        self.operation = operation[:80]
        self.winerror = winerror
        super().__init__(f"{self.code}: {self.operation} ({winerror})"[:200])


@dataclass(frozen=True)
class LaunchSpec:
    """Captured trusted release code and exact prepared bytes, not model argv.

    ``bundle.root`` must be the final atomically published private cache, never
    staging or compressed installed payload. The mandatory identity validator
    verifies that fact and opened anchors. This type only checks finite syntax.
    Prepared-request and descriptor JSON validation belong to the guarded owner
    and fixed bootstrap; this process layer does not reinterpret either payload.
    """

    bundle: BundleDescriptor
    bootstrap: str = field(repr=False)
    environment: tuple[tuple[str, str], ...] = field(repr=False)
    request_payload: bytes = field(repr=False)
    descriptor_payload: bytes = field(repr=False)
    timeout: float = 60.0

    def __post_init__(self):
        from .runtime_bundle_manifest import BundleDescriptor

        if type(self.bundle) is not BundleDescriptor or self.bundle.platform != "windows-x64":
            raise ProcessError("wrong_platform")
        if any(
            type(value) is not str or not value or len(value) > 32767 or "\0" in value
            for value in vars(self.bundle).values()
        ):
            raise ProcessError("invalid_bundle_descriptor")
        if (
            type(self.bootstrap) is not str
            or not self.bootstrap
            or len(self.bootstrap) > MAX_BOOTSTRAP_CHARS
            or "\0" in self.bootstrap
        ):
            raise ProcessError("invalid_bootstrap")
        for value, limit in (
            (self.request_payload, MAX_INPUT_BYTES),
            (self.descriptor_payload, MAX_DESCRIPTOR_BYTES),
        ):
            if type(value) is not bytes or not value or len(value) > limit:
                raise ProcessError("invalid_launch_bytes")
        if type(self.timeout) not in (int, float) or not math.isfinite(self.timeout):
            raise ProcessError("invalid_timeout")
        object.__setattr__(self, "timeout", max(1.0, min(float(self.timeout), 300.0)))
        if type(self.environment) is not tuple or len(self.environment) > 16:
            raise ProcessError("invalid_environment")
        names = set()
        for pair in self.environment:
            if type(pair) is not tuple or len(pair) != 2:
                raise ProcessError("invalid_environment")
            key, value = pair
            if (
                type(key) is not str
                or type(value) is not str
                or not value
                or key.upper() not in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
                or key.upper() in names
                or "\0" in value
                or len(value) > 32760
            ):
                raise ProcessError("invalid_environment")
            names.add(key.upper())


@dataclass(frozen=True)
class LaunchObservation:
    """Handle-derived diagnostics, never executable-by-handle authentication."""

    process_id: int
    creation_time: int
    image_path: str


class RuntimePin(Protocol):
    """Already-acquired shared cross-process pin, transferred to process owner.

    ``release`` must either succeed or leave ownership conservatively uncertain.
    A failed release is never retried automatically. The owner does not delete
    caches. Crash-orphan/child-held pins require later integration qualification.
    assert_held is checked before resume, while polling and before returning
    output. Its failure revokes success, but release must still attempt resource
    cleanup even after assert_held has failed.
    """

    bundle_id: str
    mode: str

    def assert_held(self) -> None: ...
    def release(self) -> None: ...


class LaunchValidation(Protocol):
    """Reviewed identity seam; retain all opened anchors until ``close``.

    Implementations must clean partial acquisitions in their eventual close,
    compare the captured descriptor without recapturing, and reject unsupported
    path/identity policy. after_create checks handle-derived observations before
    resume. The callbacks must not launch a process or release the runtime pin.
    close must clean retained anchors even when the pin is no longer valid.
    """

    def before_create(self, spec: LaunchSpec) -> None: ...
    def after_create(self, spec: LaunchSpec, observed: LaunchObservation) -> None: ...
    def close(self) -> None: ...


class OwnedProcess(Protocol):
    """Worker-only ownership. UI cancellation must use the existing token/owner.

    Root exit alone is not cleanup. Keep the existing execution lease and this
    object until cleanup_complete is true; neither result nor CAD evidence is
    supplied by this protocol.
    """

    def poll_exit(self) -> int | None: ...
    def cancel_tree(self, reason: str = "cancelled") -> None: ...
    def close_after_cleanup(self) -> bool: ...
    def cleanup_complete(self) -> bool: ...
