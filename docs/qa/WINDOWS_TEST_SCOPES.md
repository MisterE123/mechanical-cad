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

The earlier tripwire exposed missing pin-directory/lock proof in the automatic
preparation-transfer fixture. Its reviewed follow-on now constructs the real
exact-class `WindowsCacheOwner` with a finite in-memory metadata API at `api=`.
The API returns the importing module's concrete info, security, ACE and volume
records. Actual acquire, retained identity/ACL checks, private-entry one-link
checks, worker affinity and close execute; none is replaced by a success stub.
Only query, pin and materializer remain named lifecycle ports. The fake pin port
creates records in memory, never files or native handles. Its release requires
the real owner to be closed with all resources retired first.

Each bad pin ACL, directory reparse, two-link file, retained-identity change and
uncertain owner-close control first completes a clean preparation. Metadata
failures prevent materialization and successful descriptor/recipe transfer;
their pin can release only after clean owner closure. Uncertain owner cleanup
quarantines the original owner and pin, exposes no recipe, and never releases
the pin or retries an uncertain handle. Clean-error recipe metadata alone is
not authority: descriptor consumption must succeed before any transfer.
The original transfer/cleanup expectations remain asserted. Thirty-seven
explicit cases passed, including 31 existing owner controls. No native DLL/API,
actual cache preparation/publication, subprocess or Blender proof is claimed.

Earlier unsupported-host spoof tests were replaced by actual-host wrong-profile
metadata controls. Unsupported-host execution itself was not tested on Techbox.

## CLI subprocess source and text decoding

The CLI subprocess helper now captures raw bytes, requires the existing reviewed
`process_source_binding` proof, and only then reads each stream with strict UTF-8
and the existing text-mode universal-newline semantics. The CLI already writes
its confirmation stream as UTF-8; the old locale-default cp1252 reader corrupted
Unicode paths on Windows. No production CLI encoding, output bytes, confirmation
expectation, export implementation or golden fixture changed.

Both console and module entry paths use the same source-binding machinery as
the backend process harness. Every project import is bound to intended checkout
bytes; origin/hash or preloaded-project failures reject the process before its
output is decoded or accepted. Module execution retains `runpy`'s `__main__`
semantics; console execution retains its `-c` argv identity. Proofs are separate
files, never protocol output. `-B` prevents child bytecode writes.

The explicit Techbox selection collected and passed 15 cases: all four existing
`test_cli_export_process_stdout_contains_only_confirmation` STEP/STL and
console/module cases, plus 11 generated-source controls. Those controls exercise
an ambient older tree, a preloaded foreign package, wrong module origin, changed
source bytes, correct UTF-8 versus cp1252 interpretation and strict invalid-UTF-8
rejection. Each source-fault control first succeeds with clean fixture source.
The wrong-origin child emits invalid UTF-8 to prove source rejection precedes
decoding; the valid-source/invalid-UTF-8 control proves decoding remains strict.
All original CLI test bodies and assertions are preserved exactly.

Earlier ambient CLI subprocess results loaded the retained runtime's older
source tree despite `PYTHONPATH`; they are not current-source qualification.
The repaired four-case result binds current working-tree source bytes, with CI
checkout providing the outer commit identity. Other CLI tests and broader suites
were not executed in this bounded pass. It establishes neither native Windows
packaging nor Blender usability; Windows native release remains NOT_READY.

## Manual guarded and legacy bridge contracts

Named Linux marks retain nine `test_general_guarded_capabilities.py` cases whose
manual `BackendSelection.capture` intentionally rejects other hosts before native
evidence exists. Their original bodies, helpers and assertions are unchanged.
The Part result module marks only its two real sidecar-client cases, three real
geometry-client cases and one open-not-solid bridge case. Its 56 validator,
mutation and isolated-import cases remain active on Windows.

The sketch-pending module marks its six genuine manual sidecar/worker cases and
the real invalid-configuration case. The latter retains the exact Linux Project
Root assertion. A separate actual-Windows admission-order counterpart uses the
real default `SidecarJob` constructor, observes actual lease acquisition/release,
and forbids configuration, path, temporary-file, process and worker leaves.
It is an early-rejection control, not a substitute successful Windows sidecar.
All portable identity, strict response, lease and lifecycle cases remain active.

Collection retained all 22 Linux cases with true Windows skip conditions. The
explicit Windows execution list contains 55 Part in-process cases, 111 sketch
cases and seven new deterministic clock cases. Two unchanged portable import-only
subprocess tests remain active in CI but were excluded from this local execution.
All 173 selected cases passed, including every setup and teardown; no Linux
process case executed. This is not a broad module skip or complete suite pass.

The first bounded run's incomplete reporting and blocked pytest housekeeping
attempts remain recorded separately. The reviewed private runner now disables
JUnit, cacheprovider and external plugin autoload, clears addopts and preserves
incrementally flushed phase/failure reports with separate stream capture. It
omits only the inspected optional pytest current-alias helper, with both paths
strictly bounded beneath a fresh run-owned basetemp. Application and native guard
functions are unchanged. Its generated pass/intentional-failure validation and
the final 173-case execution recorded zero forbidden process/link attempts.

Distinct Windows public-path coverage remains in `test_windows_live_capture.py`
(bundled policy capture versus closed external capture), `test_windows_transport.py`
(real transport/owner composition with narrow fake OS leaves) and
`test_service_v3_lifecycle.py` (public-record rejection by the dormant service).
Those do not establish native parity with the retained Linux manual-process
cases. No production admission, class, authority or platform guard changed;
Windows native packaging and Blender qualification remain NOT_READY.

## Sketch cleanup deadline rounding

At an unchanged large clock value, deadline addition/subtraction can produce a
remaining wait of `0.02000000001862645` for a `0.02` budget. `cancel_all` now caps
that wait by the original seconds as well as the existing decreasing shared
deadline. The original strict `<= 0.02` assertion is unchanged. There is no new
deadline, retry, tolerance or authority to release an unconfirmed owner.

Seven deterministic regressions replace only the sketch-pending module's time
reference, leaving shared `time.monotonic` intact. One publicly admitted job
exercises unchanged large time, elapsed time, expiration, zero timeout and wait
exceptions. No second job is manufactured around the exclusive lease. Pending
cleanup and wait exceptions keep the lease held with no response consumed;
confirmed later cleanup/reap releases it. Eleven focused cancellation/clock/
Windows-admission cases passed before the 173-case selection ran. This is pure
adapter and ownership coverage, not native Windows transport qualification.

## Legacy transport admission and public Windows composition

Only named tests that enter the manual `SidecarJob` constructor or legacy bridge
transport have Linux scope. Some mock the process; their Linux scope describes
the admission/integration contract, not a claim that they run native geometry.
Every original body, helper, assertion and pre-existing decorator is preserved.

| Original module | Retained Linux cases | Original portable cases active on Windows |
| --- | ---: | ---: |
| `test_sidecar_job.py` | 66 | 3 |
| `test_bridge.py` | 17 | 5 |
| `test_bridge_geometry_actions.py` | 47 | 9 |
| `test_bridge_sketch_reports.py` | 31 | 0 |

The Linux count includes eight already-POSIX-only cases and eight generic
exception cases that could pass at Windows admission without reaching their
intended assertion boundary. No whole-module skip is used. The legacy v1 geometry
response path remains a Linux integration contract; bundled guarded operations
select v2/v3 instead. Existing strict typed Part/geometry validators remain active
on Windows. A legacy v1 reply is not relabeled as a supported Windows success.

`test_legacy_transport_validation.py` adds 43 portable data-only cases. It reuses
the original sketch mutation table against the real `_validate_sketch_report`
helper, with a clean positive before every mutation. The actual bounded request
snapshot helper retains finite/plain-JSON, exact byte limits, resource rejection
and detached-copy coverage. These calls never enter or override legacy admission
and cannot mint process evidence or publication authority.

`test_windows_public_transport.py` uses actual Windows public `capture_bundled`,
real `SidecarJob.from_selection`, guarded transport, receipt validators and
publication/lease ownership. Existing finite fake OS APIs drive the real owner
composition. The reused `test_windows_runtime.install` fixture also substitutes
`_verify_cached_tree`, `_read_launch_inputs` and `pins.acquire_bundle_pin`
(with its explicit `Pin` lifecycle double). These named seams do not perform real
filesystem inventory verification or native pin acquisition. This proves
transport/owner/receipt composition, not an OS-leaves-only integration.
Short generated paths contain inert files solely so the unchanged
receipt path resolver can verify identity; no interpreter or CAD library is run.
The earlier missing synthetic-path failure is retained separately. The private
qualification constructor, native DLL bindings and native subprocess calls are
forbidden with counters. Absorbing quarantine uses a fresh instance of the real
lease module, preserving its original owner without resetting other tests.

Fourteen public-path cases cover exact request bytes/fresh nonce, one-shot result
and publication, cancellation before launch, ready cancellation, wrong owner,
stale selection, common envelope/nonce/fingerprint/document rejection, and cleanup
uncertainty that retains the original lease/pin and suppresses publication/retry.
Twenty existing Windows owner/stream controls retain limits, original cleanup
order, ambiguous-close ownership and no-retry assertions.

The first six public composition cases passed before expansion. The final
explicit selection collected 255 cases, retained all 161 Linux cases without
executing them, and ran 94 Windows cases: 17 original portable, 43 data-validator,
14 public composition and 20 existing owner/limit cases. All 94 passed with zero
forbidden audit attempts and all setup/teardown phases passing. All 74 original
functions/helpers preserve exact source and AST apart from named Linux marks.
Production admission, class/authority checks and goldens are unchanged. This is
neither native Windows process/geometry parity nor packaged Blender qualification;
Windows native release remains NOT_READY.

Five additional portable controls execute only the current constructor's pure
snapshot/encoding statements, extracted in order from its source. They do not
invoke or bypass constructor platform admission. Four resource cases prove the
final encoder runs on a clean positive and is never reached for cyclic, expanded
DAG, oversized-string or oversized-integer input. The final-encoder mutation case
proves caller mutation cannot alter detached wire bytes and that the now-invalid
caller is rejected before a second encoding. A local globals/JSON facade keeps
shared JSON/reporting untouched. Original Linux constructor controls remain
unchanged; this is data-preflight ordering evidence, not Windows native parity.

## Standalone material opening metadata

Only the original physical FIFO mutation and FIFO-before-open swap cases have
explicit Linux scope. Their bodies and assertions remain unchanged. Six portable
controls supply FIFO/socket/directory lstat or fstat metadata at the builder
module-local opening boundary; no nonregular filesystem object is created. Each
first verifies real regular-file stream/copy/hash success, then proves rejection
before stream wrapping, copy, base build or publication. A rejected opened file
is closed once. Global OS functions and production validation remain unchanged.

The original inert-materializer case retains its real Linux publication path and
body under explicit Linux scope. A separate actual-Windows case retargets the
interpreter, runtime inventory and materials-map pins together. It uses the
caller's exact imported manifest/cache classes, `ComposedStorage` and its fake
`FileMetadataAPI` observations around real `WindowsCacheOwner` checks. Real
`materialize_bundle` and `verify_cached_bundle` inventory, staging, rename and
recheck execute, with exact cached membership/size/hash, no materials visits or
execution sentinel, and closed owner/handle/allocation assertions.

Before building, only this case's two ZIP publishers receive the reviewed
`publish_inert_zip` exclusive-copy double through module-local OS facades. The
shared production publisher and global link functions are unchanged. This is
inert archive/materializer/owner composition, not atomic/hard-link publication,
native ACL/retained-handle or backend/Blender qualification.

## Backend runtime manual and bundled currentness

Twenty cases in `test_backend_runtime.py` require Linux manual selection. Only
those named test functions receive Linux scope; all original bodies, assertions
and parameter tables are unchanged. Worker-thread ownership and forged-selection
rejection remain portable and passed on actual Windows.

The existing Windows timeout/lifetime test remains unchanged. Ten additional
actual-Windows public-profile controls cover timeout/tolerance A-to-B-to-A
revocation, reentrant recapture ordering, callback-failure revocation, and
ReferenceError/AttributeError observation loss and restoration for preferences,
timeout and tolerance. They use real preference lookup, configuration, public
`capture_bundled`, exact record identity and currentness logic with inert policy
records. Native cache/preparation/process/DLL calls and the private qualification
capture are forbidden and counted. They do not use manual admission, host spoofing
or private capture to claim parity. This is runtime authority coverage, not native
Windows process/cache or Blender qualification.

## Recovery persistence host contract

`Store.write` supports the POSIX lock path and intentionally rejects actual
Windows before decoding or filesystem access. Eleven named writer/lock test
functions now have explicit Linux scope, retaining 15 cases; the three existing
POSIX ownership/contention/crash cases remain collected. Every original real
write/lock/crash body and assertion is unchanged. Some negative lock/temp cases
previously passed at Windows platform admission without exercising their intended
POSIX failure boundary; they are no longer counted as Windows lock coverage.

Envelope, checksum, bounds, document and graph validators, read-only listing and
filename checks remain portable. A separate portable control preserves the mixed
path test's traversal/slot and nonregular inventory obligations without writing.
The existing missing-no-follow test now uses a module-local OS facade, since
Windows does not expose `O_NOFOLLOW`; the real global OS module stays unchanged.
Two actual-Windows controls retain the host guard and prove rejection before
decode, root inspection, filesystem or lock leaves, with a missing root and an
existing sentinel. No writer lock or work file appears and sentinel bytes remain
exact. Windows recovery writes remain unsupported.

The explicit bounded selection passed 53 Windows cases: 13 runtime/currentness
and 40 recovery validators/rejections. Collection retained 38 Linux cases
(20 manual runtime and 18 recovery) without executing them. Filesystem-link and
contention/crash subprocess tests were excluded from local execution. These
results do not qualify native Windows locking or recovery publication.

## Clevis existing-evidence diagnostics

The existing-evidence generator case retains exit 2, exact sentinel bytes and
no-overwrite assertions. Its expected error is now the full `FileExistsError`
string obtained from the same exclusive mkdir operation on that exact host/path,
rather than POSIX-only wording. A pure host-error/sentinel control passed. The
generator subprocess case was not run locally in this slice.

The disposable generator fixture initializes/commits a fresh Git checkout, then
runs Python with `-S -B` and `PYTHONPATH`. The generator verifies its imported
project paths, probes a second child origin, collects Git/source provenance and
checks canonical bytes before exclusive evidence-directory creation. The retained
embedded Python `_pth` ignores `PYTHONPATH`; this route needs explicit source
binding review before local execution. No generator/native evidence is claimed
from the pure error-message control.

## Snapshot duplicate-wire security and legacy admission

Only the real-process canonical snapshot case and the two mocked legacy
duplicate-wire integration cases in `test_part_snapshot_bridge.py` receive Linux
scope. The duplicate cases are admission/decoder integration contracts, not native
geometry tests. Original bodies remain unchanged. In-process canonical validators,
authored-input immutability, checksum and resource mutation controls stay active.

Two new portable controls first parse/validate a clean canonical response, then
reject duplicate envelope or nested keys through the real
`bridge.parse_document_json`, preserving the original request. Two actual-Windows
public-profile controls inject ambiguous RAW response bytes into the existing
finite process-owner API composition. The real decoder rejects them before result
or evidence handoff; each original owner closes its resources once, releases its
pin and lease, and refuses result reuse or job restart without another API event.
The last duplicate value is otherwise valid, so accepting last-key-wins JSON would
fail these controls. The documented inventory/launch-input/pin doubles remain;
this is decoder/owner/receipt composition, not native process or geometry parity.

## Remaining legacy integration map

The finite 17-case review map is:

| Existing test function | Cases | Scoped disposition |
| --- | ---: | --- |
| assembly_result_v2: `test_new_native_response_roundtrips_through_addon_client` | 3 | Linux manual/native addon roundtrip |
| bridge_constrained_integration: `test_real_sidecar_sketch_diagnostics_cross_strict_display_boundary` | 5 | Linux legacy sidecar/native diagnostics |
| edge_catalog: `test_real_guarded_sidecar_transport` | 1 | Linux manual guarded transport |
| sketch_dof_cycles: `test_real_blender_bridge_replay_retains_failure_in_both_negotiated_versions` | 2 | Linux legacy bridge replay |
| part_snapshot_bridge: `test_real_process_capture_with_current_interpreter` | 1 | Linux legacy real-process snapshot |
| part_snapshot_bridge: `test_duplicate_wire_response_keys_are_rejected_by_existing_transport` | 2 | Linux mocked legacy decoder/admission; portable and Windows raw-byte controls added |
| assembly_bridge: `test_assembly_process_errors_use_safe_shared_transport` | 2 | Unchanged; new public start-error diagnostic needs review |
| clevis_example: `test_generator_rejects_unqualified_or_destructive_requests[existing_evidence]` | 1 | Exact host expectation corrected; local subprocess execution deferred |

Only the six named functions totaling 14 cases receive Linux scope in this slice.
Their exact bodies/assertions and original parameter/decorator tables are retained.
Other native in-process result validators and portable controls remain eligible
on Windows. The final bounded Windows selection passed 63 data/public-composition
cases with zero forbidden operations; collection retained the 14 Linux cases and
three deferred cases without execution. This is not native Windows parity or a
claim that all 17 original integration cases were executed or passed locally.

## Failed-start error ordering

A failed Windows process start may complete original-owner cleanup and release
its pin before returning. `WindowsOperationOwner.exchange` now raises the retained
process error immediately after its existing cleanup-budget check, before the
normal success checkpoint. This preserves the original error code instead of
classifying the later retired-pin check as a response failure. `finally` cleanup,
expired/uncertain cleanup precedence and every success/polling pin/deadline check
remain unchanged. The original cause was retained on the process owner even
before this change; no successful result or unsafe cleanup was observed.

Seven explicitly selected actual-Windows composition cases passed: clean public
success; failed create with exact original error identity/code and one pin
release; timeout; ambiguous failed-start closure and expired cleanup retaining
original pin/lease/quarantine; successful start followed by pin loss or a late
deadline rejecting before either output read. Fake API leaves, inventory/input
and pin seams remain explicitly documented. No native Windows execution is
implied.
