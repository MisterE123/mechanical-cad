# Standalone package materials contract

`scripts/package_standalone_materials.py` is an offline build-tool wrapper around
the unchanged `package_standalone_extension.py` contract builder. It produces one
Blender Install from Disk ZIP with separately inventoried documentary materials.
Every output remains **UNQUALIFIED_CONTRACT_ARTIFACT**. It is not a release command.

For the exact reviewed candidate's source/notice index, finite component table
and remaining source-access questions, see [distribution materials](
STANDALONE_DISTRIBUTION_MATERIALS.md). For a portable caller-owned invocation,
inventory preparation and modified-runtime repack instructions, see
[rebuilding the standalone extension](REBUILD_STANDALONE.md). These are
source/modification-recipient instructions; ordinary standalone installation
remains one offline ZIP, with no extra backend installation or path setup.

The historical map's 67 unresolved declarations are mechanical coverage records,
not 67 established license duties. Preserve that map as evidence. The component
review distinguishes actual source/notice conditions, conditional distribution
choices and optional provenance work; neither document grants redistribution
clearance or changes the frozen candidate.

This implementation changes no backend, bootstrap, manifest contract, live owner,
protocol, kernel, solver, Blender preference or Windows admission behavior.
Windows real-host qualification remains deferred and closed. Synthetic packaging
or cache tests do not establish native execution or installed-package readiness.

## Required inputs and invocation

Import the build-tool module from `scripts` in a trusted build driver and call
`build_materials_extension` with keyword arguments. There is no download command,
dependency discovery, package installation or caller-supplied base-ZIP mode.

The original builder arguments remain required:

- `source_root`, `source_commit`, `source_files`
- `runtime_root`, `runtime_files`, `runtime_lock`
- `platform`, `python_path`, `destination`

The wrapper additionally requires:

- `materials_root`: existing input tree, separate from the output directory
- `materials_files`: exact inventory of every regular file under that tree
- `materials_map`: immutable, strict UTF-8 JSON bytes with the schema below
- Optional `limits=MaterialsLimits(...)`: trusted ceilings may only be reduced

The source/runtime/material inventories use the unchanged contract records:
`{"path": "relative/path", "size": 123, "sha256": "lowercase-64-hex", "mode": 420}`.
Mode 420 is octal 0644. Inventory digests are SHA-256 of UTF-8 JSON containing the
path-sorted normalized records, using `json.dumps(records, sort_keys=True,
separators=(",", ":")) + "\n"`. The exact same encoding, including the final LF,
is used for generated canonical JSON. Source Git correspondence remains an
independently reviewed prerequisite, not something the commit string proves.

All inputs are required, including the map; there is no silently partial mode.
The existing base-builder entry point and its API remain unchanged.

## Closed map schema, version 1

Every object rejects missing or unknown fields. Duplicate JSON keys, malformed
Unicode, nonfinite numbers and booleans in integer fields are rejected.

Top-level fields:

- `schema_version`: integer 1
- `source_commit`: exact lowercase 40-hex caller identity
- `platform`: exact caller `linux-x64` or `windows-x64` build identity
- `runtime_lock_sha256`: SHA-256 of the unchanged runtime-lock bytes
- `source_inventory_sha256`, `runtime_inventory_sha256`,
  `materials_inventory_sha256`: canonical inventory hashes
- `coverage_scope`: literal `external-runtime-inputs-and-declared-project-package`
- `components`: nonempty array of component objects
- `runtime_bindings`: array of runtime-path binding objects
- `unresolved_issues`: array, possibly empty, of typed unresolved-issue objects

Component fields:

- `id`: unique ASCII stable identifier matching `[A-Za-z0-9][A-Za-z0-9_.-]*`
- `kind`: `external_runtime` or `project_package`
- `name`, `declared_identity`: nonempty human-readable text
- `source_paths`, `notice_paths`, `provenance_paths`: material-path arrays
- `unresolved_issue_ids`: issue-ID array

Source references must be under `sources/`; notice references under `licenses/`.
Provenance references may use either declared material root. These are mechanical
role declarations, not judgments about the contents or legal adequacy of files.

A runtime binding has exactly `path` and nonempty `component_ids`. Every external
runtime input path must have exactly one binding. Multiple components may share a
binary, including declared static/header contributions. Bindings reference only
external-runtime components, and every such component must be used. Exactly one
project-package component declares application/backend/bootstrap/build materials
against the source commit and source inventory; it is not fake runtime ownership.

An unresolved issue has exactly `id`, `role` and `description`. Its role is
`missing_source_material`, `missing_notice_material` or `other_unresolved`.
Each empty source-path list requires a linked missing-source issue. Each empty
notice-path list separately requires a linked missing-notice issue. A generic
rebuild or permission issue does not substitute for either missing-material role.

All material and issue references must resolve, with no duplicates in a reference
list. Every supplied material and issue must be used. Shared references across
components are allowed. Component/binding/issue arrays and their reference lists
are canonically ordered in generated output; equivalent caller order does not
change the final ZIP bytes.

## Inert outer placement

The outer ZIP reserves the entire `sources/` and `licenses/` namespaces plus
`PACKAGED_MATERIALS.json` and `MATERIALS.md`. An add-on cannot supply or shadow
these names, even with alternate case or a file/directory prefix conflict.
Materials use the unchanged portable path rules, including NFC, Windows reserved
names, depth, length, case-collision and traversal rejection.

All material records must have output mode 0644. Under `sources/`, only opaque
archives with `.zip`, `.tar`, `.tar.gz`, `.tar.xz`, `.tar.bz2`, `.tgz`, `.txz`,
`.srpm` or `.src.rpm` suffixes are accepted. Archive contents are never inspected,
extracted, imported or executed. Recipes and loose source code must first be put
into a separately inventoried source archive by an authorized preparation step.

Under `licenses/`, loose Python/native import artifacts and executable suffixes
are rejected, including `.py`, `.pyw`, `.pyc`, `.pyo`, `.pth`, `.pyd`, `.so`,
`.so.*`, `.dll`, `.exe`, `.dylib`, `.com`, `.bat`, `.cmd`, `.ps1` and `.sh`.
Import-like directory components are also rejected. This is an import-surface
rule; an allowed suffix is not a claim that a file is harmless or trustworthy.

All original material bytes are preserved, including original notice/license text.
Nothing selects license alternatives, adds a license conclusion or rewrites text.
The readable index escapes caller-controlled markup and contains no generated
remote image loads or links. The JSON retains exact declared text and unresolved
items. Never execute materials merely because their package hash matches.

Material bytes and indexes never enter `payload.zip`, bundle-manifest files,
launch constants, the prepared backend cache, sidecar import paths or runtime
per-operation verification. For fixed source/runtime/lock inputs, changing only
the material bytes/map changes the outer ZIP and material record, while every
base member and the runtime bundle identity remain unchanged.

## Trusted finite limits

The wrapper reuses the unchanged inventory, path, regular-file opening, tree
enumeration and checked-stream primitives. All supplied inventories detach into
validated immutable file records before invoking the original builder.

Default ceilings:

- JSON input/canonical documents: 8 MiB; nesting depth 8
- Components: 256; unresolved issues: 1,024; runtime bindings: 50,000
- Total references across all components and bindings: 100,000
- IDs: 128 ASCII bytes; names/declared identities: 1,024 UTF-8 bytes
- Issue descriptions: 4,096 UTF-8 bytes; control characters prohibited
- Files: 50,000; one expanded file: 512 MiB; total expanded outer bytes: 2 GiB
- Portable path: 240 UTF-8 bytes and 16 components
- ZIP central-directory metadata: 16 MiB; final compressed outer ZIP: 1 GiB
- Streaming reads: at most 128 KiB; no ZIP64, multipart ZIP or ZIP comments

Map values cannot override limits. Tests may reduce ceilings, never enlarge them.
Reference validation uses keyed membership sets/maps and rejects excessive counts
before sorting; it is linear in input bytes, inventory entries and references,
apart from bounded canonical sorting. ZIP directory bounds are checked before
`ZipFile` allocates member records. Aggregate base/material/generated inventories
must fit the limits together; separate input caps are insufficient.

## Base identity, final identity and publication

The original builder is called once into a fresh internal work directory, outside
all input trees. Its returned base ZIP hash/size are verified. The wrapper bounds
and hashes every base member, checks its expected namespace/regular-file metadata
and inherited source bytes, then checked-copies the whole base ZIP into a new work
file. It appends only sorted materials and generated records. The original base
archive is never edited. Retained base bytes, final member hashes and original
metadata are rechecked. Source/runtime/material bytes are rehashed after assembly.

The following remain byte-identical: `BUILD_CONTRACT.json`, root Blender manifest,
release identity, runtime lock, bundle manifest, payload, launch constants and all
inherited add-on/license files. The old build contract describes the base artifact.

`PACKAGED_MATERIALS.json` separately binds the base ZIP hash/size, wrapper/builder/
manifest-tool hashes, canonical map, full material inventory, source/runtime/
material inventory digests, lock, commit, platform, runtime bundle ID and counts.
It carries the unqualified status and unresolved declarations. The final ZIP
hash/size appears only in the external wrapper receipt, avoiding self-hash recursion.

A complete candidate and exclusive prepublication receipt are written in retained
diagnostic work. The final destination is created once by a no-clobber hard link.
Existing files/symlinks and destination races cannot be overwritten. Unsupported
hard links, missing/extra/mutated files, stream/hash/metadata/write failures or caps
reject without publishing the wrapper destination. Diagnostic work remains.

Successful calls return `published=true`, final `sha256`/`bytes`, base identity,
material hashes/counts, runtime identity and `work_directory`. Before-link and
after-link receipts are separate files so the prepublication evidence is retained.
If after-link receipt storage raises `OSError`, the result still says
`published=true`, with `receipt_write_error` and
`receipt_phase=after_publication_receipt_write_failed`. The wrapper never retries
publication or deletes a committed destination. The internal base builder's
receipt measures the base ZIP, not the extended deliverable.

These checks address bounded inputs and ordinary mutation/corruption; they do not
create a hostile-same-user filesystem security boundary or publisher authenticity.

## Verification and remaining gates

The independent inert suite is `scripts/tests/test_standalone_package_materials.py`.
Default pytest discovery includes both `tests` and `scripts/tests`. Existing tests,
historical inverse fixtures, base builder/bootstrap and runtime contracts remain
unchanged. Tests pin their exact source identities and prohibit a live import edge
to this tool. Focused verification exercises real inert cache materialization and
rehashing, without executing the dummy interpreter or native CAD libraries.

Declared coverage and matching bytes do **not** prove complete dependency
discovery, corresponding-source equivalence, license sufficiency, copyright
ownership, redistribution rights, functional recipient rebuild/substitution,
native closure, migration, exact installed Linux qualification or Windows support.
An empty unresolved list does not grant any of those approvals. Real package
inputs/maps need independent review and their own final ZIP identity and relevant
native/installed qualification before any release admission.
