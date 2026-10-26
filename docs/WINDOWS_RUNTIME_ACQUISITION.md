# Windows-target runtime acquisition, not qualification

`release_inputs/windows-x64/acquisition-lock.json` maps exact, unmodified members
of five upstream archives into a candidate runtime. It is a Windows **target**
inventory, assembled and verified as data on Linux. No downloaded executable,
Python source, extension, installer or wheel was run. This is not a Windows
release, tested runtime, complete materials map, or licensing approval.

## Pinned sources

All archive sizes and SHA-256 hashes are in the lock. Python hashes were checked
against the matching official SPDX package entries; wheel pins were checked
against PyPI release metadata. Hashes identify downloaded bytes, not upstream
build reproducibility or an independently verified signature.

- [CPython 3.12.10 source SPDX](https://www.python.org/ftp/python/3.12.10/Python-3.12.10.tar.xz.spdx.json)
  binds `Python-3.12.10.tar.xz`, SHA-256
  `07ab697474595e06f06647417d3c7fa97ded07afc1a7e4454c5639919b46eaea`.
- [CPython 3.12.10 embeddable SPDX](https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip.spdx.json)
  binds `python-3.12.10-embed-amd64.zip`, SHA-256
  `4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3`.
- [OCP 8.0.1.1.0 metadata](https://pypi.org/pypi/cadquery-ocp-novtk/8.0.1.1.0/json)
  binds its CPython 3.12 Windows x64 wheel.
- [OCP proxy 8.0.1.1.0 metadata](https://pypi.org/pypi/cadquery-ocp-proxy/8.0.1.1.0/json)
  binds its pure-Python wheel.
- [slvs 3.2 metadata](https://pypi.org/pypi/slvs/3.2/json)
  binds its CPython 3.12 Windows x64 wheel.

No resolver chooses versions and no host installation supplies DLLs. Every wheel
regular-file member is retained at its original package-relative path, including
available distribution metadata and notices. This does not imply the wheel
contains all necessary third-party notices or corresponding sources.

## Exact mapping recipe

The current bootstrap rejects a stdlib ZIP or `_pth` configuration and requires
source modules under `python/Lib`, native stdlib modules under `python/DLLs`, and
an exact initial import path. The embeddable ZIP alone cannot satisfy that policy.
The acquisition lock does not change the bootstrap or relax its checks.

1. Inspect the pinned embedded `python312.zip` as ZIP data only. Its 589 `.pyc`
   member names identify the corresponding `.py` members in the matching official
   CPython source archive. Map those **source bytes unchanged**, not decompiled
   bytecode, into `python/Lib`. All 589 corresponding sources exist.
2. Retain the eight matching non-bytecode stdlib data files from the source tree.
   The two generated lib2to3 grammar `.pickle` caches are omitted. The runtime is
   intended for the CAD sidecar; arbitrary stdlib tooling is not qualified.
3. Keep `python.exe`, `python312.dll`, `python3.dll`, both VC runtime DLLs and
   `LICENSE.txt` at the interpreter root. Put all remaining embedded native
   extensions and their DLL dependencies in `python/DLLs` without changing bytes.
4. Do not copy `pythonw.exe`, `python312.zip`, `python312._pth` or `python.cat`.
   No catalog/signature validation is claimed for this rearranged runtime.
5. Copy all regular wheel members into `packages/`, preserving the OCP
   `cadquery_ocp_novtk.libs` directory. No wheel installer or entry point executes.

These decisions are explicit lock entries, not runtime wildcard selection. All
five whole archives passed the acquisition scanner, with no inert-case aliases
needed. The existing hash-before-parse, path/link/collision, output budget,
no-clobber and final complete-inventory checks remain active.

## Reproduction and observed evidence

Run from a Linux checkout with an existing private parent directory and a fresh
output name:

```sh
python scripts/acquire_release_inputs.py \
  --lock release_inputs/windows-x64/acquisition-lock.json \
  --work-root /existing/private-parent/new-windows-candidate
```

An optional read-only `--download-cache` reuses archives after verifying every
size/hash. Do not overwrite a failed or completed work root. The adapter records
the target platform, `native_execution: false`, and
`WINDOWS_COMPONENT_MAPPING_NOT_REVIEWED`, not Linux's historical materials count.

The 2026-10-26 Linux-host data-only realization verified:

- 1,050 files, 203,923,835 bytes.
- Runtime inventory SHA-256:
  `b7273d2776622fe5e16070be542bb3bcb07ff003200fb173bbd1b9f10b2dfb10`.
- Acquisition lock SHA-256:
  `25bc39a8a1dfd190122344a17f2f3f017707367bc77271f5771318c13038587a`.
- 103 native files have PE32+ AMD64 structural headers. This is not a PE import
  closure audit, Authenticode verification, loader test or executable test.

## Unclosed gates

The adapter still uses Unix mode accounting. Windows-target bytes are reproducible
on Linux, but running acquisition on an NTFS Windows host has not been qualified;
do not weaken mode checks to make that host pass. A future workflow can assemble
the exact candidate ZIP on Linux and qualify it on Windows independently.

Required remaining work includes actual fixed-argument isolated Python startup,
source import origins, all native imports and DLL closure, VC/third-party source
and notice provenance, exact installed package save/reopen tests, and Windows
launcher ancestry/ACL/Job Object behavior. The existing materials-review and
native qualification gates must bind the final candidate bytes. Neither this
lock nor the earlier Windows source-only tests establish those results.
