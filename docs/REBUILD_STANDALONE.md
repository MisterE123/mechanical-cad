# Rebuild or repack the standalone extension

This guide is for recipients examining or modifying the supplied source/runtime.
It documents the existing public build APIs. It is not an ordinary installation
step: the standalone installation target remains **one offline Blender extension
ZIP**, without a separate backend installation, package manager or manual paths.

All builder outputs remain **UNQUALIFIED_CONTRACT_ARTIFACT**. Redistribution
review is **OPEN**. Windows testing is deferred and public Windows admission is
**CLOSED_UNTESTED**. The example below prepares a Linux x64 artifact; accepting a
Windows platform label in an API would not qualify Windows execution. This guide
does not supply the still-unverified native source/patch sets or claim a completed
modified-library test. See [the exact materials and remaining facts](
STANDALONE_DISTRIBUTION_MATERIALS.md).

## What the public builders do

- `scripts/package_standalone_extension.py` exports
  `build_contract_extension(...)`. It accepts explicit project/runtime roots,
  inventories and runtime-lock bytes, and emits a new offline extension ZIP.
- `scripts/package_standalone_materials.py` exports
  `build_materials_extension(...)`. It takes the same inputs plus a separate
  materials tree, inventory and strict map. It invokes the base builder itself
  and appends inert source/notices. It does not accept a prebuilt base ZIP.
- Both are Python APIs, not command-line release tools. They do not download
  dependencies, compile native libraries or execute the candidate interpreter.
  Building does execute the trusted project bootstrap's build-time factory, so
  inspect and trust the project source before invoking the API.
- The builders regenerate bundle manifests, payload hashes, release identity and
  `standalone_launch_constants.py`. No publisher signing key, remote authorization
  service or secret is required by that mechanism. Hashes prove consistency,
  not publisher authenticity or distribution rights.

Historical `candidate-staging-tools.tar` is supporting evidence, not the recipe
below. Its `build_candidate.py` expects an internal `BUILD_PACKET.json` that is
not supplied, and its recovery script contains historical fixed paths. Do not
invent that packet or treat those scripts as a required recipient dependency.

## Prepare distinct input trees

Use a trusted host Python 3.11 or newer for the build tools. This host Python is
a developer tool, separate from the bundled runtime and from ordinary end-user
installation. The unchanged runtime profile specifically requires CPython
**3.12.15**, normal-GIL `cp312`, 64-bit, and the expected platform layout.

Choose your own working directory and use this layout (names are illustrative):

```text
work/
  source/                     exported, verified project source snapshot
  runtime-modified/           distinct external-runtime input tree
  materials/                 sources/ and licenses/ only
  original-package/          read-only inspection of the original outer ZIP
  inputs/                    caller description and reviewed map
  output/                    new archives and builder diagnostics
  build-recipient.py          the driver below, outside all input trees
```

1. Preserve the original ZIP, source archive, receipts, lock and inventories.
   For the reviewed reference, verify its size/SHA-256 from the distribution
   guide. Safely unpack only expected relative regular-file archive members; do
   not follow symlinks, traversal paths or executable archive hooks.
2. Export the project source into `source/`, without `.git`, virtual environments,
   caches or generated build outputs. Verify it against the supplied project
   inventory. For modified project source, record a real new source commit and
   independently verify the exported tree against that commit. Passing a valid
   40-hex string to the builder does not prove Git correspondence. For an
   unchanged source snapshot, retain its verified original commit.
3. Read `release_identity.json` to locate the nested payload and its manifest.
   Use `licenses/provenance/runtime-inventory.json` to select the **external
   runtime inputs** into `runtime-modified/`, preserving their recorded modes.
   Do not copy the payload's generated `bootstrap.py` or `src/` into this tree;
   the builder adds them from the selected project source. The payload inventory
   and external-runtime inventory have different scopes. The interpreter must
   remain at `python/bin/python3.12`, with inventory mode 0755 on Linux.
4. Make intended library changes in `runtime-modified/`, never in a published
   cache or the original runtime tree. Obtain the corresponding source, patches,
   configuration and necessary build/install instructions for the library being
   changed. The five unresolved source-access sets in the distribution guide
   remain unresolved; a version-matching tarball alone does not settle them.
5. Prepare a separate `materials/` tree. Preserve original upstream terms and
   evidence. Add the corresponding changed source, patches, build instructions,
   appropriate change notices and updated attribution. For changed project
   source, include its matching source archive and identity; do not label the
   historical project archive as the source of a new revision. Source materials
   must be allowed opaque archives under `sources/`; loose readable notices and
   provenance belong under `licenses/`. Every material has output mode 0644.
6. Put an honest change description in `inputs/runtime-description.json`. Include
   base component identities, actual changed files, source/patch hashes, build
   instructions/options, supported ABI/host assumptions and what validation has
   or has not run. This is caller-authored provenance, not a permission token.
7. Start `inputs/materials-map.reviewed.json` from the original
   `PACKAGED_MATERIALS.json`'s `materials_map` object, or author a complete map
   using [the schema](STANDALONE_PACKAGE_MATERIALS.md). Reconcile component
   identities, source/notice/provenance paths, runtime bindings and unresolved
   facts against your new inputs. Each external runtime path needs exactly one
   binding, which may name multiple contributors. Keep historical declarations
   in the original evidence; do not erase a remaining fact merely to pass a check.

Inventory records are exact relative path, byte size, lowercase SHA-256 and output
mode (0644 = 420, 0755 = 493). The portable path rules reject ambiguous spellings,
case collisions, special files and symlink/reparse inputs. Restore executable
modes from the supplied inventory if an archive extractor did not preserve them.
Freeze input trees before inventorying and do not mutate them during the build.

## Linux ABI and native replacement checks

The existing Linux profile targets Debian 13 x86_64 / Blender 5.2.2. Its private
Expat has a GLIBC_2.36 floor; this is not a generic manylinux guarantee. Blender,
the system loader/C/C++ libraries and normal OS graphics stack remain host
prerequisites. Do not substitute a different CPython ABI/version or expand the
supported-host claim merely because packaging succeeds.

For a modified OCCT, LibRaw or other native library, inspect exports, required
symbols, C++ ABI, architecture and dependency closure. Wheel-repaired libraries
can use auditwheel-hashed filenames and SONAMEs, with matching `DT_NEEDED` entries
in their consumers. A replacement is not made compatible by changing its filename.
Either preserve the ABI and expected SONAME/dependency names accurately, or
rebuild/update affected dependants and their recorded dependencies consistently.
Account for `RPATH`/`RUNPATH` and the child's existing native search policy.
Record all changed bytes and source/build inputs. Do not weaken isolation,
per-operation receipts, capability checks, manifest validation or cache hashes.

The unchanged consumer rehashes its runtime before launch. Hot-swapping a cached
library should fail. The supported modification mechanism is a **new artifact
with regenerated integrity identities**. Bundle ID is derived from source commit,
runtime-lock SHA-256 and platform; it does not directly include the runtime file
inventory. Therefore a changed runtime requires a distinct truthful lock as well
as refreshed file hashes. Reusing the old lock with new runtime bytes risks an
identity/cache collision and misrepresents the old qualification evidence.

## Portable caller-owned driver

Save the following as `work/build-recipient.py`. Run it from `work/` with
`python3 -B build-recipient.py VERIFIED_SOURCE_COMMIT`, replacing the final
argument with the real 40-character commit verified in step 2. The `-B` flag keeps
imports from adding bytecode to the frozen source tree. The description/map files
must already be complete and reviewed; the driver refreshes identity hashes, not
component ownership or legal conclusions. It uses only the standard library and
the supplied public builder. Do not run it against untrusted input trees.

```python
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

source_root = Path("source").absolute()
runtime_root = Path("runtime-modified").absolute()
materials_root = Path("materials").absolute()
output = Path("output").absolute()
source_commit = sys.argv[1]
if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
    raise ValueError("Supply the independently verified source commit")
platform = "linux-x64"
python_path = "python/bin/python3.12"


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root, *, documentary=False):
    records = []
    for parent, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            path = Path(parent) / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError(f"Link/reparse input: {path}")
            if stat.S_ISDIR(info.st_mode):
                continue
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f"Special input: {path}")
            sha = hashlib.sha256()
            size = 0
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(128 * 1024), b""):
                    size += len(chunk)
                    sha.update(chunk)
            mode = 0o644 if documentary or not info.st_mode & 0o111 else 0o755
            records.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size": size,
                    "sha256": sha.hexdigest(),
                    "mode": mode,
                }
            )
    return sorted(records, key=lambda record: record["path"])


source_files = inventory(source_root)
runtime_files = inventory(runtime_root)
materials_files = inventory(materials_root, documentary=True)
description = json.loads(Path("inputs/runtime-description.json").read_bytes())
if type(description) is not dict or not description:
    raise ValueError("Provide the actual runtime/source/build/change description")
parent_lock = Path("original-package/runtime-lock.json").read_bytes()
runtime_lock = canonical(
    {
        "schema": "recipient-repack-lock/1",
        "status": "UNQUALIFIED_RECIPIENT_REPACK",
        "source_commit": source_commit,
        "platform": platform,
        "python_path": python_path,
        "python_version": "3.12.15",
        "parent_runtime_lock_sha256": digest(parent_lock),
        "runtime_inventory_sha256": digest(canonical(runtime_files)),
        "description": description,
    }
)
if runtime_lock == parent_lock:
    raise ValueError("Modified runtime must have a distinct truthful lock")
materials_map = json.loads(Path("inputs/materials-map.reviewed.json").read_bytes())
materials_map.update(
    {
        "source_commit": source_commit,
        "platform": platform,
        "runtime_lock_sha256": digest(runtime_lock),
        "source_inventory_sha256": digest(canonical(source_files)),
        "runtime_inventory_sha256": digest(canonical(runtime_files)),
        "materials_inventory_sha256": digest(canonical(materials_files)),
    }
)
output.mkdir(exist_ok=True)
sys.path.insert(0, str(source_root / "scripts"))
from package_standalone_materials import build_materials_extension

receipt = build_materials_extension(
    source_root=source_root,
    source_commit=source_commit,
    source_files=source_files,
    runtime_root=runtime_root,
    runtime_files=runtime_files,
    runtime_lock=runtime_lock,
    platform=platform,
    python_path=python_path,
    destination=output / "mechanical-cad-recipient-linux-x64.zip",
    materials_root=materials_root,
    materials_files=materials_files,
    materials_map=canonical(materials_map),
)
print(json.dumps(receipt, indent=2, sort_keys=True))
```

The lock is a caller-owned, bounded byte document. The builder hashes it; it does
not require the historical internal lock's schema or validate its factual claims.
The example deliberately labels its replacement lock unqualified and references
the unchanged parent's lock by hash. Do not copy historic pass/rights claims into
the new description. Make any current provenance copies inside `materials/`
accurate too; clearly label retained original inventories/locks as historical.
Avoid circular hashes: the runtime lock can bind the runtime inventory, but a
materials inventory cannot contain its own final hash.

The materials wrapper checks the map's closed schema, complete references and
bounded inventories. It rejects unreferenced material, missing bindings, path
collisions and mutated input bytes. The driver above does not replace those
checks or automatically discover third-party contributions. Canonical inventory
hashing uses sorted records, `sort_keys=True`, separators `(",", ":")` and a final
LF, as in the [materials contract](STANDALONE_PACKAGE_MATERIALS.md).

For a base contract artifact without outer documentary material, import
`build_contract_extension` from `package_standalone_extension` and call it with
the same source/runtime/platform/destination arguments, omitting the three
`materials_*` arguments. That variant does not establish distribution readiness
and does not replace applicable source/notice delivery. Ordinary final delivery
remains a complete single ZIP.

## Verify the new artifact separately

The output directory must be outside all input trees, on a filesystem supporting
the builders' no-clobber hard-link publication. The destination must not exist;
use a new filename for a new attempt. Do not delete or overwrite the original
archive to make a retry work. Input/output size, path and streaming limits are
documented in the materials contract; do not increase them to bypass rejection.

Read the returned `published`, final SHA-256/size, work-directory and receipt-phase
fields. A post-publication receipt-storage error can occur after publication;
inspect the existing output before any retry. Keep both the receipt and exact
new archive identity. The wrapper's base receipt measures its internal base ZIP,
not the larger materials ZIP. Compare retained original evidence separately.

Verify every new member against the generated inventories; confirm the new lock,
bundle ID, payload hash, release identity and launch constants agree. Perform
pure/inert contract checks before any separately authorized native validation.
Then qualify the exact modified artifact: native load/dependency origins,
compatible-library use, ordinary offline install/enable/first operation and
relevant failure/recovery behavior. Install as a distinct artifact using normal
Blender extension handling; do not try to enable two conflicting Mechanical CAD
owners or patch an active cache. A new package does not inherit old native or GUI
qualification merely because only one library or a notice changed.

For LGPL-covered components, assess the complete source plus usable repack or
relink mechanism against an applicable section 6 option. Section 6(b) is not
mandatory; section 6(a), if used, needs its required machine-readable work/object
and other relink materials. This guide does not claim that supplying an API alone
fulfills all conditions. Missing necessary source/scripts or an ABI failure are
concrete remaining work; inability to reproduce the original compiler's identical
machine code is not a separate blanket requirement.
