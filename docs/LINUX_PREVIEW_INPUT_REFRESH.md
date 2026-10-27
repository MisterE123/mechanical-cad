# Linux preview input source refresh (not a release)

`prepare_linux_preview_inputs.py` is a bounded, offline **preparation** step for
Linux preview candidates. It does not change the canonical two-platform release
pipeline, build a full installer, download a seed, run Blender, create a materials
review, approve compiler provenance, tag, publish, or push anything.

## Exact input and trust boundary

The only accepted seed is the private 1.30.0 Linux candidate:

- `mechanical-cad-1.30.0-linux-x64-full.zip`, 359,256,244 bytes
- SHA-256 `488703725d6523088b800ba219f634c4697d01932fe493a264323e641373cda3`
- source `8d259b577107eb4556bd2a6c16d1eca41f020c9c`

The script fixes the independently checked `PACKAGED_MATERIALS.json`, acquisition
lock, runtime inventory/lock, and historical preparation-source ZIP identities in
code. There are no caller-supplied override pins or trusted-review inputs. A new
seed requires separate review and a code change. The seed has no verified public
release URL: obtain the exact existing local file through an authorized transfer;
**do not invent a GitHub download URL**. Its earlier bounded Linux installation
checks do not qualify newly selected code, Windows, or release admission.

Use a separately verified public checkout from
`https://github.com/MisterE123/mechanical-cad.git`. Fetch/verify its public main
through the normal public Git route before invoking this offline tool. It checks
the explicit full commit, origin spelling, reachability from local `origin/main`,
a strict descendant of the seed, and project/core version agreement. **Local Git remote configuration and tracking
refs are not independent evidence that a commit was published.** The caller is
responsible for that public-source verification. It exports Git blobs and modes,
not dirty working files or `git archive` attribute transformations. Replacement objects and lazy promisor fetches are disabled; ambient `GIT_*`
overrides and global/system Git configuration are ignored. All required objects
must already be local. Git must support `--no-lazy-fetch` (checked before work);
the implementation sets the corresponding `GIT_NO_LAZY_FETCH` environment flag. Do not use an
untrusted checkout/local Git configuration.

Example, with the independently verified public main at the time of this change:

```sh
python scripts/prepare_linux_preview_inputs.py \
  --seed /absolute/path/mechanical-cad-1.30.0-linux-x64-full.zip \
  --source-repo /absolute/path/verified-public-checkout \
  --source-commit 0ccfd627a473a587891bc0efa99b1b0058c3f44c \
  --version 1.30.0 \
  --output /absolute/path/new-linux-preview-inputs
```

The destination must not exist and must be outside the source checkout. The
Linux-only implementation needs Python 3.11+ and Git, but no downloaded packages
or native runtime. It rejects symlink/reparse ancestry, nonregular files,
nonportable/aliased paths, duplicate entries, unsupported ZIP modes/flags,
ZIP64, encrypted ZIPs, comments, extra fields, gaps, overlaps and expansion
beyond fixed byte/count bounds. Both outer and nested payload ZIPs are checked;
only inventoried external runtime files are materialized. Other source archives
remain opaque data. At least 5 GiB free disk is reserved, with a capacity check
before output creation and checks while writing. A failed run retains its own
partial output and, when space permits, `PREPARATION_FAILED.json`; inspect it and
choose a genuinely new destination rather than retrying over existing evidence.
The seed and all previous output directories remain untouched.

## Output and unchanged history

The fresh directory contains:

- `source/`: exact selected Git source, with source ZIP checked by the unchanged
  `check_release_materials.verify_project_source` verifier;
- `inputs/{runtime,materials,metadata}`: the existing candidate-builder input
  layout, with exactly its four metadata files;
- `preparer-source/`: the exact preparation implementation/checker dependency
  snapshot, also packaged as an opaque ZIP under `sources/preparation/`;
- `preparation-receipt.json`: pinned inputs, derived identities and explicit
  `CANDIDATE_INPUTS_REQUIRE_REVIEW_AND_NATIVE_QUALIFICATION` status.

Only the previous current-project ZIP under `sources/project/` is omitted from
the new inputs. Its identity is recorded; the original seed is never modified.
The new complete project ZIP, commit-specific LICENSE/notices, an explicit current
source/reconstruction notice superseding named historical locators, refresh provenance
and separate preparer-source ZIP are added. All other seed material bytes/modes,
including the original preparation ZIP and same-source-only
`reconstruct_inputs.py`, remain unchanged. All 1,030 external runtime files and
the exact runtime lock/inventory lineage remain unchanged. All 42 non-project
component declarations, all 42 historical issue objects (including limitations),
all runtime bindings, and historical notices/provenance remain unchanged. The
historical runtime lock's source commit is deliberately **not** relabeled.

The generated `licenses/project/<commit>/CURRENT_SOURCE_AND_RECONSTRUCTION.md`
explicitly supersedes historical CURRENT/this-candidate claims and the old
`DISTRIBUTION_NOTICE.md`, `INTEGRATED_MATERIALS.md` and `REPRODUCE_INPUTS.md` source
locators. It distinguishes reproducing the refresh (requires the fixed seed)
from reconstructing a future built candidate using the unchanged generic
same-source helper (does not require the predecessor seed). It does not invent
that future candidate or its metadata hash.

Historical statements retain their original scope. No issue is automatically
resolved or declared nonblocking; missing historical compiler approval is not
manufactured. No trusted review ledger/hash or native qualification is generated.

## Recipient reconstruction and implementation identity

For targets such as `0ccfd627a473a587891bc0efa99b1b0058c3f44c`, the selected
project commit predates this preparer. Its project-source ZIP therefore does
**not** contain the new preparer. The separate
`sources/preparation/linux-preview-source-refresh-<inventory-sha256>.zip`
contains the exact preparer, its local checker dependencies, fixed acquisition
lock and this documentation, using repository-relative paths. The receipt and
provenance record that ZIP's SHA-256/inventory identity and, only when every
included file exactly matches local Git HEAD, the implementation commit. A null
implementation commit means an uncommitted or non-Git implementation snapshot;
the exact embedded bytes still identify it. A local implementation commit is
not a claim of public availability.

To reproduce, review and safely unpack that small source ZIP into a new tools
directory, verify its SHA-256 against the receipt, obtain the same immutable seed
and independently verified public source checkout, then invoke its
`scripts/prepare_linux_preview_inputs.py` with a new destination. It does not
need private history, the original workspace, or executable code extracted from
the seed. It imports only its own reviewed sibling validators. All these outputs
remain **private candidate inputs** until the preparation code and materials have
received substantive review and the required publication/qualification steps.

Next bounded step: review this preparer and its exact output; then use the
existing explicit `build_release_candidate.py --candidate-only` interface for
one new Linux candidate followed by exact installed/native qualification. A
separate trusted substantive materials review remains required. Automated
publishers and Windows acquisition/qualification are separate work, not enabled
by this preparer.

The public-source receipt field always says caller verification remains required
and is not established by this tool, even when an external caller has performed
that verification independently.

Reconstruction from the embedded non-Git preparer snapshot records
`implementation_git_commit: null`. Its implementation-source bytes/inventory and
selected project source can match, but this truthful provenance difference
changes the derived provenance,
materials inventory/map and receipt hashes. The reproduction contract is exact
input identities, selected source, external runtime, retained historical material
bytes and preserved historical scope;
it does **not** promise byte-identical receipts/maps across those different
implementation contexts. Always record the actual resulting hashes.
