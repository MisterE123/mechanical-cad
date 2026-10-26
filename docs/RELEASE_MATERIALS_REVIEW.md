# Exact-source materials review accounting

`check_release_materials.py` is an offline, nonpublishing prerequisite for a
future release-admission workflow. It checks that a separately reviewed materials
ledger covers the exact source and inputs being considered. It does not decide
license obligations, grant permission, qualify native binaries, run dependencies,
or turn a candidate into a release. It is intentionally separate from the
candidate builder: incomplete candidates can still be built for investigation.

## Why this gate exists

A nonzero historical issue count is not proof of a license violation. A zero count
obtained by deleting issues is not proof of compliance either. This gate preserves
all issues in the pinned map and requires an explicit, evidence-linked review of
every component and issue. The review is a trusted input, not generated approval.
Its SHA-256 must come from the independently reviewed manifest or source commit,
not be computed blindly from an untrusted input at invocation time. The release
maintainer must establish who is authorized to substantively review that ledger;
this tool has no reviewer-identity, signature, account-role or approval service.
Possession of a self-computed hash is not evidence of authorization. Neither the
adapter nor CI may invent a review decision solely to make the gate pass.

The current Linux acquisition audit records 43 components and 42 issues. Of these,
27 describe documentary source-material absences; the rest include identity,
original-build correspondence, route and notice-scope questions. These categories
must be adjudicated individually. Existing selected routes include FreeImage GPLv3,
LibRaw LGPL2.1, FreeType FTL and slvs GPL3-or-later; old generic prose saying no
routes were selected is not a reason to overwrite the recorded choices. The
slvs classifier/source-terms conflict and LibRaw notice-scope evidence remain
separate questions. This tool supplies no real-component review or legal finding.

## Inputs and trust boundary

Use the exact public tagged-main checkout and the same audited input directory
specified in [the candidate-builder contract](RELEASE_CANDIDATE_BUILDER.md).
The tool independently exports exact Git blobs, checks tag/main/version identity,
verifies all runtime/material files and inventory hashes, and invokes the existing
strict map validator. It neither rewrites old runtime-lock lineage nor updates
map hashes to make stale inputs appear current. Metadata and review bytes are
captured once and checked unchanged before a result is returned. A fresh private
work directory is assumed; this is not a same-user hostile-process sandbox.

The reviewed ledger has exactly these top-level fields:

- `schema_version`: integer 1.
- `source_commit`, `platform`, `materials_map_sha256`: exact map identity.
- `project_source_path`: one source archive declared by the unique
  `project_package` component.
- `components`: exactly one entry for each map component, no omissions/duplicates.
- `issues`: exactly one entry for each retained issue, no omissions/duplicates.

Each component entry has exactly `id`, `selected_license_route`, `source_status`,
`notice_status`, `evidence_paths`, and `rationale`.

- The route is bounded nonempty text recording the actual selected route, including
  exceptions or alternatives when applicable. The tool does not interpret SPDX
  expressions or infer a route from a package classifier.
- Source status is `reviewed_present`, `reviewed_not_required`, or `blocked`.
  The second requires a substantive review rationale; it is not an automatic
  waiver inferred from absent files. It cannot be used for the project itself.
- Notice status is `reviewed_present` or `blocked`. Missing notices cannot be
  marked present. A present status must reference every corresponding declared
  source/notice file in that component's evidence paths.
- Evidence paths must be unique, nonempty and refer only to that component's
  inventoried source, notice or provenance files. Those bytes are verified before
  review accounting. The tool proves the references exist, not that their content
  establishes a legal proposition.

Each issue entry has exactly `id`, `disposition`, `evidence_paths`, and `rationale`.
Disposition is `blocks_distribution` or `reviewed_nonblocking`. Evidence must be
inventoried material belonging to a component linked to that issue. Nonblocking
review does not remove or rename the issue, erase the underlying historical fact,
or claim that original-build equivalence was established. If the facts cannot be
reviewed with available evidence, keep the issue blocking. Reviewed rationale and
source/notice sufficiency need independent substantive review; this script only
checks their bounded, complete accounting and identity.

## Complete recipient project source

Unlike the older opaque-source map contract, this gate also reads the selected
project-source ZIP as data and checks every member against the exact exported Git
inventory. A current source SHA in a map cannot accompany an old or reduced source
archive. Complete project source cannot be marked `reviewed_not_required`.

The source ZIP must contain only regular files at exact repository-relative paths,
without a wrapper directory or explicit directory entries. Modes must be Unix
regular-file 0644/0755 matching Git. Every member's name, size, hash and mode must
match; no missing/extra/duplicate member is accepted. Stored/deflated ZIP entries
are supported; encrypted entries, links, nonregular modes, extra fields and comments
are refused. Local headers must agree with directory names, sizes, methods, flags and CRCs
and be contiguous; DOS timestamp equality is not required.
Prefixes, gaps, trailing bytes and oversized directory metadata are refused.
The ZIP is never extracted or executed. Source path and size/count
limits are inherited from the candidate builder. A packaging preparer must create
this exact file-only archive from the source snapshot; a GitHub-generated archive
with wrapper directories is not directly this input format. Other historical
archives can remain declared evidence, but cannot substitute for this exact one.

## Invocation and result

```sh
python scripts/check_release_materials.py \
  --source-repo CHECKOUT --source-commit FULL_SHA --tag v1.30.0 \
  --inputs-root AUDITED_INPUTS --platform linux-x64 \
  --runtime-lock-sha256 REVIEWED_RUNTIME_LOCK_HASH \
  --materials-map-sha256 REVIEWED_MATERIALS_MAP_HASH \
  --review REVIEWED_LEDGER.json --review-sha256 REVIEWED_LEDGER_HASH \
  --work-parent EXISTING_PRIVATE_DIRECTORY
```

No persistent output file, candidate or release is written. A temporary exact
source snapshot is removed normally on exit. The result is deterministic JSON on
stdout, suitable for capture by a later workflow. It contains exact review/map/
inventory/archive hashes, retained issue IDs, selected routes and blocking IDs.
It never contains local paths, material contents or review rationales; selected
route labels are deliberately retained.

Exit 0 means `MATERIALS_REVIEW_RECORDED`: complete structurally valid accounting
with no declared blockers. Exit 2 means `MATERIALS_REVIEW_BLOCKED`: the complete
review still declares component or issue blockers. Exit 1 means invalid, incomplete,
stale or failed verification, with no successful accounting result. All statuses
retain `legal_clearance` and `release_admission` as `NOT_ESTABLISHED_BY_THIS_TOOL`,
and native qualification as `NOT_RUN`.

Do not publish merely because this command exits 0. A future publication workflow
must also bind the exact built archive and native-qualification receipts, run the
required source tests, and independently establish its release-admission policy.
No real release ledger, GitHub publishing workflow, Windows input inventory or
Windows qualification is supplied by this change.
