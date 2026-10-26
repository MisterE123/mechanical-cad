# Offline release-candidate builder

`scripts/build_release_candidate.py` produces a **candidate**, never a qualified
release. It wraps the existing offline materials builder without changing its
`UNQUALIFIED_CONTRACT_ARTIFACT` status. The receipt says `qualification: NOT_RUN`.
A separate exact-archive native qualification and release-admission step is required.
See the [standalone qualification contract](STANDALONE_QUALIFICATION.md).
The separate [materials review accounting gate](RELEASE_MATERIALS_REVIEW.md) checks
complete review coverage and exact recipient project-source archive bytes without
turning candidate construction into release admission.

## Inputs

Use a complete public repository clone, with tags and `origin/main` fetched and
verified against the intended remote before invocation. The tag must resolve to
the full supplied source SHA, and that SHA must belong to main. A stale local
remote-tracking ref is not proof of current GitHub state. The CLI performs no
network calls. It rechecks local tag/main identity after building.

Prepare an audited directory containing exactly:

```
inputs/
  runtime/                   # clean external runtime, no project src/bootstrap
  materials/                 # explicit audited source/license/provenance materials
  metadata/
    runtime-inventory.json
    materials-inventory.json
    runtime-lock.json
    materials-map.json
```

The map must already bind the exact source commit, source inventory, platform,
runtime lock, runtime inventory and materials inventory. The adapter refuses a
stale map; it does not rewrite declarations or silently replace historical project
source archives. Complete source inventory is sorted by path; each record is
`{path,size,sha256,mode}`, using exact Git blobs and executable mode. Its digest is
SHA256 of sorted-key compact JSON plus newline, matching existing builder rules.
Runtime-lock historical lineage is preserved as bytes, not forced to equal the
current package source commit. The [Linux runtime acquisition adapter](RUNTIME_ACQUISITION.md) provides only the
external runtime. Materials preparation remains a separate audited step, not
inferred from acquisition or a successful build.

Pass expected lock/map SHA256 values from the reviewed input manifest, not values
computed blindly from an untrusted downloaded bundle. No credentials, private
backups, whole-workspace dumps or unaudited inherited project archives belong in
these inputs. Input map validation proves declarations/byte correspondence, not
license sufficiency or native dependency closure.

## Invocation

Output directories must already exist, outside the repository and input tree;
output ZIP and receipt must not exist. Use a fresh directory per attempt.

```
python scripts/build_release_candidate.py \
  --source-repo CHECKOUT --source-commit FULL_40_HEX_SHA --tag v1.30.0 \
  --inputs-root AUDITED_INPUTS --platform linux-x64 \
  --runtime-lock-sha256 REVIEWED_LOCK_HASH \
  --materials-map-sha256 REVIEWED_MAP_HASH \
  --output OUTPUT/mechanical-cad-1.30.0-linux-x64-full.zip \
  --receipt OUTPUT/linux-build.json
```

`--platform windows-x64` selects the fixed Windows interpreter profile. It does
not qualify Windows. `--main-ref refs/heads/main` supports an explicitly verified
local main; default is `refs/remotes/origin/main`. Arbitrary branch refs are refused.
The version must be plain `MAJOR.MINOR.PATCH`, without leading zero or suffix,
and match project/core/tag; a prerelease can be marked as such in GitHub metadata
without inventing a package-version syntax the builder does not support.

Git blob export is independent of dirty working-tree files, `export-ignore` and
`export-subst`; Git replacement objects are disabled for identity/export checks.
No private history is bundled. Source symlinks/submodules and
special modes are refused. The complete path plan is validated before exporting:
Windows drive/ADS/reserved paths, trailing dot/space, non-NFC/control characters,
case-colliding files/directories and `.git` spellings fail before any write.
Builder modules are loaded from that exact source
snapshot, with bytecode writing disabled so the snapshot inventory stays exact.
This runs trusted tagged project build code; it is not an untrusted-code sandbox.

The adapter reads bounded strict JSON, rejects duplicate keys/nonfinite constants,
symlink/reparse ancestry and unexpected input files, and rehashes exact inventories.
It delegates namespace/mode/material validation and no-clobber publication to the
existing builder. It never executes a candidate interpreter or native dependency.

## Receipts and failure handling

Successful JSON includes:
- `schema_version: 1`, unchanged `status`, and `qualification: NOT_RUN`;
- `source_commit`, `tag`, `version`, `platform`;
- `archive` (basename only), `bytes`, `sha256`;
- source/runtime/material inventory hashes, runtime-lock/map hashes;
- explicit `unresolved_material_issue_ids`.

No timestamps, temporary directories or absolute private paths appear in this
portable receipt. Rebuilding the same immutable inputs and archive basename has
been tested to produce identical candidate bytes and receipt. Different platform
native execution has not been established by that deterministic contract test.

Receipt is exclusively reserved before builder publication. If building fails
thereafter, it records `BUILD_UNCONFIRMED` and whether a candidate exists. A denied
hard link is not retried through copying or another API. If the final candidate
exists but receipt verification/write or final ref check fails, retain both
artifacts and investigate exact bytes/state; do not blindly rerun or overwrite.
Underlying builder's private work/diagnostic paths are retained for local analysis
but are **not** automatically uploaded. A JSON-write failure can leave an empty
or partial reserved receipt; that is not success.

Bind the qualifier to the same archive and assert build `sha256/bytes` equal
qualifier `archive_sha256/archive_bytes`, plus exact source/version identity.
Neither candidate production nor installed smoke proves a full-suite pass, GUI
usability, license review, stable release eligibility or manufacturing suitability.

## Verification

Focused tests exercise the real offline materials builder with inert runtime
fixtures, actual CLI invocation, immutable Git export, Linux/Windows candidate
profiles, deterministic archives/receipts, malformed metadata, changed inventories,
extra files, symlinks, source version/tag/main mismatches, bootstrap shadowing and
publication denial/no retry. No runtime fixture is executed. Full project and
native platform gates remain separate and must retain their actual results.

The separate readiness workflow fetches full tag/main history and uses read-only
repository permission. Its action pins were resolved from official release pages:
[checkout v4.3.1](https://github.com/actions/checkout/commit/34e114876b0b11c390a56381ad16ebd13914f8d5)
and [setup-python v5.6.0](https://github.com/actions/setup-python/commit/a26af69be951a213d495a4c3e4e4022e16d87065).
This is identity verification, not a claim of full third-party action security review.
The workflow remains nonpublishing while input acquisition, native platform and
release-admission gates are incomplete.

When dispatching readiness manually, select the existing version tag as the
workflow ref (for example `gh workflow run release-readiness.yml --ref v1.30.0`).
Dispatching the default main branch intentionally fails the tag preflight. This
example is an invocation instruction, not evidence of a dispatched or passing run.
