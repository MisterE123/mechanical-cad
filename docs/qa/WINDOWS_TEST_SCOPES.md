# Runtime launch test scopes

The Windows collection blocker in `test_runtime_bundle_launch.py` was an
unconditional `fcntl` import in a suite combining Linux process ownership with
portable record validation. The tests are now organized by their real contracts.

- `test_runtime_bundle_launch.py` retains portable record immutability, exact
  field/type validation and unknown-field rejection. Each capture mutation starts
  from an accepted profile. Windows policy records are checked on both hosts;
  Linux policy capture cases require a real Linux host. Linux constant-record
  shape validation still runs on Windows without constructing a Linux policy.
- `test_runtime_bundle_launch_linux.py` preserves Linux cache, descriptor-FD,
  cancellation, cleanup uncertainty, lease and real subprocess `flock` assertions.
  `fcntl` is imported lazily in its Linux fake-child constructor and in the
  retained real lock-probe child, never during Windows collection. The CAD and
  interpreter payloads stay inert; the real child is the standard-library lock
  probe. This explicitly Linux-specific suite is skipped on Windows.
- Native Windows host checks call real public `capture_bundled` without changing
  `sys.platform` or `os.name`. They test the Windows default, explicit timeout,
  currentness and rejection of unsupported Linux/manual routes before I/O.
  Captured selection/policy/descriptor records remain distinct from authorized
  guarded evidence. These checks do not launch a native backend or establish
  installed-runtime qualification.
- `test_backend_selection.py` identifies the external/venv route as Linux-only,
  including its path identity and environment tests. Its portable default data
  checks and actual Windows manual-route rejection remain active on Windows.
  Invalid-argument cases no longer pass vacuously through the Windows host guard.
- `test_windows_transport.py`, `test_windows_live_capture.py` and the Win32 pin
  tests retain synthetic API leaves and real higher-level state/cleanup checks.
  Those results are mock coverage, not real Windows kernel/process qualification.

Production launch, cache and selection guards were not changed. No model inputs,
authorization checks or unknown-field rejection rules were relaxed. The previous
denied Techbox hard-link/symlink operations were not retried; platform collection
uses no test bodies and the bounded Windows executions omit Linux filesystem-link
tests through their explicit native-host markers.

## Shared history and owner fixtures

The shared gesture/history fixture now uses an immutable
`PureHistoryBackendStamp` for reducers, row routing, fillet ports and picker state.
Its paths are explicit non-executable `pure-history://` identifiers. It is not a
`BackendSelection`, cannot supply a launch environment, and fails the unchanged
production type checks for guarded transport and evidence acceptance. Generation
changes remain explicit dataclass replacements; canonical model inputs and all
owner/rollback assertions remain unchanged.

The two recorded driver-chain cases instead request `native_backend_host`, which
uses the real Linux manual selection. Receipt acceptance, publication consumption
and revocation/currentness still execute unchanged against real captured identity.
Only those cases are Linux-scoped; the mixed gesture module and pure history
consumers execute on Windows.

The `test_geometry3_owner.host` fixture and its current-read/history-draw/panel
consumers validate actual source/interpreter filesystem identity and real
`GuardedEvidence`. They retain a Linux-qualified manual-backend fixture, with an
explicit skip on unsupported hosts rather than a fake identity or acceptance
waiver. Tests not requesting that fixture remain eligible on Windows. This does
not establish Windows row-presentation/freshness qualification. Windows bundled
public selection, manual rejection, admission, transport and runtime-cache suites
remain separate active counterparts; their API leaves/receipts are synthetic
where documented, not evidence of a launched native backend.
