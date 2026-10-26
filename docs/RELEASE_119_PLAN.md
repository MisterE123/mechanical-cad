# Bounded 1.19 packaging and verification plan

1. Integrate release metadata, then freeze the exact clean source commit before
   building. Preserve Linux 1.18, its source/history, and recovered inputs.
2. Export only committed files to a clean source snapshot. Use the existing
   standalone extension/materials packaging contracts, not the development venv.
3. Recover external-runtime inputs from the verified 1.18 payload, excluding its
   old src/ tree and bootstrap.py. Preserve every external file hash and mode and
   the original runtime-lock bytes. Carry original dependency/materials declarations
   and unresolved issues forward, updating only project identity/source references
   and corresponding inventories. Do not silently install old project code.
4. Build an exact 1.19 Linux x86_64 archive and source/evidence companions. Record
   input/output hashes, exact source commit and inventories. Verify old/new external
   runtime inventories match and packaged core/add-on/bootstrap match frozen source.
5. Reserve the native slot before launching verified Blender 5.2.2. Install the
   exact ZIP into an isolated user profile, enable with the bundled backend only,
   assert version and release identity, and check no OCP/slvs imports in Blender.
6. Use one small plate: edit a dimension, replay, Check, save .blend, independently
   reopen, verify canonical data and replay/check again. Require exit status zero
   and explicit success markers with --python-exit-code 1. Do not run the legacy
   broad install harness, full suite or complex enclosure as part of this pass.
7. Record fresh results separately from prior source evidence. Explicitly list
   installed interactive GUI, Windows and full-suite qualification as unrun.
   Return artifacts to the parent for persistence/delivery; no GitHub publication
   or Library upload occurs in the packaging worker.
