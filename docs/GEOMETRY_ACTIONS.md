# Geometry checks and atomic part exports

The canonical feature document is the source of every geometry check and export.
Each action regenerates the entire current document, checks the active solid, and
uses that fresh B-rep. A Blender viewport mesh, a previous successful replay, or a
last-good display cache is never an export source.

## Scope

- One valid, positive-volume solid must be active. No active feature, a selected
  sketch, zero/multiple solids, or any failed branch blocks the action. A failed
  independent branch also blocks export when the active branch succeeded.
- All three actions check the B-rep and its tessellation. The mesh gate checks
  closed consistently oriented manifold edges, manifold vertex links, absence of
  collapsed/duplicate triangles, and positive oriented volume after numerical
  seam welding. It does not repair the canonical solid.
- `check_geometry` is read-only. It creates no export or temporary output file.
- STEP exports exact B-rep geometry; STL exports checked binary triangles. STL
  additionally checks actual encoded triangles and the maximum error introduced
  by binary32 coordinates. The independent precision ceiling is
  `min(0.00001 mm, 0.1 × linear_deflection)`.
- Coordinates are millimetres. STL has no intrinsic units: select millimetres in
  the receiving application. Neither export preserves this application's editable
  feature document; save `.mcad.json` or the scene for that history.
- Linear deflection is a finite numeric value from 0.001 through 10 mm, default
  0.1 mm. Booleans, strings, null and non-finite values are rejected.

These are geometry/mesh checks. They are **not manufacturability certification**,
structural/load analysis, wall-thickness assessment, tolerance compliance,
clearance analysis, or proof against all possible self-intersections. The adapter's
legacy method name `manufacturing_check` does not broaden these guarantees.

## Bounded schema-3 Part output candidate

The development Part owner now selects explicit result 3 for Geometry Check,
STEP and STL only on one directed arc, two radial lines using the arc's exact
center/endpoint IDs, and its sole active direct extrusion. The sketch plane must
have exact zero origin and identity quaternion; the solved radius and extrusion
height retain the 1–1000 mm domain. Every action performs a fresh solve/replay.
Nonzero DoF does not by itself reject a valid solid, and authored seeds are not
silently replaced by solved coordinates.

Profile-only/selected-profile output, arc-empty schema 3, extra consumers or
branches, other curves and arbitrary planes remain unavailable. Snapshot and
Assembly capture/update remain unavailable for schema-3 Parts. Existing result-2
behavior is retained. This owner implementation still requires native operator,
persistence and installed-package/manual-GUI qualification.

A guarded operation's exact action, options, destination spelling, selected
version, fresh nonce, backend generation and original owner must all match before
publication. A successful replay is distinct from a successful Geometry Check or
export. A valid Part may remain current after a check or writer failure while the
geometry report says FAILED.

UNKNOWN preserves uncertainty after a missing or invalid post-launch export
reply; the file may already have been replaced. OUTDATED retains a validated
historical file write when current scene/backend publication is rejected. Neither
outcome retries automatically. Inspect the selected file before deliberately
rerunning. Reopening saved reports does not restore authority: a new explicit
check/export is required. Blender Undo never reverses an exported file.

## Public helper

`mechanical_cad.actions.run_geometry_action(document, action, *, destination=None,
linear_deflection=0.1, kernel=None)` accepts a canonical `Document` snapshot. The
optional kernel parameter is a dependency-injection port for tests; no native
handle crosses the process boundary.

Actions are exactly `check_geometry`, `export_step`, and `export_stl`. Destination
is required for exports and forbidden for a read-only check. Paths are literal
filesystem paths; there is no shell or variable expansion. A relative path is
relative to the current process directory, so the Blender file selector should
supply an absolute path. Missing parent directories are not created implicitly.
The caller is responsible for explicit user file selection and any overwrite
confirmation. Merely loading a model cannot request an export.

The helper returns JSON-compatible data:

- `ok`: true only when the requested action completed.
- `result`: the full fresh replay, including failed/blocked feature diagnostics;
  null when request/document validation prevented replay.
- `action`: the requested action.
- `geometry_check`: completed B-rep/mesh checks, or null. Successful STL adds the
  `encoded_mesh` and `encoding` reports.
- `export`: null for checks and failed exports. Success includes `format`
  (`STEP`/`STL`), `destination`, `bytes`, `units` (`mm`), current `document_hash`,
  `active_feature`, `linear_deflection_mm`, and `atomic_replace` (`true`).
- `error`: null or a `code`/`message` object.

A replay can succeed while an export fails. A geometry check can complete while a
later file write or STL precision check fails. Consumers must inspect top-level
`ok` and `error`; the presence of a replay/check report alone is not success.

Validation error codes are retained. Failed feature replay returns
`regeneration_failed` plus its full per-feature diagnostics. Active-output gates
report `missing_active_feature`, `not_a_solid`, `unsupported_solid_count`, or
`invalid_solid`. Subsequent failures report `geometry_check_failed`, `export_failed`,
`export_io_error`, or `empty_export`, as applicable.

## Atomic replacement and symlinks

Native writers never receive the user's destination. After successful fresh replay
and geometry validation, the helper creates a private temporary file in the
same directory. Only a successful nonempty writer result, followed by `fsync`, is
committed with `os.replace`.

Caught kernel/writer, flush, and replacement failures preserve the prior destination
and remove the temporary file. A failed or invalid draft does not touch the
existing export. No stale or partial output is substituted silently.

If the destination is a symbolic link, successful export **replaces the link entry
with the new regular file**, rather than following the link and overwriting its
referent. The referent remains unchanged. A failed export preserves both the link
and its referent. This behavior is tested for STEP/STL success and writer failure
on Linux; platforms without symlink support skip these tests.

This is atomic replacement, not a multi-process lock or a power-loss durability
guarantee. Fatal process termination can leave an uncommitted hidden temporary
file. It does not direct partial kernel output into the prior destination. A
concurrent external replacement of the same destination is not coordinated.
Low-level kernel writer methods remain low-level APIs; this guarantee applies
when using the helper, CLI geometry/export commands, or sidecar geometry actions.

## Additive sidecar protocol 1 extension

The request's optional top-level `action` defaults to `replay`. Supported actions
are `replay`, `check_geometry`, `export_step`, and `export_stl`. Explicit export
requests require a nonempty string `destination` outside the document. Replay and
check reject the destination field even when null. Unknown fields and operations
fail; the canonical document schema is unchanged and rejects export instructions.

Example check request:

```json
{
  "protocol_version": 1,
  "action": "check_geometry",
  "document": {"...": "complete schema-1 document"},
  "options": {"linear_deflection": 0.1}
}
```

For export, choose `export_step` or `export_stl` and add the selected filesystem
`destination` at the top level. There is no operation for arbitrary code, external
commands, network access, or implicit document-driven file export.

Legacy requests and explicit `replay` retain exactly the legacy four response
keys: `protocol_version`, `ok`, `result`, `error`. New-action responses add `action`,
`geometry_check`, and `export`. An early invalid request/schema failure retains the
legacy error response shape, so those additive fields may be absent. Exit code 0
means action success; exit code 1 means failure. Always parse the response to
retain useful diagnostics from an unsuccessful replay.

The process reserves a dedicated descriptor for its one JSON response and keeps
native stdout redirected to stderr until process teardown. A temporary redirection
around the kernel call is insufficient: OCCT STEP logging can be buffered until
shutdown and otherwise append console text after the JSON. Sidecar `main` owns a
short-lived process and is not an in-process Blender API.

## CLI compatibility

Commands remain `check-geometry`, `export-step`, and `export-stl`, using the shared
helper and default 0.1 mm deflection. Check output remains the geometry-check JSON;
export output remains `Exported <path>`. Exit codes remain 0/1. Established CLI
`export_geometry_invalid` and `io_error` categories are retained for action geometry
and filesystem failures; failed replay still reports `regeneration_failed`.

The new common conservative mesh gate also applies to STEP. Earlier direct-kernel
STEP export required a valid single B-rep but did not run this mesh gate. Rejection
is preferable to claiming an unchecked geometry result passed the shared action.

Command-line entry points reserve Python/argparse stdout separately from native
logs, including delayed STEP logging. `main()` owns that short-lived process;
`main(explicit_argv)` remains available for in-process tests without redirecting
the caller's file descriptors. The `validate`, `replay`, and `set-parameter`
commands retain their existing data/output contracts. Replay JSON-file persistence
is separate from atomic geometry export.

## Regression coverage and verification limits

The real-kernel tests cover exact drilled-plate volumes; edited dimensions exported
as current STEP/STL geometry; decoded STL coordinates/manifoldness; failed/blocked
and independent branches; no active/sketch active/multiple solids; geometry-only
checks; tolerance endpoints and invalid inputs; existing-file preservation under
partial writer, fsync and replace failures; empty writer output; UTF-8/spaces in
paths; symlink destination behavior; unknown actions/fields and document-injected
export rejection; legacy protocol compatibility; and clean stdout from actual
STEP/STL subprocesses and command-line entry points.

The tested environment is Linux/CPython 3.12 with the project's pinned OCP backend.
These tests do not establish Windows/macOS behavior or native Blender GUI usability.
