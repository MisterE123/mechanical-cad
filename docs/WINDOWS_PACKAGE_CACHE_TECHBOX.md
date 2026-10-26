# Windows registered-package cache development

Public technical summary of historical guarded-cache development. Readiness is not child-execution or installed GUI qualification.

## Implementation and invariants

- Native `GetPackagesByPackageFamily` plus WinRT
  `ApplicationDataManager.CreateForPackageFamily(...).LocalCacheFolder` select
  the registered package cache. A trusted caller supplies the family. There is
  no embedded Codex family/path, shell invocation, environment/model override,
  registration installation, permission repair or adoption of a failed alias.
  Exactly one current-user full registration must remain unchanged during query.
- The frozen recipe retains provider kind, package family/full name, OS root and
  fixed `MechanicalCAD/r` suffix through policy copying, equality and selection
  currentness. Each cache worker requeries it before opening/creating anything;
  a changed registration/root fails closed. Retained ancestry, NTFS, DACL, full
  bundle IDs, path budgets, process/output ownership and cleanup guards remain.
- Original COM pointers, HSTRINGs and balanced WinRT apartment resources receive
  one retirement attempt. Cleanup uncertainty retains records and prevents
  another query on that provider object.
- The finite DACL validator recognizes `OWNER RIGHTS` only when the descriptor
  owner is exactly the current token user. This is CPython 3.12.10's documented
  `mkdir(0o700)` owner-relative grant. Effective/propagating full access, protection
  where required, masks/flags and rejection of all other principals remain.
  No existing ACL was changed.
- Windows reports `C:\WINDOWS` while its retained handle reports `C:\Windows`.
  Only for this OS root, retain original and canonical opens and require equal
  complete identity/metadata before using canonical ancestry. Case folding alone
  never establishes identity. Other aliases or distinct case-sensitive objects
  fail. Cache/runtime/output paths continue to require exact final paths.
- Image auditing rejects empty, malformed, failed, duplicate or oversized module
  inventories and requires interpreter, `python312.dll`, OCP and SolveSpace.
  Imported native module file/spec origins and exact extension loaders must match
  fixed private paths before mapped-image auditing or dispatch. Parent-held
  hashes/PE anchors and restricted DLL search remain intact.
- Windows fixtures now use Python 3.12.10; Linux fixtures retain 3.12.15. Native
  importer/API doubles, stable identity across duplicate handles and supplied
  Windows handle doubles replace stale assumptions. Bounded parameter IDs avoid
  Windows environment limits. POSIX-only contracts and native Linux controls
  are explicitly skipped on Windows, without disabling production validators.

## Bounded historical evidence

Focused synthetic cache, provider, preparation, runtime and ownership checks reported 1,028 passes and 17 platform-specific skips; Ruff passed. Native registered-package capture and cache preparation reached readiness with cleanup confirmed, and read-only checks passed 120 runtime anchors. These readiness checks used an intermediate candidate, not the final updated bootstrap, and do not establish successful guarded CAD execution.

Further qualification requires a matching candidate through actual child launch, image inventory, cancellation/timeouts, output identity and cleanup, followed by real Blender create/cancel, replay/export and save/reopen. Public admission and external/raw selection remain subject to the guarded qualification boundary. Historical denied filesystem operations were not retried or replaced with permission workarounds. Private artifact receipts, machine paths and executor-session details are omitted.

## Primary API contracts

- [Current-user registered packages](https://learn.microsoft.com/en-us/windows/win32/api/appmodel/nf-appmodel-getpackagesbypackagefamily).
- [CreateForPackageFamily](https://learn.microsoft.com/en-us/uwp/api/windows.management.core.applicationdatamanager.createforpackagefamily?view=winrt-26100).
- [LocalCacheFolder](https://learn.microsoft.com/en-us/uwp/api/windows.storage.applicationdata.localcachefolder?view=winrt-26100).
- [Owner Rights SID](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-special-identities-groups).
- [CPython 3.12.10 mkdir source](https://github.com/python/cpython/blob/v3.12.10/Modules/posixmodule.c#L5024-L5034).

WinRT GUIDs/vtable slots were checked against Windows SDK 10.0.26100.0
`windows.management.core.h` and `windows.storage.h`, then exercised natively.
