# Release material evidence — 2026-10-26

Technical evidence snapshot prepared against source commit
`dd9683492b43f74807e26c5f7ec45c8375877381`. This is **not** a materials review ledger,
legal clearance, native qualification, or release admission. No component/issue
was approved or silently closed. No production behavior changes accompany it.

## What was verified

- All **194 files** in the retained Linux material inventory matched their exact
  recorded sizes and SHA-256 hashes. This proves local byte presence, not complete
  source correspondence, notice sufficiency, or public acquisition availability.
- Linux evidence retains **43 components / 42 issues**: **27** documentary
  `missing_source_material` entries and **15** identity, route, scope or build
  questions. Neither that nonzero count nor deleting entries establishes a legal
  conclusion. No component lacks all notice paths; that is not completeness proof.
- Existing selections remain FreeImage **GPLv3 (not later)**, FreeType **FTL**,
  LibRaw **LGPL2.1**, slvs **GPL3-or-later**, and OCCT **LGPL2.1 with its exception**.
  Original alternatives and the slvs MIT-classifier/source-terms conflict remain.
- Retained Windows wheel members were inspected as data. OCP and proxy contain
  no filenames matching `license`, `copying`, `notice`, or `sbom`; slvs contains
  `slvs-3.2.dist-info/licenses/COPYING.txt`. This is a filename observation, not a
  claim that no file contains licensing text. OCP's 72 native members and slvs's
  one native member have exact byte hashes in the manifest.

## Smallest next steps, in order

1. **Bind current project source.** Generate a complete file-only source ZIP from
   the final public tagged Git snapshot, with exact Git paths, modes and bytes.
   Generate the current distribution notice using that commit and actual material
   paths. The historical notice names `5b272e6cf19dadf25df2972377de46af80944256`;
   keep historical evidence separately rather than presenting it as current.
   Follow [the review contract](../../RELEASE_MATERIALS_REVIEW.md).
2. **Complete public material recipes.** Nine exact whole-download copy mappings
   are recorded below. For the other 185 entries, acquire or reconstruct the
   source-to-material recipe before CI relies on them. These are not 185 claims
   of unavailable origins. Distro patch tar files, RapidJSON header tar files,
   combined notices and authored provenance need their own explicit recipes;
   a normalized local tar digest is not an upstream-download digest. Do not ship
   private history or redundant historical project source archives merely because
   they occur in this historical inventory.
3. **Identify Windows dependencies separately.** Obtain original conda package
   names, exact versions/build strings, recipe/patch/source and notice files, and
   original wheel repair inputs for retained DLLs. The pinned
   [OCP build action](https://raw.githubusercontent.com/CadQuery/ocp-build-system/eace4e42cfa2c162ac39bc36864534fe5f5787a6/.github/actions/build-occt-sdk/action.yml)
   uses a different Windows dependency route than Linux; it is not an original
   resolved dependency lock. DLL families include deflate, Lerc, openjph,
   sharpyuv and zstd; Linux's 43-component map cannot be copied across. The exact
   Windows generated-binding archive hash is not established here.
4. **Resolve Microsoft DLL provenance.** Separately identify CPython's
   `vcruntime140.dll` / `vcruntime140_1.dll` and OCP's renamed `msvcp140` /
   `vcomp140` bytes, their supplier versions and applicable distribution terms.
   [Microsoft's guidance](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170)
   makes redistribution conditional; presence in a public wheel is not a grant
   established by this audit. No agreements were accepted or authority inferred.
5. **Map actual CPython contributions.** Matching CPython source and embedded
   `LICENSE.txt` are already acquired under the Windows lock. The
   [official SPDX document](https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip.spdx.json)
   supplies exact constituent source candidates, but has no file list and uses
   `NOASSERTION` for constituent licensing. Do not classify unshipped Tcl/Tk/Tix
   as missing runtime source just because the package-level SBOM lists them.
6. **Review remaining facts, without artificial closure.** Preserve LibRaw's
   unrecovered original Adobe SDK notice scope, unpinned pybind11 patch identity,
   TIFF original-input uncertainty, PBS zlib/zlib-ng identity alternatives,
   proxy generated `_version.py` mismatch and source-to-binary limits. Archive
   actual proxy wheel source bytes, not a differing generated file. PBS candidates
   are pinned below; obtaining all 27 absent source archives is not automatically
   required or sufficient. Exact original build reproduction is not asserted as
   a universal additional license requirement.

A substantively authorized reviewer must assess each component and issue against
its exact platform/source/map. No review ledger is generated here. Qualification
and release-admission gates remain separate from acquisition and this report.

## Machine-readable evidence

| File | Scope |
| --- | --- |
| [linux-components.json](linux-components.json) | All 43 identities, retained 42 issue descriptions, source/notice/provenance references and selected routes |
| [linux-material-inventory.json](linux-material-inventory.json) | All 194 historical material paths, sizes, modes and SHA-256 values; nine proven-origin whole-file copy mappings |
| [linux-pbs-source-candidates.json](linux-pbs-source-candidates.json) | Ten absent-material entries with pinned candidate URLs, sizes and hashes; zlib has two alternatives, applicability unresolved |
| [windows-material-evidence.json](windows-material-evidence.json) | Exact wheel origins/hashes, native-member hashes, notice-name inspection and official CPython source candidates |

Paths beginning `licenses/` or `sources/` refer to the **historical recipient
material root**, not checked-in repository files. `linux-private` is the historical
name for packaged private ELF dependencies; it does not mean private source URLs.
Those material bytes are not included in this documentation commit. Inventory
hashes let a future acquisition compare exact bytes; they do not make a report
self-contained source delivery. Source candidate URLs/hashes are preserved from
specified upstream/retained metadata, not newly fetched archives in this pass.

The nine mappings require fresh bounded staging, exact size/hash verification,
then unchanged copying with the declared mode. They are documentary mappings,
not an executable acquisition lock. Other entries explicitly remain without a
complete recipe in this manifest. No missing URL or source hash was guessed.

## Verification boundary

This slice parsed JSON, checked counts and unique paths/IDs, matched mapped
size/hash pairs to the verified inventory, checked Windows pins against the
checked-in acquisition lock, and scanned these new files for local absolute paths,
credentials and internal identifiers. No native software, dependency builds,
archive downloads, publication or release admission was performed. Runtime tests
and the full project suite are separate; documentation checks do not substitute
for them.
