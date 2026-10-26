# Opt-in local recovery (source development)

This is a bounded recovery-copy feature for unsaved **Part canonical JSON and
supported sketch intent**, not a native allocator crash fix, automatic Save,
full document history, geometry cache or backup service. Frozen 1.22 is unchanged.

## Explicit choice and retention

The add-on preference **Enable local recovery (unencrypted)** defaults to **off**.
It is also exposed in the CAD sidebar's Local Recovery panel. A model or `.blend`
file cannot enable it. Enabling stores unencrypted design and sketch data on this
computer, under Blender's per-user configuration directory:
`mechanical_cad/recovery-v1`. The current path is shown in the collapsed **Storage and coverage details**
section beside the setting.
Nothing is uploaded, exported, put in Git, or sent over a network.

The observer checks every two seconds on Blender's main thread. This is a
best-effort interval while Blender is responsive and CAD transactions are idle,
not a guaranteed two-second maximum loss window. Native jobs, modal acceptance,
long callbacks and disk stalls delay capture. All edits newer than the reported
last successful disk snapshot can be lost. Disk errors are visible and do not
turn a valid CAD publication into a failed model operation.

Each runtime Blender-session/Scene/document-ID combination gets a fresh random
scope. Loading a file starts fresh scopes; scope IDs are never loaded from model
content. This is not per-file history: opening the same document in another
Scene or session produces another scope. Two generations are retained per scope.
Bounds are 2 MiB canonical text, 8 MiB draft text, 12 MiB complete envelope,
32 scopes, and 128 MiB total directory use including temporary/unknown files.
JSON escaping can reach the envelope bound before individual text bounds.
Quota exhaustion refuses new writes; no other session or original file is evicted.
Disabling retains existing snapshots. This initial milestone offers no automatic
cleanup or retention expiry; there is no in-product cleanup action yet.

The synchronous write avoids a worker queue, stale worker publication, shutdown
thread races and all off-main-thread RNA access. Large snapshots can briefly
stall the UI. This is a correctness-first bounded milestone, not a latency claim.

## What is covered

The exact canonical Scene string and a supported draft codec's raw intent are
captured together only after settled transactions and postchecks. Live draft
serialization retains accepted command history and invalid raw length text, not
queued acceptance, native solver authority, input leases/tokens or display meshes.
The observer does not write the Scene checkpoint slot.

Part schemas 1/2 and explicitly supported embedded sketch capabilities are
validated without rewriting original strings. Draft codec dispatch is strict;
its recorded base must match the exact canonical bytes, including whitespace.
Unknown or corrupt state is refused rather than normalized, migrated or discarded.

Assembly scenes, unapplied repair and exceptional in-memory sketch conflict
copies are **not covered**. Their presence visibly pauses capture rather than
claiming that all active work is safe. Prior disk snapshots remain intact. Scene
objects, materials, generic Blender data and standalone annotation layout outside
the supported draft envelope are not included. Continue saving `.blend` and CAD
documents explicitly for those needs.

## Explicit restore only

**Restore Local Snapshot as New Scene** lists document names, random scope
prefixes, generation numbers and UTC timestamps; the newest readable timestamp
sorts first. The dialog binds its selected generation to a full-envelope digest; if that slot
rotates before confirmation, Restore refuses and asks to reopen the chooser.
Every restore validates envelope, checksums, size/schema limits and
exact draft/base binding before creating anything. A corrupt entry remains on
disk unchanged and Restore refuses it clearly.

Restore always creates a fresh Scene, never merges into or overwrites the current
Scene or a file. Canonical byte identity (and therefore internal Part ID) is
preserved in this unsaved copy. `document_path` is empty, Assembly data/bindings
are absent, display/solver authority is absent and a recovered sketch is suspended.
Explicit Resume must freshly validate the sketch; Regenerate must build fresh
geometry. Restore is refused while a live sketch owner or CAD operation is active.
The original Scene and objects remain untouched. No automatic restore occurs at
startup, load, enable or recovery discovery.

## Storage protocol

The version-1 data-only envelope carries kind/version, random scope, monotonic
sequence, UTC creation time, exact canonical/draft strings and SHA-256 checksums
of each string. Filenames are generated only from validated scope and slot IDs.
No model name, recovered path or `document_path` becomes a storage path.

Writing uses an exclusive random temporary, mode 0600, full write/flush/file
fsync and atomic replace of the older of two slots. At least the previous newest
generation remains intact if writing fails. Directory fsync is best effort where
supported; this is process-exit recovery, not certified power-loss durability.
Stale sequence numbers cannot replace newer data. A nonblocking POSIX advisory
lock serializes writers across Blender processes through temporary cleanup; a
busy writer causes a visible retry-later failure instead of blocking indefinitely.
The zero-byte private lock file is retained. Writes fail closed on platforms
without this locking support; this milestone is Linux-only. Root ancestors, symlinks,
nonregular entries and hard-linked entries are refused. Unknown/corrupt files are
retained; quota checks include their bytes. This directory is not an adversarial
multi-user secure vault; it is private, unencrypted user-local application storage.
Static symlinks/path escapes are rejected, but hostile same-user concurrent
replacement of ancestor directories is outside its protection boundary.

## Evidence

Focused pure storage tests cover exact string identity/raw invalid input, strict
envelopes, monotonic ordering, two-generation retention, bounds/quotas, path and
symlink refusal, original-file preservation, and injected write/fsync/replace
failures. Native smoke exercises opt-out, postcheck rollback, Finish/Discard,
visible disk failure and fresh-Scene restore. A two-process case captures unsaved
canonical data (parameterized rectangle/extrusion, native volume 2880 mm³) plus a natively
accepted draft line and invalid pending length,
then restores in another Blender process **without `.blend` or `.mcad` Save**.
Bounded source-loaded GUI evidence is recorded below.
This is not a full inherited-suite, installed-package or Windows qualification.

### Focused verification record, 2026-10-25

- 59 pure storage tests and 57 existing draft-dispatch tests pass. The store test
  set includes real subprocess lock contention while a temporary file is held.
- Native Blender 5.2.2 smoke passes `LOCAL_RECOVERY_SMOKE_OK`, including immediate
  empty/changed/unsupported status, missing/corrupt disk-copy detection, read-only
  invalid-context inspection, and preference isolation through actual file loads.
- Separate fresh-process capture/restore pass `LOCAL_RECOVERY_PROCESS_CAPTURE_OK`
  and `LOCAL_RECOVERY_PROCESS_RESTORE_OK` with `--python-exit-code 1`, exit zero.
  The unsaved canonical Part has a natively published parameterized rectangle
  and extrusion (2880 mm³); no display objects or volume authority survive restore.
  Invalid raw length is inspected unchanged before explicit proposal cancellation
  and fresh native Check. No model or `.blend` Save is used in that case.
- Cloud Linux GUI, source-loaded disposable profile: default OFF and disclosure
  inspected; checkbox explicitly enabled; timed snapshot appeared; Restore dialog
  cancelled without Scene change, reopened and accepted; a new empty-display
  unsaved Scene showed the suspended sketch and fresh-validation requirement.
  The original Scene remains separately available. This is bounded opt-in/restore
  GUI evidence, not exhaustive authoring/Undo GUI qualification.
- Ruff passes for changed Python files. No new dependencies were installed.

All fixtures are generated and disposable. Recovery was not enabled on the
user's computer. No package, upload, source publication or frozen-release change
is part of this source milestone. The unresolved native allocator crash remains.

### Restore chooser RNA correction

The enum callback receives an `OperatorProperties` wrapper, not the owning
operator. Pending chooser snapshots now use a hidden, non-saved nonce plus the
RNA properties pointer. Execution additionally requires the original operator
pointer and private snapshot identity. Each dialog retains immutable choices
and fingerprint bindings; cancel, execute and failed invoke revoke only that
invocation. Enum strings remain retained for the module/UI lifetime.

`tests/blender_recovery_rna_smoke.py` exercises two simultaneously live registered
operators through real `bpy.ops`, including interleaved bindings, copied-token
refusal, rotation refusal, cancellation and retained strings. Only popup
presentation is mocked there. Actual cloud Blender 5.2.2 GUI separately verified
panel-click popup, Cancel, selected-slot rotation refusal, then successful fresh
selection into a new unsaved Scene with original objects preserved. The earlier
Python-proxy chooser smoke did not cover the real RNA callback and was replaced.
This is not evidence about the pre-existing allocator crash.

### Compact recovery controls (source development)

The ordinary expanded Local Recovery panel now keeps only the opt-in setting,
current status, essential Linux-only/unavailable-Windows, unencrypted local
Part/sketch, best-effort/not-Save and off-retains-copies disclosures, and the
**Restore as New Scene** action visible. These essential warnings remain visible
before enabling recovery. Longer retention, timing, scope, excluded-work and
folder explanations move behind **Storage and coverage details**, closed by
default and not saved with preferences. The same presentation is used in add-on
preferences. The outer sidebar panel continues to default closed, with status
in its header. Restore and errors are never hidden behind the details toggle.

This is presentation only: no capture timing, storage, quota, capability,
validation, chooser binding or fresh-Scene restore behavior changed. Nine focused
pure draw-policy tests cover collapsed/expanded copy, narrow-width line budget,
status visibility, Restore ordering, default-off and non-saved disclosure state.
The 59 existing pure storage tests also pass (68 focused tests total).
Changed-file Ruff passes. Native/source GUI evidence is separate; this change
has not been packaged or qualified on Windows.

Bounded source-loaded Blender 5.2.2 Linux GUI review used a disposable profile
and the existing generated canonical/draft fixture. It verified default OFF,
the closed outer panel, visible consent with inner details closed, explicit
expansion/collapse, opt-in, timed snapshot status and the actual Restore chooser.
Restoring produced two Scenes, preserved the original Scene and objects, kept
canonical/draft bytes equal and the recovered path empty, with zero restored
display objects. The compact expanded recovery panel occupied approximately
330 pixels of sidebar height at the tested narrow width rather than the previous
full-height disclosure. Collapsing recovery and opening Mechanical CAD exposed
Return to Sketch, Discard Draft, Save and Regenerate without scrolling through
recovery explanations. This does not qualify exhaustive GUI/Undo, a new installed
archive, Windows or the unresolved native allocator crash.

The source GUI process exited cleanly (exit 0); test-only canonical/draft bytes
and scene inventory were preserved and reread before closure.
