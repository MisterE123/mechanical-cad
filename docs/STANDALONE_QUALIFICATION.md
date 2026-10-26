# Standalone candidate smoke qualification

This harness tests the **exact built extension archive**, without a source-checkout backend. It runs install, write, and read in three independent Blender processes. It does not build, download, publish, replace, or delete an installer, and its success is not general release admission.

## Build-to-test contract

1. Resolve an existing `vMAJOR.MINOR.PATCH` tag to its immutable commit and verify the commit belongs to the maintained main branch. The release coordinator—not this harness—owns these checks.
2. Build from that exact committed source and verified platform runtime/material inputs. The builder's plain version must match the tag, project/core metadata, and generated extension manifest. Versions have three numeric components with no leading zeroes, prerelease suffix, or build suffix.
3. Pass the newly built archive, the **same full source commit**, and the **same version** to this harness. Never substitute a later working tree, another platform's archive, or a historical runtime-lock source field for the package source identity.
4. Admission must compare the build receipt's exact archive SHA-256 and byte size with this harness's `archive_sha256` and `archive_bytes`. Also compare source commit, version, platform and runtime identities from the corresponding verified build. A matching filename or version alone is insufficient. This harness does not consume or authenticate a build receipt itself.
5. Preserve contract-builder status as `UNQUALIFIED_CONTRACT_ARTIFACT`; separate scoped test evidence does not rewrite that status or resolve distribution-material obligations.

The builder's receipt uses `sha256` and `bytes`; the qualifier uses `archive_sha256` and `archive_bytes`. The coordinator must compare these pairs exactly, plus `source_commit` and `version`. The builder's `platform` and runtime/material hashes remain separately admitted metadata bound to those same archive bytes. The qualifier does not infer platform from a filename. Its successful per-mode receipt includes the installed `bundle_id`.

The builder requires a pre-bound, audited materials map for the exact source/platform/inventories. The qualification step must not repair or rewrite stale map declarations.

For example, after the coordinator supplies verified values:

```sh
python scripts/qualify_standalone_candidate.py \
  --blender "$VERIFIED_BLENDER" \
  --archive "$CANDIDATE_ARCHIVE" \
  --source-commit "$TAG_COMMIT" \
  --version "$TAG_VERSION" \
  --work-root "$NEW_QUALIFICATION_DIRECTORY" \
  --timeout 300
```

The work directory must not exist. A failed attempt retains its logs and profile; use a different new directory for a justified rerun. The optional timeout is per process (default 900 seconds), not a product timeout change. No cleanup or overwrite is performed.

## Exact version and identity semantics

The current required Blender numeric tuple is `(5, 2, 2)`. Receipts use canonical `blender: "5.2.2"` and retain `blender_version_string` separately (for example, `5.2.2 LTS`). The harness does not download or authenticate the Blender executable: supply it through a separately verified acquisition gate.

`source_commit` must be the full lowercase 40-hex package source identity; it is checked against the installed `release_identity.json`. `version` must match the installed extension manifest. A preserved runtime lock may refer to an older source lineage; it is not a substitute for the current package identity. Archive, native test script, and inert fixture SHA-256/size are recorded and must remain unchanged during the run.

## Checks performed

- Only the installed `bl_ext.user_default.mechanical_cad` modules are imported. Manual project/interpreter preferences must be empty; source-addon/core and OCP/slvs imports in Blender are rejected.
- Installed executable/package files are compared with exact ZIP bytes and, on POSIX, modes. Documentary `sources/` and `licenses/` files are excluded from that installed-byte loop; their completeness remains a build/material gate.
- The bundled backend must become ready, yield the guarded bundled policy, and match every extracted backend-manifest file's size/hash and POSIX mode.
- The adjacent inert constrained-plate JSON exercises the bundled sketch solver and geometry kernel. The resulting graph has a 40 × 30 × 10 mm plate and 12000 mm³ volume; explicit geometry validation is checked before native save.
- A separate process opens the saved file. Saved geometry authority must be revoked, canonical graph must match, and fresh bundled replay must restore the expected geometry. The read phase must not overwrite the saved file.
- Each process must exit zero and emit exactly one `MCAD_STANDALONE_RESULT=` marker that agrees with its JSON receipt and requested typed identities. A crash after a success marker is a failure.

The runner clears source-backend environment overrides, creates isolated configuration/extensions/temp directories, and scopes POSIX umask 022 to each child only. Windows omits POSIX mode checks; mocked Windows launch coverage is not actual Windows qualification.

## Outputs and admission limits

The work directory contains `logs/{install,write,read}.log`, `receipts/{install,write,read}.json`, `artifacts/` (saved model/snapshot), the isolated profile, and `summary.json`. A successful summary has `ok: true` and three successful mode records. Exit codes: 0 for bounded success, 1 for execution/evidence failure, 2 for preflight refusal. Inspect the retained error and logs rather than treating a partial receipt as success.

Raw summaries contain local diagnostic paths and commands. Before public release attachment, create an explicitly allowlisted, reviewed admission record containing relevant hashes/identities/results—not an unreviewed copy of profiles, model files, private paths or all local evidence.

This is not full-suite, GUI, cross-platform, native dynamic-library-origin/closure, performance, or legal qualification. A timeout terminates the direct Blender process; independently spawned sidecar cleanup is not proven by this harness. No broad process termination is attempted. Release admission still needs the required platform regressions, source/runtime/material provenance, exact-candidate workflow coverage, and reviewed publication gates.

## Verification scope

The three-process implementation was exercised successfully against the frozen Linux 1.29 archive using Blender 5.2.2. That validates the harness on that candidate only, not a later source revision or Windows. Host tests cover malformed/duplicate/mismatched receipts, nonzero exit after a marker, timeout, isolation, immutable assets, version refusals, and POSIX/Windows command branches. No existing failure is skipped or weakened by this harness.
