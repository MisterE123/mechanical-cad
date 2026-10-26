# Self-contained Blender extension: isolated implementation

The target is one platform-specific Install from Disk ZIP containing the complete
isolated Python/CAD backend. First use must not require a separate source tree,
Python installation, package manager, network download or manual backend paths.
The Linux implementation has now passed ordinary offline Install from Disk,
automatic preparation, New Document, constrained Rectangle, extrusion, Geometry
Check, sector STEP/STL, and two-process save/reopen in the actual Blender GUI.
Native CAD remains isolated from Blender. These observations apply to the tested
internal candidate; they do not establish Windows support or release clearance.

The development source additionally connects bounded sector-solid Parts to the
existing rooted-tree Assembly workflow: capture, reuse, explicit source updates,
literal placement frames, joint edits and pose checks. The
[box-and-sector project](BOX_SECTOR_PROJECT.md) is the concrete regression and
walkthrough. Its successor installed-package/manual check remains pending.
Assembly-wide export and broader arc profiles remain unavailable.

## Current implementation, not a release

Automatic offline preparation is connected to enable/disable, main-thread
selection and the managed worker. Preferences show preparation/ready/failure
without requiring external source or Python paths. A manifest package missing
its generated constants stays blocked. Another enabled version's RNA ownership
is checked before registration.

Preparation owns one exclusive pin, transfers a setup descriptor once only after
confirmed cleanup, and retains uncertain owners across disable/re-enable. Each
actual operation reacquires a shared pin and rehashes the complete immutable
runtime before launch, retaining that pin through process/file cleanup. Published
caches are never deleted, repaired or replaced in place. A descriptor, hash,
startup diagnostic or marker is never CAD evidence.

The Linux child receives fixed isolated flags, a fixed bootstrap loader, a separate
read-only descriptor FD and unchanged guarded request stdin. Its environment is
built from a small explicit allowlist, including only the manifest-bound private
native directory. All existing request/nonce/receipt/currentness/once-only publisher
checks remain authoritative. Native CAD is never imported into Blender.

An independent inspection caught a synchronous wait that could remain blocked on
uncertain cleanup. The reviewed correction extends the existing lease with one
absorbing retained transport owner and scoped synchronous binding: return a clear
restart-required failure without releasing uncertain resources or allowing a
successor operation. Async owners retain their original job and lease and expose
the same diagnosis. Read-only cleanup banners cover Preferences, the ordinary CAD
panel and all CAD workspace histories, including orphaned/detached async owners.
They normalize raw job diagnostics to the fixed save-and-restart instruction and
never poll, reap, cancel or start work while drawing. Empty-document guidance uses
automatic offline setup in bundled mode and keeps manual paths only for the legacy
development mode. The retained Linux native and installed-GUI results exercise these lifecycle
paths; a new functional build still requires its own focused installed regression.

The accepted inert Linux profile adds exact private Expat/zlib and excludes only
the deprecated crypt.py/_crypt pair. It targets Debian 13 x86_64 with the eleven
explicit Blender/OS shared-library dependencies; it is not a general manylinux
compatibility claim. The pinned geometry kernel and solver are unchanged.

The closed automatic Windows cache source slice adds a fixed OS-known
LocalAppData\MechanicalCAD\r recipe, private retained-handle storage checks and
same-worker dormant preparation. Its existing extractor gains only a concrete
Windows storage owner at four functions; Linux checks remain intact. A created
stage is retained for diagnosis even when its helper fails before returning, and
Windows files/ready markers require exact one-link proof from the retained handle.
Registration now rejects Windows before any setup import/path/cache/timer work.
This describes the setup entry only, not all extension-import I/O. See
[automatic Windows cache storage](WINDOWS_CACHE_STORAGE.md) for the finite scope,
captured-location semantics and remaining native gates.

Windows live selection remains closed. Fake Win32 process/pin/cache tests do not prove
Windows execution. Actual Windows testing is deferred by the user, and public execution remains
disabled. Specific Linux source/notice obligations and Microsoft runtime
redistribution rights remain unresolved. No applicable
entitlement or legal acceptance has been assumed.

The builder emits a true root `blender_manifest.toml`, the Blender package and one
compressed offline backend payload. Native libraries are not Blender manifest
wheels. The tested internal materials-bearing Linux ZIP is 162,415,859 bytes.
That is a measured candidate size, not a final successor size. The delivery target
remains one ZIP; a supported large-file attachment route must be tested when the
artifact is ready. No splitting or manual reassembly is required by the design.

## Remaining release work

1. Finish the coherent box/sector project regression and check its exact installed
   successor through the ordinary UI, retaining editable project files and
   individual-Part exports.
2. Complete the actual component notice, source-access and modification/relink
   obligations in [the materials guide](STANDALONE_DISTRIBUTION_MATERIALS.md).
   Optional provenance work is distinct from those obligations; bit-identical
   upstream rebuilds are not a blanket prerequisite.
3. Package the tested source/runtime together, verify installation and preservation
   of existing documents/raw drafts, and deliver the single extension ZIP with the
   example project. Earlier release archives remain unchanged.
4. Qualify Windows on a real host when testing resumes. Its dormant fake-OS tests
   and closed transport do not establish a working Windows installer.

Blender manifest syntax follows the
[official schema](https://developer.blender.org/docs/features/extensions/schema/1.0.0/).
Private Install from Disk delivery is distinct from acceptance by the public
Blender Extensions marketplace.

## Dormant Windows transport source slice

The development source now composes the existing Windows process owner beneath
`SidecarJob`, with exact immutable Windows setup records, worker-only identity
and environment validation, bounded cleanup, child-only DLL-search hardening,
and pure fake-OS composition/admission controls. Public Windows selection and
legacy/manual launch routes remain closed. No Windows usability or release claim
follows from these tests.

At the historical transport-only baseline, the conventional Windows cache layout
exceeded ordinary path limits even for typical usernames, and registration could
perform cache-path I/O before rejecting Windows. The current closed cache slice
adds the fixed LocalAppData recipe and dormant same-worker preparation described
above, and its early registration guard rejects before that setup I/O. The later
launch-policy/operation binding is now implemented only through the dormant
private qualification seam: one read-only original cache owner precedes the
existing shared pin/full verifier, original job/stream handles receive private
ACL proof before writes, and cache cleanup precedes pin release under the same
absolute deadline. Public activation and genuine installed-first-use
qualification remain unimplemented. No preparation/native process or fresh
authority is admitted through the public Windows path. See
[the historical transport boundary](WINDOWS_TRANSPORT_INTEGRATION.md) and
[the current cache boundary](WINDOWS_CACHE_STORAGE.md).
