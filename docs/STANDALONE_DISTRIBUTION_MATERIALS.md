# Standalone distribution materials and remaining facts

This is a finite documentary review of the Linux standalone candidate, dated
2026-10-19. It identifies supplied materials and remaining work; it is not legal
clearance, a new license grant, a license election or a release approval.
Redistribution rights review remains **OPEN**. Windows real-host testing is
deferred; public Windows admission remains **CLOSED_UNTESTED**. Bounded Linux
native and actual-GUI evidence does not close those separate gates.

The ordinary installation target is one self-contained Blender Install from Disk
ZIP with automatic offline backend preparation. The files described here are
source, attribution and modification materials for recipients, not a requirement
to install another backend, Python environment or package manager.

## Exact reference package and scope

- Source: `9a5a5581f1d5980f072da239301827361da8433a`.
- Archive: `mechanical-cad-0.6.0-9a5a558-linux-x64-INTERNAL-RIGHTS-INCOMPLETE.zip`.
- Size: **162,415,859 bytes**.
- SHA-256: `d1150809b64c73152aa4f1c9f1a8949ba2acd3e2220eade5c90ac9c3cde31ab0`.
- Materials-map SHA-256:
  `10e7ac6f3523967cb5659750c6173eac002a0ad4cbcd4cadf7c72da11fb311cf`.

The reviewed map declares 43 components, 1,030 external runtime input files and
65 material files. Those runtime and material hashes/sizes were checked against
the actual nested payload and outer archive. The project source archive's 1,260
regular files matched its frozen source inventory. These facts establish which
bytes were reviewed, not their legal sufficiency or complete unknown static-code
coverage. This document is a later documentary correction; it has not been added
retroactively to the frozen archive or its source. Prior archives stay unchanged.

Paths below are relative to the outer ZIP unless an archive-member path is
explicitly stated. `MATERIALS.md` is the readable generated index.
`PACKAGED_MATERIALS.json` contains the exact materials map and material inventory;
it records declared coverage, not a clearance decision. Keep the original license
texts, publisher metadata and provenance records unchanged when preparing a
reviewed successor, and distinguish any added explanation from upstream terms.

### Coverage records versus obligations

The strict map requires a `missing_source_material` issue for an empty source
list and a `missing_notice_material` issue for an empty notice list, regardless
of the component's license. Its 67 historical unresolved declarations are not
automatically 67 legal defects. In particular, MIT/BSD/Apache/Zlib source archives
are not universally required for binary distribution. Applicable attribution,
modification notices and cross-component conditions still matter.

Required source access means usable access to the actual required source,
relevant modifications, interface definitions and necessary build/install scripts
through a permitted distribution option. It does not universally require every
source archive inside this extension ZIP. GPLv3 section 6(d) and LGPL-2.1 section 4
have qualifying network-access options; a generic homepage is not an exact
source-access arrangement. Original CI, the original compiler and bit-identical
output are separate provenance goals, not blanket requirements of these terms.
A genuinely necessary missing build script is still substantive source work.

## Index of existing source and notice material

### Source archives

| Existing outer member | Contents and limits |
| --- | --- |
| `sources/project/mechanical-cad-9a5a5581f1d5980f072da239301827361da8433a.zip` | Frozen application, backend, bootstrap, public builders, tests, documentation and asset sources. SHA-256 `31a40b22adb7cf3668db3ecd44738603410c3f8dbf82ae83c451cfaf499c90cd`. |
| `sources/slvs/slvs-3.2.tar.gz` | Complete supplied slvs sdist, including C/C++, Cython, CMake, Eigen and mimalloc. SHA-256 `cf7c00fb17a2d100df7cfa80db5e04c7ec16e6093b3d9a74402f001043550a9b`. |
| `sources/occt/OCCT-b8f597c677811d1f9f4d8a97f5ae2825c0353a42.tar.gz` | Full retained upstream OCCT commit; actual wheel patch/source correspondence remains open. |
| `sources/linux-private/expat_2.9.0.orig.tar.gz` and `expat_2.9.0-1~deb13u1.debian.tar.xz` in the same directory | Expat upstream and Debian patch source. |
| `sources/linux-private/zlib_1.3.dfsg+really1.3.1.orig.tar.gz` and `zlib_1.3.dfsg+really1.3.1-1.debian.tar.xz` in the same directory | zlib upstream and Debian patch source. |
| `sources/build-evidence/ocp-selected-recipes-eace4e42.tar` | Selected OCP/OCCT workflows, no-VTK patch, CMake-order patch and proxy source; not all original wheel build inputs. |
| `sources/build-evidence/pbs-selected-recipes-20261013.tar` | Selected PBS recipes, target/module declarations, download pins and MPL license; not complete DB/CPython modified-source delivery. |
| `sources/build-evidence/candidate-staging-tools.tar` | Historical staging tools. One expects an absent internal `BUILD_PACKET.json`; the recovery tool uses historical fixed paths. Neither is the portable recipient recipe. Use [the public builder guide](REBUILD_STANDALONE.md). |

### Detached notices and provenance

- `licenses/project/`: `LICENSE`, historical `THIRD_PARTY_NOTICES.md`,
  `icons-Apache-2.0.txt`, `icons-GPL-3.0-or-later.txt`, `icons-NOTICE.txt` and
  `palette-shapes-NOTICE.txt`. The historical notice's no-binaries claim is stale
  for standalone packaging; the corrected repository notice distinguishes the
  legacy add-on from the standalone candidate.
- `licenses/occt/`: `LICENSE_LGPL_21.txt`, `OCCT_LGPL_EXCEPTION.txt` and
  `dox/license.md`. `licenses/ocp/`: `OCP-8.0.1.1-LICENSE.txt` and
  `build-system-LICENSE.txt`.
- `licenses/slvs/`: `COPYING.txt`, `source-README.md`, `mimalloc-LICENSE.txt`.
  `licenses/slvs/eigen/`: `COPYING.APACHE`, `COPYING.GPL`, `COPYING.LGPL`,
  `COPYING.MINPACK`, `COPYING.MPL2`, `COPYING.README`, `Eigen_Colamd.h.txt`.
- `licenses/python/`: `CPython-LICENSE.txt`, `runtime-LICENSE.txt`,
  `PBS-LICENSE.txt` and supplier `LICENSE.*.txt` notices for `bdb`, `bzip2`,
  `expat`, `libedit`, `libffi`, `liblzma`, `libuuid`, `mpdecimal`, `ncurses`,
  `openssl-1.1`, `openssl-3`, `sqlite`, `zlib-ng` and `zlib`. Retaining an old
  OpenSSL notice does not declare that OpenSSL 1.1 is the shipped library.
- `licenses/linux-private/`: `private-expat-debian-copyright.txt` and
  `private-zlib-debian-copyright.txt`. Exact Expat 2.9.0 upstream attribution is
  also in `sources/linux-private/expat_2.9.0.orig.tar.gz`, member
  `libexpat-R_2_9_0/expat/COPYING`; use it to supplement the older detached notices.
- `licenses/provenance/`: `project-source-freeze.json`,
  `project-source-inventory.json`, `runtime-inventory.json`, `runtime-lock.json`,
  `runtime-file-provenance.json`, `runtime-static-elf.json`,
  `pbs-declared-source-pins.json`, `pbs-linux-PYTHON.json`,
  `linux-ocp-declared-components.json`, `slvs-PKG-INFO.txt`,
  `restored-source-summary.json`, `source-analysis-scope-001.json` and
  `source-analysis-scope-002.json`. Its `linux-private/` subdirectory contains
  `expat_2.9.0-1~deb13u1.dsc` and `zlib_1.3.dfsg+really1.3.1-1.dsc`.
  Provenance is evidence of declarations and inputs, not replacement license text.

### Additional solver notices already inside the sdist

The following member paths start under `slvs-3.2/extlib/eigen/` inside
`sources/slvs/slvs-3.2.tar.gz`. Preserve the actual headers and notices.

| Member | Notice scope |
| --- | --- |
| `Eigen/src/OrderingMethods/Eigen_Colamd.h` | MPL adaptation plus University of Florida 1998–2003 COLAMD grant, disclaimer and original-version availability; also detached in the notice index above. |
| `Eigen/src/SparseCore/SparseColEtree.h` | MPL adaptation of SuperLU elimination-tree code, with Xerox 1994 permission and modification notice. This is not a claim that the full SuperLU library is shipped. |
| `Eigen/src/Core/arch/Default/BFloat16.h` | TensorFlow 2017 Apache-2.0 attribution; the Apache text is supplied. Header inclusion does not establish template instantiation. |
| `Eigen/src/Core/arch/Default/Half.h` | MPL header with Fabian Giesen's 2016 permissive conversion notice; preserve its source notice. |
| `Eigen/src/Core/util/MKL_support.h` and `Eigen/src/Core/products/*_BLAS.h` | Applicable Intel BSD-style notices. Some paths are conditional; this does not establish that Intel MKL or all BLAS implementations are linked. |

A conservative include review did not identify a solver-path LGPL Eigen module.
Unused LGPL/MINPACK material in the complete source archive is not evidence that
it is linked; preserve its notices without inventing a relink obligation from a
license filename alone.

## Finite component table

Each of the 43 map IDs occurs once below. Versions are supplied declarations,
not a guarantee of native source equivalence. “No general source duty” refers
only to the identified component's own terms; a concrete combined-work or chosen
relink route can require additional material. A notice marked “missing” remains
to be supplied or reconciled; listing its name here does not supply its text.

### Project, solver and principal runtime

| Map ID / declared component | Terms and actual distribution conditions | Supplied material / remaining fact |
| --- | --- | --- |
| `project` / Mechanical CAD | GPL-3.0-or-later: retain notices, GPL and applicable change notices; provide Corresponding Source under an applicable option. | Full frozen source and asset sources/notices supplied. This revision corrects stale packaging prose; portable repack instructions are supplied separately. Source/installation usability still requires validation. |
| `proxy` / cadquery-ocp-proxy 8.0.1.1.0 | Apache-2.0: license, applicable NOTICE and change notices; no general source-archive duty. | Apache text and the actual readable runtime Python source supplied. Historical recipe version differs; separate version-generation reconstruction is provenance work. |
| `slvs` / slvs 3.2, SolveSpace | Combined solver GPL-3.0-or-later; publisher MIT classifier does not override linked GPL code. | Complete sdist and GPL text supplied. Four source/metadata texts match the wheel; independent native source-to-binary correspondence is not proved and undisclosed patches are not excluded. No identified missing solver archive. |
| `slvs-eigen` / declared Eigen 3.4.0 vendor tree | MPL-2.0 covered-file source access/directions plus applicable header terms; compatible larger-work terms preserve MPL source rights. | Full vendor source, license texts and header notices supplied; readable header index above. No claim every optional module is linked. |
| `slvs-colamd` / Eigen COLAMD adaptation | MPL plus University of Florida grant; keep copyright, conditions, disclaimer and original-version availability accessible. | Full header source and detached `Eigen_Colamd.h.txt` supplied. |
| `slvs-mimalloc` / declared 2.2.2 | MIT copyright/permission notice; no independent source/relink duty. | MIT notice and full vendor source supplied. Retained CMake version establishes 2.2.2 beyond the historical map's header-only uncertainty. |
| `cpython-pbs` / CPython 3.12.15, PBS 20261013 | Python license stack and acknowledgements; brief summary of distributor changes. MPL applies to the supplied PBS covered recipe source, not automatically its output. | Python/PBS notices and selected recipe source supplied; `crypt.py`/`_crypt` exclusion documented. DB source-access scope is separate below. |
| `ocp` / cadquery-ocp-novtk 8.0.1.1.0 | Apache-2.0 and incorporated-header notices; prominent OCCT-use notice. No general Apache generated-source duty. | OCP/build-system texts supplied. Reconcile applicable NOTICE/change labels and pybind11/fmt/RapidJSON credits. OCP source/object material may be needed for a selected OCCT relink option. |
| `occt` / 51 libraries labelled 8.0.1 | LGPL-2.1 with OCCT exception: corresponding library source/access, notice, modification/debugging permissions and applicable section 6 route. | Upstream source, LGPL, exception and selected patch/recipe supplied. Actual modified-source/build correspondence, RapidJSON attribution/inputs and end-to-end compatible replacement remain open. |

### OCP-wheel dependencies

| Map ID / declared component | Terms and actual distribution conditions | Supplied material / remaining fact |
| --- | --- | --- |
| `ocp-bzip2-libs` / 1.0.6-28.el8_10 | bzip2 terms: source notices/change marking, truthful origin, no unauthorized endorsement; no binary-only notice or source-offer duty identified. | Empty map notice/source lists are not themselves binary-distribution violations. |
| `ocp-fmt` / 6.2.1-1.el8 | MIT with a compiled-portion exception whose applicability to this copied shared library is not established. | Applicable notice missing; include it or establish the exact exception applies. No general source duty. |
| `ocp-fontconfig` / 2.13.1-4.el8 | MIT-style notice and restrictions on promotional use of names. | Exact applicable holder/permission notice missing; no general source duty. |
| `ocp-freeimage` / 3.17.0-5.el8 | Upstream offers GPLv2, GPLv3 or FIPL; exact distro grant/patch coverage unverified. Codec terms remain separate. | Actual grant, applicable notices/acknowledgement, patches/build inputs and usable source route open. No license election; see the five source-access sets below. |
| `ocp-freetype` / 2.9.1-10.el8_10 | FTL or GPL-2.0-or-later; applicable subcomponent terms remain. FTL needs FreeType credit and source conditions; GPL choice brings its source duties. | Credit and applicable BDF/PCF/fthash/gzip notices need selection. This document does not elect a route or require all FreeType source under the FTL route. |
| `ocp-ilmbase` / 2.2.0-13.el8 | BSD-3-Clause binary notices and no endorsement; no general source duty. | Applicable notice missing for five retained shared libraries. |
| `ocp-jasper-libs` / 2.0.14-6.el8_10 | JasPer-2.0 notice and no-endorsement conditions; no general source duty. | Exact applicable release/distro notice missing; an older author-hosted notice does not settle attribution. |
| `ocp-jxrlib` / 1.1-1.el8 | Provisionally BSD-2-Clause binary-notice conditions. | Exact official-origin holder/grant binding and notices for libjpegxr/libjxrglue remain unverified; do not replace them with a generic template or unverified mirror. |
| `ocp-lcms2` / 2.9-2.el8 | MIT notice; no general source duty. | Applicable Little CMS notice missing. |
| `ocp-libgomp` / 8.5.0-29.el8_10.alma.1 | GPL-3.0-or-later with GCC Runtime Library Exception 3.1; distributing the library itself still needs corresponding source. | GPL text already supplied elsewhere. Component copyright/exception, actual source/patches/scripts and source-access arrangement remain open. |
| `ocp-libjpeg-turbo` / 1.5.3-14.el8_10 | IJG for libjpeg, Zlib for SIMD; BSD-3-Clause additionally if TurboJPEG API code is included. | IJG acknowledgement missing. Only libjpeg ELF mapped; do not infer TurboJPEG API inclusion. No general source duty under these terms. |
| `ocp-libpng` / 1.6.34-11.el8_10 | Version-specific Libpng terms: truthful origin, altered-version marking, source notice retention. | No binary-only notice/source duty identified; empty map lists alone are not violations. Review other contributions only when identified. |
| `ocp-libraw` / 0.19.5-6.el8_10 | LGPL-2.1 or CDDL-1.0, plus applicable DCB/FBDD, X3F and Adobe DNG notices. Both main routes require covered-source access. | Actual patches/source-access route, main and third-party notices unresolved. LGPL route also needs an applicable modification/relink option; CDDL has separate combination questions. No election here. |
| `ocp-libuuid` / util-linux 2.32.1-48.el8_10 | libuuid-specific BSD-3-Clause, not aggregate util-linux GPL; binary notices/no endorsement. | Exact holder/version notice missing. Separate identity from PBS uuid. |
| `ocp-libwebp` / 1.0.0-11.el8_10 | BSD-3-Clause binary notices/no endorsement; no general source duty. | Applicable notice missing for both retained libraries. |
| `ocp-openexr-libs` / 2.2.0-12.el8_10.1 | BSD-3-Clause binary notices/no endorsement; no general source duty. | Applicable OpenEXR notice missing. |
| `ocp-openjpeg2` / 2.4.0-5.el8 | BSD-2-Clause binary notices; no general source duty. | Applicable OpenJPEG notice missing; terms do not grant other parties' patent rights. |
| `ocp-pybind11` / recipe 2.13.* | BSD-3-Clause binary notices, including compiled header contributions. | Applicable notice missing and exact patch version unpinned; source-build reconstruction is not an independent BSD duty. |
| `ocp-tiff` / historical 4.0.9; libtiff-92a88e40.so.5.3.0 | libtiff permissive notice and promotional-name conditions; no general source duty. | Exact source/patch identity and applicable notice unresolved. No direct JBIG dependency was observed; this does not exclude static/plugin inclusion. |
| `ocp-xz-libs` / 5.2.4-4.el8_6 | XZ's liblzma component is public domain; utility/build-script GPL terms do not automatically attach. | No own-license binary notice/source duty identified. Concrete separately incorporated code would require its own review. |

### Python contributions and private libraries

| Map ID / declared component | Terms and actual distribution conditions | Supplied material / remaining fact |
| --- | --- | --- |
| `pbs-bdb` / Berkeley DB 6.0.19 | Sleepycat plus retained notices: binary notices and source-obtainment information for DB and accompanying software using it. | Notice supplied; PBS metadata binds static DB to shipped `_dbm`. Complete DB/CPython `_dbm` source access with applicable modifications and finite accompanying-software scope remains open. Not the later AGPL license. |
| `pbs-bzip2` / 1.0.8 | bzip2 source/origin/no-endorsement conditions; no binary-only source/notice duty identified. | Supplier notice supplied; absent source archive is provenance work. |
| `pbs-expat` / 2.9.0 | MIT copyright/permission notice. | Older supplier notice supplied; exact 2025 notice already exists in the private Expat source archive. Expose/reuse it without claiming that proves PBS source provenance. |
| `pbs-libedit` / 20240808-3.1 | BSD-3-Clause binary notices/no endorsement. | Notice supplied; reconcile applicable exact-release attribution. No general source duty. |
| `pbs-libffi` / 3.8.0 | MIT copyright/permission notice. | Supplier notice ends 2019; supplement with the exact declared release's 1996–2026 notice, preserving the old evidence. |
| `pbs-mpdecimal` / 4.0.0 | BSD-2-Clause binary notices. | Notice supplied; exact release attribution not reconciled (retained notice ends 2020). No general source duty. |
| `pbs-ncurses` / 6.5 | MIT/X11-style notice and promotional-name conditions. | Notice supplied; reconcile exact release attribution (retained text identifies 2021). |
| `pbs-openssl-3.5` / 3.5.9 | Apache-2.0 license, applicable NOTICE and change notices. | License supplied; exact-build additional attribution/NOTICE and modifications need reconciliation. No general source duty. |
| `pbs-sqlite` / pin 3530100 | Public-domain deliverable SQLite code. | Declaration retained; no own-license source/notice remediation identified. |
| `pbs-uuid` / standalone uuid 1.0.3 | BSD-3-Clause binary notices/no endorsement. | Theodore Ts'o notice supplied; reconcile applicable attribution. This is not the OCP util-linux uuid identity. |
| `pbs-xz` / liblzma 5.8.4 | 0BSD for this library. | Notice retained; no own-license source/notice condition. Other XZ tool terms are separate. |
| `pbs-zlib` / zlib 1.3.2 versus zlib-ng 2.2.4 | Zlib-family origin, altered-source and source-notice conditions. | Both notices supplied; actual static implementation unresolved. No binary-only source/acknowledgement duty under either declared alternative. |
| `private-expat` / Debian 2.9.0-1~deb13u1 | MIT copyright/permission notice. | Debian notice, exact upstream COPYING, upstream/patch archives and DSC supplied. Expose the current upstream notice alongside the older detached attribution. |
| `private-zlib` / binary 1:1.3.dfsg+really1.3.1-1+b1 | Zlib source/origin conditions. | Debian notice, upstream/patch archives and DSC supplied; no own-license source/relink remediation identified. Original +b1 reproduction is provenance work. |

## Five source-access sets to resolve

1. **OCCT:** bind the retained upstream source, actual changes, interfaces and
   necessary build/install recipe to the distributed libraries. Account for the
   pinned RapidJSON headers/notice where applicable. Complete and validate a
   suitable recipient modification/relink route under an applicable LGPL section
   6 option; section 6(b) is not the only possible route. See [OCCT's terms](
   https://occt3d.com/dev/doc/overview/html/occt_public_license.html).
2. **Berkeley DB / `_dbm`:** provide exact usable directions for obtaining DB and
   the accompanying CPython `_dbm` source/modifications within the actual
   Sleepycat scope. Existing pins give base URLs/hashes, not a completed modified
   source-access arrangement. Other files merely sharing a ZIP are not all
   automatically DB-using software. The operative license is the retained
   `licenses/python/LICENSE.bdb.txt`; [PBS's exact module recipe](
   https://raw.githubusercontent.com/astral-sh/python-build-standalone/20261013/cpython-unix/extension-modules.yml)
   explains the separately built module.
3. **libgomp:** provide component copyright and Runtime Library Exception 3.1,
   and exact applicable downstream source/patches/scripts through a valid GPL
   source-access option. The exception's qualifying combinations do not eliminate
   source duties for libgomp itself. See the [FSF exception explanation](
   https://www.gnu.org/licenses/gcc-exception-3.1-faq.html).
4. **LibRaw:** bind actual 0.19.5-6.el8_10 source/patches, retain its main and
   third-party notices, and establish an applicable source-access arrangement.
   Review the consequences of the applicable LGPL or CDDL route rather than
   choosing one to avoid a technical check. See [LibRaw 0.19.5 COPYRIGHT](
   https://raw.githubusercontent.com/LibRaw/LibRaw/0.19.5/COPYRIGHT).
5. **FreeImage:** verify the original and downstream grant for 3.17.0-5.el8,
   the actual patches/build inputs, incorporated codec notices and appropriate
   source-access directions. [Upstream explicitly offers GPLv2, GPLv3 or FIPL](
   https://freeimage.sourceforge.io/license.html); that is not an unrestricted
   “or later” grant and does not establish licensing for all distro patches.
   GPLv2-only cannot support a GPLv3-covered combined-work route. FIPL's larger-work
   permission does not itself establish GPL compatibility. Mere ZIP aggregation
   does not prove a combined work; the actual native links/imports warrant a
   scoped review. Under FIPL retain its executable source-rights/location notice
   and applicable modification-source availability; a GPL route has its own
   Corresponding Source conditions. No route is elected here.

Finite notice work remains alongside these source sets: the missing OCP-wheel
credits in the table, exact attribution updates for the named Python components,
and applicable incorporated-header notices. Already supplied source and notices
should be reused and indexed where appropriate; a generic license template does
not replace the actual copyright-holder notice.

## Modification, verification and stopping condition

[REBUILD_STANDALONE.md](REBUILD_STANDALONE.md) documents the existing public
builder's no-secret route to a distinct modified package. It regenerates integrity
identities instead of weakening the runtime checks. A direct edit to a published
cache is rejected; that is not evidence that recipient repacking is impossible.
Actual ABI-compatible replacement and complete corresponding-source usability
remain to be demonstrated under separate validation.

For the project/solver GPL route, an eventual network distribution can use a
qualifying section 6(d) arrangement with matching source and clear, equivalent
no-extra-charge access. A three-year written offer is not universally required;
it belongs to particular other distribution options. Preserve MPL source rights
and directions. Assess interactive-notice or User-Product installation conditions
when their actual predicates apply, rather than inventing an unconditional
About-screen, signing-secret or original-toolchain requirement. See [GPLv3](
https://www.gnu.org/licenses/gpl-3.0.html) and [MPL 2.0](
https://www.mozilla.org/en-US/MPL/2.0/).

Stop the documentary work when each named notice/source/repack requirement has
evidence or a concrete unresolved fact. Reassess redistribution only then.
Hash correspondence, an empty issue list, successful geometry tests and a
source-available builder are each insufficient by themselves to grant clearance.
