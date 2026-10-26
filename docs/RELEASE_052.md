# 0.5.2 compatibility-safety preview candidate

This candidate adds backend compatibility checks and revocable current evidence
to the existing bounded sketch, Part and rooted-tree Assembly workflow. It does
not release arc authoring, arc profiles or result version 3. The previously
delivered 0.5.1 archives remain unchanged.

## Upgrade and recovery

Install the matching source and add-on together. Configure Blender's Project
Root and Python executable for that source and its pinned sidecar environment.
Run `scripts/verify_sidecar_install.py` with that interpreter and require the
0.5.2 identity, conservative cyclic rejection and successful acyclic control.

Every production operation now requires evidence from its own fresh backend
request. Old 0.5/0.5.1 sidecars, missing capability receipts, unexpected source
identity and substituted replies cannot authorize current results. Correct the
settings and run the operation again; there is no silent compatibility fallback.

Preference changes, load/history events and disable/re-enable revoke earlier
evidence, including changing a setting away and back. Authored documents and
recoverable drafts are preserved. Saved status fields and stale outlines do not
restore current solve, Finish, geometry-check or export authority. A fresh
successful operation is required. Drawing does not launch backend work.

An export whose write completed but whose receipt is missing or invalid remains
an unknown file outcome. Inspect the destination before an explicit retry. A
valid write receipt followed by revoked context is historical evidence only;
the software does not automatically retry or roll back exported files.

## Qualification status

The functional source at `61b59fc889b6a772cd24abc662ae0a6384543de0` passed the
complete Ruff/format/pytest suite (4,018 cases and 19,597 subtests), 45 serialized
native Blender gates and two real process-exit gates. Independent native audit
passed 117 owner-bypass checks and 67 correction checks, with exact source hashes
verified. The packaging delta contains only metadata, matching verification
expectations and documentation.

Exact 0.5.2 ZIP installation, deliberate old/mismatched backend GUI rejection,
corrected-settings recovery, Cancel/Finish, export and save/reopen review remain
required before delivery. Headless tests do not establish GUI usability. This
candidate is not yet a fully qualified release.

The bounded runtime is Blender 5.2.2 LTS on Linux x86_64 with a CPython 3.12
sidecar. Other platforms and newer Blender versions remain unqualified. Native
libraries are installed separately; they are not bundled in the add-on ZIP.
