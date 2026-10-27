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

## Cleanup/quarantine release blocker

The cleanup suite's default fixture is now an opaque lifecycle identity for the
tests that already substitute a non-CAD job port. A safety test proves that this
identity cannot enter real guarded transport or evidence acceptance.

Threaded worker and exact-class admission-order cases request `worker_harness`.
It captures the real Linux manual profile on Linux and the real public bundled
profile on the actual Windows host, copying inert fixture data into the exact
module-local record classes. It never changes the host platform or relaxes type
checks. The existing worker exchanges are fault-injected; native process/API
leaves are forbidden, and a retained attempt counter prevents an expected worker
exception from hiding an accidental native call. This is lifecycle/record
coverage, not native backend or Blender qualification. No module-wide skip was
introduced.

## Captured receipts and pure visual owners

The shared visual-owner fixture now uses an explicit logical epoch for the
already synthetic display/publication ports. Its stale-epoch controls remain
active. A separate rejection proof sends that stamp to the real transport and
guarded-evidence entry points; neither accepts it. Shared candidate-create,
explicit-replay, load-rebuild and motion-preview consumers execute those pure
owner assertions on Windows.

Receipt/publication tests use `captured_backend_fixture.py`. On Linux it retains
the real manual selection. On the actual Windows host it uses public bundled
capture with the namespace's exact immutable record classes and regular inert
files in a short, test-local directory. Production path resolution, receipt
binding, currentness and class checks all stay active. No platform spoof, type
waiver, filesystem link or native launch is involved. Interpreter/DLL/solver
bytes are inert fixture data, not a usable backend. Process/API entry points are
forbidden, and an attempt counter survives failure/cancellation paths. Existing
foreign files/directories must fail receipt identity comparisons after a clean
positive succeeds. The fresh-interpreter nine-operation check retains its deny
finder for Blender/core/native imports and constructs the same Windows profile
through public capture.

The dormant data-only result-3 service explicitly rejects every bundled profile
before model validation. Its original manual-profile lifecycle, receipt,
currentness and process tests remain unchanged in
`test_service_v3_lifecycle_linux.py`; they require the Linux-only manual profile.
The portable module tests exact-class rejection before later leaves, and the
Windows-specific cases use a real public captured profile to prove bundled,
policy and descriptor admission rejection. No service guard is removed to make
an unsupported profile run. These scopes establish neither native Windows
backend qualification nor Blender usability.

Source/fixture readers in these modules specify UTF-8. Windows' legacy default
encoding must not reject valid source or change Unicode constants before an AST
audit. Reviewed hashes, exact allowlists, authority assertions and negative
mutation checks retain their original values and remain live.

The mixed client-contract module uses the same captured fixtures. Its Linux
venv/symlink invocation test remains Linux-specific. Windows instead compares
identical bytes in two ordinary files and rejects the alternative invocation
and resolved target after accepting the original receipt. This neither creates
a filesystem link nor establishes native Windows link support.

`test_guarded_transport.py` scopes only its real manual-profile child-process
cases to Linux. Its stale-before-launch, cancel-before-launch and forged-request
cases execute on Windows with an exact public capture, inert files and forbidden
native leaves. The original real-child test bodies and assertions are retained;
`test_windows_transport.py` separately executes Windows process-owner composition
against explicit fake OS/API leaves. Neither suite relabels mocks as a native
Windows child or Blender qualification.

The captured-record factory is registered in the unit directory's `conftest.py`.
Pytest resolves dependencies of an imported fixture in the importing test's
fixture namespace, so the compact-status and saved-sketch-extrusion consumers
must be able to find it too. Registration is opt-in; it does not introduce an
automatic fixture, change capture behavior, or add native work during collection.

Assembly STEP packet defaults use the actual host's temporary directory. Explicit
invalid/relative path arguments still pass unchanged to production validation;
the foreign-receipt destination remains a different valid host-absolute path.
The literal `..` destination comparison still proves that path text is neither
resolved nor silently rewritten. Part-owner diagnostic prefixes likewise derive
from the captured root, with an independent host-absolute assertion that catches
single-leading-slash fixtures even on older Windows Python versions.

Combined receipt projection tests explicitly bind both their selected record and
the imported receipt producer to the captured fixture. Importing a helper alias
does not inherit the defining module's automatic fixture setup.

Additional owner, profile, insertion and pending-sidebar AST audit readers use
UTF-8. The mutation fixture's source append helper also writes UTF-8 with LF to
retain the original bytes outside its intentional append. Normalizing away only
these I/O options leaves the complete audit-module ASTs unchanged: no approved
hash, allowlist, mutation or assertion is rebased. Cache-owner materialization
composition and unsupported manual-profile native groups remain outside this
bounded repair pass.
