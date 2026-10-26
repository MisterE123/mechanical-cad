# Third-party software

This repository's original code is GPL-3.0-or-later (see LICENSE). Dependencies
retain their own licenses, copyright notices and applicable source obligations.
Mechanical CAD uses Open CASCADE Technology (OCCT) through the OCP bindings and
SolveSpace through slvs in a separate Python process, never inside Blender.

Copyright (c) 2026 Mechanical CAD contributors.

This software contains paintlib code. paintlib is copyright (c) 1996-2002
Ulrich von Zadow and other contributors. The original notice is preserved with
the FreeImage source and under `licenses/freeimage/`. The same acknowledgement
is displayed with Mechanical CAD's copyright in the extension preferences.
This software uses FreeImage, whose original license texts and corresponding
source/patch materials are included in the standalone distribution materials.

## Which package these notices describe

The standalone extension candidate contains the isolated CPython/CAD runtime,
including native OCP, OCCT, slvs and their selected dependencies, in its nested
offline backend payload. Its intended installation is one Blender Install from
Disk ZIP with automatic offline preparation, without a separate Python install,
package manager or manually configured backend path. Blender itself and the
supported host's normal OS/graphics libraries are installed separately.

The earlier delivered 0.6 add-on used a separate matching sidecar environment;
that legacy add-on ZIP did not contain the native backend. The Git source tree
does not vendor runtime binaries. Neither fact describes the standalone ZIP.

These documentary corrections do not alter the frozen candidate or its original
source archive. Redistribution review remains **OPEN**; this is not public-release
clearance. Windows testing is deferred and public Windows admission remains
**CLOSED_UNTESTED**. See the [distribution materials and remaining facts](
docs/STANDALONE_DISTRIBUTION_MATERIALS.md) and the [recipient rebuild/repack guide](
docs/REBUILD_STANDALONE.md).

## Principal components and existing material locations

Paths below starting with `licenses/` or `sources/` refer to members of the
standalone materials ZIP, not additional installation directories. Its generated
`MATERIALS.md` and `PACKAGED_MATERIALS.json` provide the full inventory and hashes.

- **Blender**: GPL-3.0-or-later. Installed and distributed separately.
  https://www.blender.org/about/license/
- **CPython 3.12.15 / Python Build Standalone 20261013**: Python's license stack
  and supplier acknowledgements are retained in `licenses/python/`. Selected PBS
  build recipes carry MPL-2.0; this does not make every generated runtime file
  MPL-covered. The runtime excludes the deprecated `crypt.py`/`_crypt` pair.
  The separate Berkeley DB 6.0.19 contribution to `_dbm` has Sleepycat source-access
  conditions; its notice is `licenses/python/LICENSE.bdb.txt`.
- **cadquery-ocp-novtk 8.0.1.1.0** and **cadquery-ocp-proxy 8.0.1.1.0**: Apache-2.0
  bindings/build-system terms, with incorporated-code terms retained separately.
  See `licenses/ocp/OCP-8.0.1.1-LICENSE.txt`,
  `licenses/ocp/build-system-LICENSE.txt` and https://github.com/CadQuery/OCP .
- **Open CASCADE Technology**: LGPL-2.1 with the OCCT additional exception.
  The standalone payload includes 51 `libTK` shared libraries. License, exception
  and upstream explanation are in `licenses/occt/`; the retained upstream source
  archive is under `sources/occt/`. Exact source/patch correspondence and a usable
  recipient modification route remain under review. The header exception does
  not waive the library's own source obligations.
  https://occt3d.com/dev/doc/overview/html/occt_public_license.html
- **slvs 3.2 / SolveSpace**: the combined solver is documented under
  **GPL-3.0-or-later**. Its publisher metadata contains an MIT classifier alongside
  a GPL-v3-or-later declaration, and its supplied COPYING is GPLv3. The classifier
  is not a grant to relicense the linked SolveSpace whole. Preserve that original
  metadata and the publisher's license texts rather than rewriting them. The
  complete supplied sdist is `sources/slvs/slvs-3.2.tar.gz`; notices are in
  `licenses/slvs/`. It is bundled in the standalone sidecar, although the legacy
  source project's `sketch` dependency group is optional.
  https://pypi.org/project/slvs/3.2/ and https://solvespace.com/library.pl
- **Solver contributions**: the supplied slvs source includes Eigen (declared
  3.4.0), COLAMD notices and mimalloc (declared 2.2.2). Keep the MPL and applicable
  permissive notices as well as the combined solver's GPL terms. Detached texts
  are in `licenses/slvs/eigen/` and `licenses/slvs/mimalloc-LICENSE.txt`.
  Additional SuperLU/Xerox, TensorFlow, half-conversion and Intel header notices
  are indexed in the distribution guide; their source presence does not prove
  that every optional library or template is linked.
- **Other runtime contributions**: the finite 43-component table in the
  distribution guide identifies the selected Python, OCP-wheel and private
  Expat/zlib dependencies, supplied notices and unresolved facts. In particular,
  libgomp, LibRaw and the exact downstream FreeImage grant/source route still need
  component-specific work. No alternative license is elected by this notice.
- **pytest, ruff and packaging tools**: development-only dependencies. Consult
  their distribution metadata for their own licenses.

The project source and build/package tools are supplied under `sources/project/`.
The public builders can regenerate manifests and launch hashes for a recipient's
modified runtime without a publisher signing secret. That mechanism does not by
itself establish complete corresponding source, ABI compatibility or compliance
with an applicable relink/replacement option. Applicable notices, source access
and distribution conditions must be completed before redistribution clearance.

## Offline UI icons

`blender_addon/mechanical_cad_blender/assets/icons/` includes 20 Google Material
Symbols sources under Apache-2.0, pinned to upstream commit
`49d4db35df873165d6bd6ba09b063c7dafbac2f4`, and 24 original CAD action symbols
under GPL-3.0-or-later. The pack includes original SVGs, transparent PNG sizes,
source hashes, exact upstream files, license texts, NOTICE, and rebuild scripts.
See its manifest and NOTICE for per-asset attribution and modifications. The
asset catalog includes future actions; an icon's existence is not a claim that
its tool is implemented. Google does not endorse this project.
