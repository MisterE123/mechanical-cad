# 1.23.1 Linux development checkpoint

This checkpoint follows immutable Linux 1.22 and the undelivered 1.23.0 failed
candidate. The 1.23.0 tag/artifacts remain unchanged: actual installed GUI Restore
failed before its chooser despite passing background recovery checks. This successor
requires a separately recorded real installed GUI opt-in/Cancel/Restore observation;
its new version/tag must not be confused with that failed candidate.

This checkpoint adds optional local recovery
for unsaved Part canonical JSON and supported raw sketch intent. The preference
defaults OFF; explicit opt-in writes unencrypted local copies. Writing is
Linux/POSIX-only. Restore is explicit into a new unsaved Scene, never an overwrite
or automatic startup action. See [local recovery](LOCAL_RECOVERY.md).

The main-thread observer checks every two seconds when Blender is responsive and
CAD transactions are idle. This is best effort, not a guaranteed loss window.
The limits are 2 MiB canonical text, 8 MiB draft text, 12 MiB envelope, 32 scopes
and 128 MiB total storage, with two generations per scope. No automatic cleanup
or retention expiry is included. Assembly, unapplied repair, exceptional sketch
conflict copies and generic Blender data are not covered. Continue saving files.
The native allocator crash remains unresolved; recovery is not a crash fix or a
zero-loss guarantee. Invalid raw intent is retained without solver/display or
input authority; explicit Resume and fresh native validation are required.

## Evidence boundaries

The companion receipt identifies exact source, archive/source/runtime hashes and
checks actually completed. This document is not a passing receipt. Qualification
is limited to focused packaging/version checks, exact installed Blender 5.2.2
ordinary Part edit/Check/save/reopen, default-off/no-write, and two-process unsaved
nonempty Part plus accepted sketch and invalid raw intent capture/explicit restore.
Installed module provenance, original preservation and absent inherited authority
are checked. Any bounded actual GUI observation is reported separately; synthetic
or background execution is not GUI evidence. Native kernels remain in the sidecar.

No full inherited or boundary/history suite, exhaustive GUI/Undo, Windows 1.23.1,
manufacturing certification or zero-loss guarantee is claimed. Earlier unclassified
suite failures and temporary-storage exhaustion remain unresolved, not waived.
Historical packaging source-byte expectations are not weakened.

## Retained runtime and materials

Frozen 1.22 and all earlier artifacts/tags remain unchanged. The builder retains
all 1,030 external runtime files, modes and original lock bytes from verified Linux
1.18. Only project source and trusted bootstrap are substituted; historical
materials remain historical and exact source/license/provenance are appended.
No development virtual environment is shipped. The dependency remains
cadquery-ocp-novtk 8.0.1.1.0. Existing dependency materials/source issues remain;
no legal clearance, source correspondence or recipient rebuild is claimed.
