# Additive Linux candidate input preparation

`scripts/supplement_linux_preview_inputs.py` is an offline, Linux-host-only copier,
not a builder, trusted review ledger, native qualification or release admission.
It accepts an existing source-refresh directory and separately pinned SHA256s of
its `preparation-receipt.json` and `inputs/metadata/materials-map.json`.

Supply `--base`, `--base-receipt-sha256`, `--base-map-sha256`, `--additions-root`,
`--additions-manifest`, `--additions-sha256`, and a fresh separate `--output`.
The additions manifest is strict JSON `{ "schema_version": 1, "files": [...] }`.
Each file has `path`, `mode` (420), `size`, `sha256`, and `roles` (a nonempty unique
list drawn from `source`, `notice`, `provenance`). Source paths start `sources/`;
notice/provenance paths start `licenses/`. The unchanged material parser controls
allowed data formats. Paths address the exact same relative file in the additions
root and new materials root. The manifest itself stays outside that root. Limits:
64 added files, 512 MiB combined; unknown, aliased or colliding entries fail closed.

The tool copies regular files (no hardlinks), requires a 5 GiB free-space reserve,
and leaves incomplete output on failure without deletion or overwrite. It verifies
base source, runtime and materials before copying and verifies original and copied
bytes afterward. All 42 nonproject components, 42 historical issues, runtime
bindings, selected source identity and runtime bytes remain unchanged. Only the
existing project-package references gain additional inventoried material paths.

The new materials include the exact additions manifest, pinned predecessor receipt,
supplement provenance and a separate helper/checker source ZIP. This implementation
may postdate the target source commit; the ZIP is not represented as part of that
older project snapshot. To reproduce, inspect/extract the helper ZIP into a separate
checkout-shaped directory, use its script with the same base, pins and additions,
and select another fresh output. No private Git history is required. This tool
executes no input source, downloads nothing and selects no license route. The
historical evidence and open issues are retained, not automatically resolved.
