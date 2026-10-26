# Automatic Linux and Windows release pipeline

Implementation is staged locally and has not run on GitHub. No enabled automation,
qualified native release, legal clearance or main promotion is claimed. Existing
suite failures, absent substantive materials review and prepared platform inputs
remain blocking inputs, not optional warnings.

`.github/workflows/release.yml` replaces the nonpublishing readiness workflow.
Its tag path runs the full suite on Python 3.11, 3.12 and 3.13 on both OSes, matching
the supported Core workflow matrix as a direct job dependency. It assembles both target archives on
Linux, installs/writes/reopens each exact archive in three independent native
Blender processes on its target OS, admits both results, and publishes one release.
Failed matrix jobs block publication. Only the final job gets `contents: write`;
only its publish step receives the built-in token. Official actions have full
commit pins resolved from their public repositories. No additional secret is used.
Process-level Git configuration disables checkout line-ending conversion so sealed
fixtures retain exact blob bytes on Windows; no global Git setting is changed.

Before the workflow exists on default main, pushes to the exact approved branch
`techbox/release-pipeline` run the workflow definition from that pushed commit.
These pushes use its exact `GITHUB_SHA` and always select nonpublishing candidate
mode. They require neither dispatch discovery on main nor a default-branch change.
Other development branches and pull-request events are not admitted. Adding a
candidate branch requires changing both the workflow filter and source policy.
The read-only jobs run; the tag-only publisher job is skipped on candidate pushes.
Missing prepared materials/review and failing tests still block subsequent stages.

Manual dispatch, once discoverable on the default branch, requires a full
development commit SHA and always runs in explicit
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

The shared reviewed `scripts/acquire_release_inputs.py: acquire(lock_path,
work_root)` now supplies runtime bytes for both target locks. The source snapshot
065be4a adds `release_inputs/windows-x64/acquisition-lock.json`, mapping 1,050 files.
Both execute on Linux to retain Unix mode accounting. The adapter's receipt must
bind the intended platform, exact acquisition-lock hash and `native_execution:
false`; its inventory must equal the separately reviewed metadata inventory.
This integration does not establish a Windows build or native qualification.

Blender downloads are size/hash pinned. Source/materials input extraction remains
file-only: links, reparse-style entries and traversal fail. The official Linux
Blender 5.2.2 archive has a separate narrow normalization policy in
`scripts/blender_release_archive.py`. Its exact archive hash/size/URL and the exact
79-link map in `release_inputs/blender-5.2.2-linux-x64-links.json` are pinned.
Only those library-basename aliases may resolve through reviewed in-archive links
to regular members. The entire plan rejects duplicate/case-ambiguous paths,
absolute/traversing targets, missing or unreviewed aliases/members, file/link
parents, cycles, excessive depth, sparse/special members and expansion overruns
before output writes. Resolved aliases become independent regular copies with
verified target-byte hashes. No filesystem symlink or hard link is created.
Tests use isolated generated designs/profiles. No global preferences or user
models are accessed. Native smoke is bounded installed-package evidence, not GUI,
Undo, exhaustive workflow, or manufacturing qualification.

## Publication and uncertain outcomes

Admission binds exact source/tree/tag/version, archive hashes/sizes, build/material
inventory hashes, all retained issue dispositions, native host and three successful
native modes, and qualification script/fixture Git blob identities. Full-suite
success is enforced by workflow job dependencies, not a forgeable success flag in
the input configuration. Artifact transfers stay within the same workflow run.

The publisher verifies the existing remote tag, refuses any existing release or draft,
creates a draft, uploads both ZIPs and admission manifest, verifies GitHub's SHA256
asset digests and exact asset set, rechecks the tag, then publishes the draft.
It never creates/moves tags, overwrites/deletes assets, or cleans up uncertain
remote state. Draft detection uses authenticated release listing, with 100 rows
per page and at most 10 pages. A full last page, malformed response or repeated
release ID fails closed without claiming completeness. Published-release-by-tag
404 responses are never used to prove draft absence. An uncertain creation
requires exactly one draft matching the tag, run/body and exact commit, with no
assets, followed by a by-ID reread. Pre-existing drafts and ambiguous, nonempty or
other-run drafts are never adopted. If any write times out, read reconciliation
must prove that exact operation completed. No write retries occur. Unconfirmed results stop the job and
retain any remote draft for explicit operator reconciliation; rerunning refuses
an existing release rather than adopting it. A tag/main change or conflicting
asset requires investigation, not an automated overwrite.

Local tests exercise admission mutations and publisher fault injection only;
they do not call GitHub or launch Blender. A successful mocked pipeline test is
not an actual Actions run or native qualification.

## Live Windows policy and data-only Blender evidence

The fourth live runtime gate retains the sealed historical predecessor supplied
by 065be4a, while comparing current `ROOT`/`ADDON` production files. Later reviewed
symbols are pinned individually in `current_windows_policy_symbols.json` to c407
bytes, verified identical in 065be4a. They cover the finite Windows timeout default
and explicit-preference capture, retained package/cache identity fields and OS
provider dispatch, private cache security handling and read-only runtime DLL
origin helpers. Exact symbol hashes constrain these later changes rather than
adding broad method exemptions. Import multiplicity, call scope, aliases,
dynamic-name rejection and older mutation controls remain active.

On Techbox, the official Linux archive (383,295,504 bytes; SHA256
`84098912789dc450e95697c4184fb8a90acbe5111c2ba4aede3fecb57806a168`) was
verified against the official Blender 5.2.2 checksum listing and normalized as
data only. Its 6,547 members yielded 5,672 regular output files, including 79
independent alias copies totaling 511,833,496 bytes. Every alias hash matched its
resolved regular source and no filesystem links were created. Neither Blender
nor its Python/runtime was executed; this is not native Linux qualification.
