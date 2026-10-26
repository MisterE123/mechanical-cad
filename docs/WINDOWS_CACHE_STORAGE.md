# Automatic Windows cache: dormant source boundary

This source slice implements a fixed automatic Windows cache preparation path
and its dormant binding to the existing Windows operation owner.
It does **not** enable Windows backend execution or qualify a Windows release.
The public registration, setup, backend selection and legacy execution gates
remain closed. No genuine Windows host, Blender installation or Windows API was
exercised by the Linux pure/fake controls used for this slice.

## Captured location and one existing worker

The explicit dormant query uses only
`SHGetKnownFolderPath(FOLDERID_LocalAppData, KF_FLAG_DONT_VERIFY, NULL)` and appends
exactly `MechanicalCAD\r`. There is no environment-variable or registry fallback,
manual cache/Python preference, alternative short root, alias or long-path opt-in.
The result is an immutable pair of strings. The query releases the original shell
allocation with `CoTaskMemFree` before returning that pair.

`BundlePreparationJob.for_windows_qualification` captures those strings and uses
the same preparation worker, cancellation state, exclusive full-ID lifetime pin,
materializer and one-shot setup descriptor transfer as the existing Linux path.
It cannot install a production launch policy or publish CAD evidence. The worker
never re-queries KnownFolder. It checks the filesystem objects reached through
those captured strings at acquisition and their retained identities afterward.
A later unrelated change to Windows KnownFolder configuration is not detected:
the existing request may continue at a still-valid captured location. A separate
new setup request obtains a new location. No pre-observation identity history or
configuration watch is claimed.

## Private storage and finite path policy

Only local fixed NTFS with persistent ACLs and ordinary uppercase-drive DOS
spelling is accepted. Reparse/offline paths, UNC/device paths, traversal, alternate
streams, aliases, percent signs, trailing-dot/space components and non-NFC spelling
are rejected. Supported accented, CJK and non-BMP characters are preserved, never
normalized into another pathname. Full bundle identities remain 64 hexadecimal
characters in final paths, staging names and stable lock filenames.

The worker retains original non-inheritable metadata handles to the existing
ancestry before creating only the two fixed application suffixes. Creation uses
an explicit protected private DACL for the current process user, SYSTEM and
Administrators. Existing objects are inspected without permission repair. Actual
handle security must demonstrate the same finite private-principal contract;
directory grants must separately provide effective user access and continuing
file/subdirectory inheritance. Windows `chmod` and a `mode=0o700` argument are not
privacy evidence. Administrators and hostile same-user software are outside this
boundary; pathname creation plus retained handles is not a sandbox or atomic
handle-relative creation.

Every installed input, full-ID pin, final path, exact staging candidate, manifest
file, parent directory and marker is budgeted before its corresponding use. Files
are limited to 259 UTF-16 units and directories to 247, with the volume's component
limit also checked. Each non-BMP character consumes two units. The limits are
calculated from the actual manifest rather than a remembered payload maximum.
Too-long installations or profiles stop with a bounded diagnostic; no setting,
registry change or manual backend path is offered as a workaround.

## One inventory and original ownership

The existing archive, exact membership, size, content hash, applicable mode,
ready-marker and descriptor checks remain authoritative. The only Windows
link-count observation comes from the concrete storage owner's retained original
file handle, whose link count must be an actual integer equal to one. Windows
`DirEntry.stat().st_nlink` may report zero and is not substituted for that proof.
The proof runs for every regular file, including `.bundle-ready.json`, before the
marker shortcut. The original Linux regular-file/one-link test remains intact.

A stage uses `.stage-<full64>-<eight lowercase hex>` with at most 16 exclusive
creation attempts. A collision is neither owned nor reused. Immediately after
native creation succeeds, the original owner records that exact candidate before
cancellation, allocation cleanup, anchor opening or metadata inspection can fail.
The Windows error path uses this pure creation record and never calls `exists()`
to recover a diagnostic. The record means an attempt was created at that name;
it does not promise the name still exists, including after successful rename.
Failed attempts are not repaired, resumed, overwritten or recursively deleted.

Only the stage-root deny-delete anchor is closed immediately before the existing
rename. Confirmed close is required; retained cache ancestry and the exclusive pin
remain. The reopened final must match the stage identity. A separately appearing
final follows the existing full-verification branch and is not compared to the
unrelated stage. All added cache handles/allocations must finish their once-only
cleanup before pin release. Uncertain cleanup retains the original owner and pin,
keeps `done` false, suppresses the descriptor and blocks successors. `LocalFree`
succeeds only with NULL; no numeric handle or allocation cleanup is retried.

## Dormant operation binding and pre-write proof

The private qualification path now captures an exact, detached automatic cache
recipe in the immutable launch policy and selection equality. Windows captures
validate primitive fields before copying or comparing them; Linux continues to
carry no Windows recipe. Descriptor, request and capability-receipt formats are
unchanged. This is not a production caller or an alternate manual cache path.

Every operation retains one original read-only cache owner before acquiring its
existing shared pin. The same owner proves the private pin directory and lock
file and reaches the existing complete inventory verifier. No cache creation,
repair, KnownFolder requery, second inventory, pin or worker is introduced.

The existing `.jobs/<uuid>` directory and all four original temporary streams
must pass actual private ACL checks before any stream initialization writes.
Directory anchors request READ_CONTROL. Stream checks borrow each original OS
handle and require canonical direct-child paths, local NTFS, regular nonreparse,
nonoffline, noninheritable single-link files with zero initial size. Four bounded
observations retain the original file, handle, identity and path for the launch
recheck; validation neither reopens nor closes those borrowed handles.

Cleanup remains in the existing process/validation/pin lifecycle: confirmed
process and stream cleanup, job retirement and runtime anchors, cache resources,
then the original shared pin. Cache close accepts the operation's original
absolute cleanup checkpoint. It checks entry, every native resource-release
admission and return, and completion. A confirmed release is recorded before a
late post-check rejects the outcome. Failure stops successor releases, prevents
pin release and usable output, and retains the original uncertain owners without
retry. An already entered OS call is not preemptible. The unchanged pin release
remains one observed call with its existing internal finite cleanup loop.

## Remaining qualification gates

Pure/fake tests establish only conditional source behavior and ownership ordering.
Genuine Windows qualification must still establish actual ABI behavior, DACL
inheritance under Blender's Python, canonical paths/Unicode, handle link counts,
sharing/rename semantics, pin contention, interruption/restart and clean offline
installation. Native operation/DLL origin/job cleanup, complete installed-path and
third-party TEMP budgets, exact package/source/license closure and installed GUI
first use remain separate gates.

Public Windows activation remains closed. The bounded source tests are pure/fake
observations, including injected failures and deadline returns, rather than real
Windows/API, native CAD, installed Blender or GUI qualification. The previous
Linux candidate and all earlier release archives remain unchanged.
