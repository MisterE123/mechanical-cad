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
composition was addressed in the subsequent bounded pass below. Unsupported
manual-profile native groups remain deferred.

## Concrete Windows owner and materializer composition

On Windows, `test_runtime_bundle_materialize.py` now composes its namespace's
exact `WindowsCacheOwner` with short host-absolute package/cache roots on a worker
thread. `windows_materializer_fixture.py` supplies explicit fake token, ACL,
volume and handle metadata leaves; real file identity/link observations use the
inert temporary files. Native API construction and DLL binding are forbidden.
Production binding, worker affinity, path budgets, ownership, ACL and one-link
checks remain active. Extraction, hashes, inventory, ready marker, stage rename,
shared recheck and resource retirement are real unit-test composition.

Each metadata-fault case first completes an independent clean materialization
and recheck. Faults cover two-link observations, reparse attributes, foreign ACL
ownership, changed identity after rename, cancellation, uncertain cleanup and
attempted native binding. Uncertain resources remain recorded without retry or
deletion. Existing Windows hook tests observe real owner methods on Windows;
their original POSIX method doubles remain unchanged on Linux. No private-entry
check is replaced by blanket success in the Windows composition.

The Linux payload/POSIX mode mutation and two existing FIFO tests remain
platform-scoped. Windows link/reparse negatives use metadata/predicate controls
without creating filesystem links. Its retained open payload can reject a
replacement with WinError 5/32; that branch requires unchanged original bytes
and no published tree. Linux keeps its original replacement assertions.

The two isolated builder/materializer tests build a Windows-target inert payload
on Windows and use the same concrete-owner composition, including shared
reverification. Only their ZIP publication leaf is an explicit exclusive-copy
test double: this does not prove production atomic hard-link publication. The
native-import deny finder remains active in the separate interpreter.

A broader local builder run invoked existing native link tests and confirmed
WinError 5 for hard-link publication and WinError 1314 for symlink creation.
Those actions were not repeated after that run. The remaining builder tests
requiring those actions are not qualified by the bounded composed run. No
production guard or publication implementation was changed. These observations
establish neither native cache ACL/locking behavior nor Windows/Blender release
qualification; Windows remains NOT_READY.

## Historical/live differential child framing

The 50 pre-service differential cases and lazy historical-kernel loader run
unmodified historical/live source under explicit test-child UTF-8/LF text
framing. Both sidecars create a UTF-8 response writer with `os.fdopen`; their
default Windows newline translation otherwise adds CR before the sealed LF.
The opt-in child harness sets its text streams to UTF-8/LF and supplies LF only
when that UTF-8 writer leaves newline unspecified. Other process tests retain
their ordinary harness behavior, and production code is unchanged.

Captured stdout/stderr remain raw bytes. Separate child controls exercise both
stdout and the duplicated-descriptor writer under an ASCII ambient encoding,
then prove that explicit binary CRLF/invalid stderr bytes and explicitly chosen
text CRLF remain unchanged. Request/example readers specify UTF-8 and have
independent non-ASCII part/assembly controls. Sealed source, hashes, golden
stdout, raw-byte comparisons and existing mutation assertions are unchanged.
These are differential framing tests, not native bundled runtime qualification.

The bounded Techbox Python 3.12.10 run collected 70 explicit safe cases and
finished 61 passed / 9 failed. All six framing/Unicode controls, the lazy-loader
test and 13 mutation/hash controls passed; 41 of the 50 differential cases passed.
Six historical native outputs still differ from the sealed golden bytes after
LF framing. Three dependency-absence cases also fail locally: the retained
embedded runtime's `python312._pth` explicitly includes `Lib/site-packages`, so
`-S` does not remove those native packages. No numeric tolerance, dependency
policy, golden/hash value or production behavior was changed to hide these
remaining observations. They require separate review; this is not a full pass.

The process harness now binds project imports explicitly to its intended
checkout, independently of `PYTHONPATH`. A test-only source loader compiles the
captured live bytes rather than accepting an ambient module or cached bytecode;
origin and SHA-256 checks compare to that checkout's current bytes, not frozen
hashes for intentionally live files. The pinned historical engine/sidecar/kernel
remain exact overrides. Their unpinned shared dependencies use the intended
current tree. A separate per-child proof must verify before the parent accepts
protocol output. No diagnostic marker is added to protocol stdout. Private
entry scripts avoid Windows' command-line size limit for historical source.

Controls accept intended source despite an ambient older directory, reject a
preloaded older package, reject a mismatched module origin even with well-formed
response JSON, and reject source bytes changed after capture. Each rejection
has a positive control first. A failed source proof cannot become successful
merely because final verification or expected-error handling runs afterward.

A read-only related-helper audit found the same environment-only selection in
integration replay, sidecar-actions, CLI, part-snapshot, versioned-sketch, clevis,
cut-chain and install-verifier processes, plus core-import children in the arc
profile suites. Those helpers were not executed or repaired in this slice.
Earlier Techbox subprocess totals involving those paths do not qualify the
current source. Parent-process AST checks remain checks of the files they read;
the geometry-result client child separately supplies an explicit add-on package
path and is not evidence of this particular core-source-selection defect.
Source binding also does not make `-S` remove embedded `_pth` package entries;
the three dependency-unavailability cases are handled in the separate slice below.

The subsequent controlled-unavailability slice keeps the original `-S` flag but
adds an explicit child-only import policy for exactly `invalid_deflection`
(OCP), `solver_dependency_absent` (slvs), and `kernel_dependency_absent` (OCP).
Historical/live children receive the same policy. Already-loaded target roots
or descendants reject setup; normal and dynamic imports of selected roots and
descendants raise the top-level `ModuleNotFoundError` envelope. Standard-library
and current-checkout imports remain available. Native positive cases receive no
policy. Controls prove these properties without creating a physically different
runtime, and all three original raw golden/error comparisons pass unchanged.

Only six demonstrated platform-sensitive native cases use a Linux-specific
sealed-output baseline: the three `primitive_cut_result_*` cases,
`replay_circle_sketch_part`, `replay_parameter_chain`, and
`independent_failure_graph`. Their original exact golden assertions remain in
`test_linux_native_pre_service_golden`. Windows executes these same requests in
`test_windows_native_pre_service_full_raw_differential`: source proofs must pass
first, return codes remain exact, and full current stdout must equal the
pre-existing reviewed transformation of the full captured historical stdout.
There is no tolerance, mesh sorting, extra transformation or Windows golden.

All 50 sealed request/golden integrity cases execute on every host. The other
44 behavioral comparisons retain exact golden equality on Windows as well as
Linux, including controlled unavailability and portable/non-native cases. The
entire mixed suite is not scoped to Linux. Separate positive-before-negative
controls for each of the six native cases reject unreviewed vertex changes,
triangle-index changes, feature identity changes, errors and JSON key order.
Neither a Windows differential pass nor Linux golden equality proves native
Windows packaging, retained-handle/ACL behavior or Blender usability. Earlier
ambient subprocess evidence is not retroactively qualified by source binding.

The final explicit Techbox Python 3.12.10 selection collected 166 cases and
finished 160 passed / 6 skipped. The skips are exactly the six Linux native
golden cases; all 50 integrity cases, 44 remaining exact-golden comparisons,
six Windows full-byte native differentials, and the source/visibility/framing
and mutation controls executed. This is a bounded current-source process-harness
result. The Linux baseline was not executed on Techbox, no wider Windows suite
pass is claimed, and Windows standalone/native Blender release remains NOT_READY.

## Dormant-service owner rejection

All 36 cases in `tests/integration/test_service_v3_owner_rejection.py` require
the shared `real_cases` fixture's Linux/manual capture and native sidecar packet
production. The module now states that Linux-only scope with an explicit
platform mark; its 25 functions/fixtures, including all 15 original test bodies
and their assertions/decorators, are preserved exactly. Collection retains all
36 nodes. Windows does not execute their fixtures or substitute bundled/fake
records for those process packets. No Linux process execution is claimed here.

Windows executes the portable dormant-service rejection counterparts in
`tests/unit/test_service_v3_lifecycle.py`: five foreign-record cases, three
actual public Windows capture/policy/descriptor rejection cases and one new
subclass control. The existing cases did not distinguish an exact-class guard
from `isinstance`; the new control first observes the real public selection's
intentional dormant rejection, then requires its otherwise identical subclass
to reject sooner at the exact-class gate. Model/currentness/job leaves remain
forbidden, alongside the capture fixture's native process/API traps. This uses
regular inert fixture files and real public capture, not a native backend or
Blender process. Production class, authority and bundled rejection guards are
unchanged; native Windows release qualification remains NOT_READY.

The bounded pure path/encoding pass keeps current-host UI paths separate from
historical wire spelling. Document suffix and expanded recovery-folder fixtures
expect the host's `Path` rendering. The four sealed geometry export observations
use `PurePosixPath` only for their historical POSIX destination expectation;
stored request/response bytes, fingerprints and SHA-256 checks are unchanged.
No export runs in these tests. Frozen arc-envelope JSON and the assembly action
AST helper read UTF-8 explicitly. The stale-action label matches its original
UTF-8 source; no caption, checksum, privacy rule or production code changed.
Only the 17 named pure cases were executed; CLI export, subprocess/native tests,
Blender and broad modules/suites remain outside this pass.

The bundled-runtime lifecycle fixture uses actual-host metadata and short
host-absolute Windows package paths. Windows requests retain `cache_root=None`
and use only the named fake `for_bundled_windows` job port, which captures and
returns a detached concrete `WindowsCacheLocation`. Real runtime begin/poll,
host/profile admission, callback revocation, cleanup gating and policy transfer
remain active. Linux retains its original package/cache values and generic job
port. Replacement setup changes the Windows package, not an unsupported manual
cache override. Wrong-profile metadata is rejected on the actual host without
spoofing it. Detached-literal checks mutate to the other host's profile.

Native API/DLL binding, subprocess launch and real preparation/pin/materializer
leaves are forbidden with retained attempt counters. The Windows setup-capture
and timeout/lifetime counterparts also run with tripwires and assert real host
module identity rather than substituting Windows platform values on Windows.
This is lifecycle-port coverage, not native cache, publication or Blender proof.

The separately inspected automatic preparation-transfer counterpart still needs
its original private-entry success stub for the pin directory/lock. Replacing
that stub with a tripwire stopped before any OS action and exposed the fixture
gap. Its original test remains unchanged and is excluded from this bounded
execution claim; a concrete owner/API fixture needs separate review. No new
private-entry success shortcut or production guard change was introduced.
