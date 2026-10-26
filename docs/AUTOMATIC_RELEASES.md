# Automatic Linux and Windows release pipeline

Implementation is staged locally and has not run on GitHub. No enabled automation,
qualified native release, legal clearance or main promotion is claimed. Existing
suite failures, absent substantive materials review and pending Windows acquisition
remain blocking inputs, not optional warnings.

`.github/workflows/release.yml` replaces the nonpublishing readiness workflow.
Its tag path runs the full suite on both OSes, assembles both target archives on
Linux, installs/writes/reopens each exact archive in three independent native
Blender processes on its target OS, admits both results, and publishes one release.
Failed matrix jobs block publication. Only the final job gets `contents: write`;
only its publish step receives the built-in token. Official actions have full
commit pins resolved from their public repositories. No additional secret is used.

Manual dispatch requires a full development commit SHA and always runs in explicit
`--candidate-only` mode. That path checks committed version/core metadata through
the exact source export, without requiring or creating a tag or main membership.
Its receipts contain `candidate_validation_only: true`; release admission rejects
them. A successful candidate can therefore be reviewed before main promotion.
Publishing requires a new tag whose exact commit is on main and a fresh run of the
strict release path. Main and tags are never changed by these tools.

## Reviewed input configuration

Before a run, maintainers must provide repository variables `RELEASE_INPUTS_URL`,
`RELEASE_INPUTS_SHA256`, `RELEASE_INPUTS_BYTES`. These pin one bounded HTTPS JSON
document. Missing variables fail the build. Both matrix jobs independently verify
the configured hash. This document has exactly this shape (placeholders are not
usable values):

```json
{
  "schema_version": 1,
  "platforms": {
    "linux-x64": {
      "prepared": {"url": "https://reviewed-host/materials.zip", "sha256": "REVIEWED_SHA256", "bytes": 1},
      "acquisition_lock": "release_inputs/linux-x64/acquisition-lock.json",
      "blender": {"url": "https://download.blender.org/REVIEWED_ARCHIVE", "sha256": "REVIEWED_SHA256", "bytes": 1},
      "blender_path": "blender-5.2.2-linux-x64/blender",
      "runtime_lock_sha256": "REVIEWED_SHA256",
      "materials_map_sha256": "REVIEWED_SHA256",
      "review_sha256": "REVIEWED_SHA256"
    },
    "windows-x64": {
      "prepared": {"url": "https://reviewed-host/windows-materials.zip", "sha256": "REVIEWED_SHA256", "bytes": 1},
      "acquisition_lock": "release_inputs/windows-x64/acquisition-lock.json",
      "blender": {"url": "https://download.blender.org/REVIEWED_ARCHIVE.zip", "sha256": "REVIEWED_SHA256", "bytes": 1},
      "blender_path": "blender-5.2.2-windows-x64/blender.exe",
      "runtime_lock_sha256": "REVIEWED_SHA256",
      "materials_map_sha256": "REVIEWED_SHA256",
      "review_sha256": "REVIEWED_SHA256"
    }
  }
}
```

Each prepared ZIP contains only `metadata/`, `materials/`, and `review.json` at
root. Metadata uses the existing candidate-builder contract, including a complete
audited runtime inventory. The materials review is the substantive trusted ledger
documented in RELEASE_MATERIALS_REVIEW.md; tools must not manufacture it. In
particular, retain all unresolved issues and account explicitly for each one.
The map must bind the exact candidate source. Updating configuration does not
rewrite maps, waive missing sources or approve distribution.

The Linux acquisition adapter supplies only runtime bytes. Integration contract
for the cloud-owned Windows adapter is
`scripts/acquire_windows_release_inputs.py: acquire(lock_path, work_root)` returning
`platform: windows-x64`, `native_execution: false`, and producing `runtime/` and
`runtime-inventory.json`. Both execute on Linux to retain Unix mode accounting;
the acquired inventory must equal the separately reviewed metadata inventory.
Until that adapter and lock are available this stage deliberately fails. A rename
or changed cloud interface requires explicit integration, never a fallback recipe.

Blender downloads are size/hash pinned. Extraction accepts only portable regular
files with finite expansion; symlinks, reparse-style entries and traversal fail.
Tests use isolated generated designs/profiles. No global preferences or user
models are accessed. Native smoke is bounded installed-package evidence, not GUI,
Undo, exhaustive workflow, or manufacturing qualification.

## Publication and uncertain outcomes

Admission binds exact source/tree/tag/version, archive hashes/sizes, build/material
inventory hashes, all retained issue dispositions, native host and three successful
native modes, and qualification script/fixture Git blob identities. Full-suite
success is enforced by workflow job dependencies, not a forgeable success flag in
the input configuration. Artifact transfers stay within the same workflow run.

The publisher verifies the existing remote tag, refuses any existing release,
creates a draft, uploads both ZIPs and admission manifest, verifies GitHub's SHA256
asset digests and exact asset set, rechecks the tag, then publishes the draft.
It never creates/moves tags, overwrites/deletes assets, or cleans up uncertain
remote state. If a write times out, one read reconciliation must prove that exact
operation completed. No write retries occur. Unconfirmed results stop the job and
retain any remote draft for explicit operator reconciliation; rerunning refuses
an existing release rather than adopting it. A tag/main change or conflicting
asset requires investigation, not an automated overwrite.

Local tests exercise admission mutations and publisher fault injection only;
they do not call GitHub or launch Blender. A successful mocked pipeline test is
not an actual Actions run or native qualification.
