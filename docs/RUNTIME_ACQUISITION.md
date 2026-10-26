# Reproducible Linux runtime acquisition

This adapter realizes **runtime bytes only**, not a qualified installer, complete recipient materials, or legal clearance. It uses public HTTPS inputs and Python standard-library archive readers. It never runs archive scripts, pip installers, Debian maintainer scripts, or the downloaded interpreter. This page describes the Linux lock; a separate [Windows-target acquisition recipe](WINDOWS_RUNTIME_ACQUISITION.md) is data-only and remains natively unqualified.

Ubuntu 24.04 is the intended Linux qualification host. Bundled Expat requires GLIBC 2.36; the OCP manylinux tag alone does not establish Ubuntu 22.04 support.

## Trusted input and invocation

The reviewed, source-controlled lock is the input authority. The adapter accepts structurally valid Linux or Windows x64 target locks, not only the current six-archive Linux lock. Do not supply an unreviewed replacement lock and treat its internally consistent hashes as independent authentication. Confirm the lock's identity against the intended source commit or another separately reviewed manifest.

```sh
python scripts/acquire_release_inputs.py \
  --lock release_inputs/linux-x64/acquisition-lock.json \
  --work-root "$NEW_ACQUISITION_DIRECTORY"
```

The work root must not exist. Its parent must already exist without symlink ancestry. Downloads go to `cache/`; regular runtime output goes to `runtime/`. Success creates `runtime-inventory.json` and `acquisition-receipt.json`. There is no overwrite/delete flag. Failed attempts retain partial output without a success receipt.

After inspecting a failed attempt, a justified retry can use a new output root and the earlier archive cache read-only:

```sh
python scripts/acquire_release_inputs.py \
  --lock release_inputs/linux-x64/acquisition-lock.json \
  --download-cache "$VERIFIED_EXISTING_CACHE" \
  --work-root "$ANOTHER_NEW_ACQUISITION_DIRECTORY"
```

Every reused archive is rechecked against exact size and SHA-256 before parsing. Cache presence is not trust. No files are copied from installed host libraries, dependency resolution, private backup artifacts, or earlier runtime trees.

## Guardrails

- Strict JSON field sets, duplicate-key/nonfinite rejection, integer schema typing, and bounded input size. The original bounded lock bytes are captured once; the success receipt binds their exact digest. Changed lock bytes are refused before success outputs.
- HTTPS host allowlist applies to redirects as well as initial URLs. No credentials or executable hooks are accepted.
- At most 16 archives, 150 MB per archive, 200 MB per member, 20,000 members per archive, and 1 GB declared expansion per archive/output total. Downloads enforce their exact locked size.
- Archive checksums precede parsing. Only explicitly mapped regular members are copied under validated destination paths; archive extraction APIs never write member paths directly.
- Traversal, absolute paths, backslashes, drive/ADS syntax, reserved names, trailing dot/space ambiguity, duplicate names, selected case collisions, and file/link-parent ambiguity are refused.
- **Explicit inert PBS exception:** the current upstream terminfo data contains case aliases. Its lock allows aliases only under the unmapped `python/share/terminfo` prefix and forbids any mapped output from that prefix. No terminfo member is written. Exact duplicate paths remain rejected; all output paths retain strict collision checks.
- Unselected link aliases remain inert metadata. Selected links, sparse files, and nonregular output fail. Explicit 0644/0755 modes and every final file's size, hash, mode, and regular single-link identity are checked.
- Debian ar/data-tar parsing is data-only: no package installation, host-library copying, ELF stripping, or binary patching occurs.

A fresh private work directory is assumed. This is not a sandbox against a malicious concurrent process running as the same OS user. Preserved failures and caches are not automatically uploaded.

## Current Linux lock

The checked-in lock identifies six official public archives totaling 104,256,225 downloaded bytes. Its runtime mapping has 1,030 files totaling 481,294,639 bytes. The canonical runtime inventory SHA-256 is:

```
a0edf4bec0050a9f16de7eceb3a91cb358bda29eef1f3c6050f543aea3953a9c
```

The acquisition lock SHA-256 is:

```
a209e4a2e3f721465d77e68458a7a32802623bd4e25d4ae6c501354cd42d44de
```

Actual official-source acquisition reproduced the external runtime inventory of the frozen Linux 1.29 checkpoint byte-for-byte. The corrected adapter's complete inventory was reverified read-only; downloaded code was not executed. This is runtime-byte correspondence, not original source-to-binary build reproducibility or qualification of later project source.

## Builder handoff and remaining gates

The acquisition output is **not directly the complete input bundle** accepted by the [candidate builder](RELEASE_CANDIDATE_BUILDER.md). The builder needs exactly `runtime/`, `materials/`, and `metadata/`; the acquisition work root also contains a cache and receipts, and does not supply complete materials or a source-bound materials map.

A separately reviewed material-preparation step must provide the required source/license/provenance files, preserved historical runtime-lock bytes, exact public project-source archive, and map bound to the new source commit and all inventories. It must not silently discard inherited declarations or rewrite old evidence as new qualification. Do not feed the whole acquisition work directory to the builder or replace missing materials with an empty map.

The retained material review has 43 component records and 42 explicit issues. Missing documentary source archives are not automatically established legal violations; acquisition does not resolve build correspondence, original notices, source obligations, or all distribution conditions. Pinned upstream source acquisition may improve specific documentary coverage only after a reviewed map update. It cannot erase unrelated uncertainties.

After a complete candidate is built, the [standalone harness](STANDALONE_QUALIFICATION.md) tests the exact archive independently. Full regressions, current-source workflows, native-platform admission, and publication remain separate gates. Windows requires its own authenticated runtime inventory, DLL-origin/material review, and native-runner qualification.
