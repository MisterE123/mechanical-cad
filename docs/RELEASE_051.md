# 0.5.1: cyclic coordinate-equality DoF safeguard

The pinned slvs 3.2 solver can return a successful status with an incorrect
remaining degree-of-freedom count for cyclic coincidence, Horizontal or Vertical
relations. This affects ordinary line sketches in 0.5. A three-point coincidence
cycle reports zero DoF although two translations remain; a three-line Horizontal
cycle reports three instead of four. The defect does not require arcs.

## What changes

0.5.1 checks separate active u/v equality graphs after the existing exact-relation
deduplication. A cycle produces `solver_dof_indeterminate` before calling native
SolveSpace. The draft remains available, but no current solved geometry, trusted
DoF or extrusion/export authority is accepted from that solve.

This conservative restriction can reject a cyclic system even when its native
count happens to be correct. It does not calculate a replacement rank, delete
relations, change document schemas or migrate authored geometry. Acyclic systems
continue through the native solver. This is a bounded correction, not a claim
that every other constraint system is numerically correct.

## Upgrade both components

1. Preserve your `.blend` and canonical `.mcad.json` files and the old installation.
2. Extract the 0.5.1 source ZIP, or restore its full-history bundle. Create/install
   its Python sidecar environment using [INSTALL.md](INSTALL.md).
3. Install the matching 0.5.1 add-on ZIP in Blender and configure its Project Root
   and Sidecar Python to the new source/environment. Updating only the add-on ZIP
   does not replace the solver adapter in an old sidecar installation.
4. Reopen your file and run a fresh Check/Rebuild. Previously accepted display
   geometry is not proof that the current sketch is solved. Do not rely on a
   0.5 freedom count for a cyclic equality system.

The 0.5.1 interface does not negotiate a solver-guard capability or detect an old
sidecar version. Its displayed add-on version alone is not proof of this repair.
An intentionally configured 0.5 core can still return the incorrect successful
DoF report through the compatible protocol. Qualification therefore checks the
actual configured core's version, imported solver path and SHA-256, then exercises
the cyclic failure and recovery through the installed add-on.

Run the read-only installation check from the new source directory with the
interpreter that you will configure in Blender:

```sh
.venv/bin/python scripts/verify_sidecar_install.py --project-root "$PWD"
```

Require `ok: true`, core version `0.5.1`, rejection with
`solver_dof_indeterminate`, and the successful acyclic native control with two
remaining DoF. It prints the exact Project Root, interpreter and solver SHA-256.
Set Blender to those same values. The check cannot inspect another Blender
process's preferences; installation is incomplete until it passes and the
configured values match. Runtime capability negotiation remains future work.

The add-on still ships without native dependencies. Qualified dependencies and
platforms are listed in the verification record; the package receipt identifies
the actual tested archive. The delivered 0.5 package is retained byte-for-byte.

## Recover an affected draft

Check presents a readable counting-defect error and keeps the authored points,
relations, command history and recoverable draft intact. Finish remains blocked
until there is current successful solver evidence. Repeated Check does not erase
or silently remove a relation, and this guard does not fabricate conflict IDs.

You can Undo your last relation change, inspect exact relation identities, or
explicitly choose an authored-position relation removal through the existing
confirmation flow. That recovery preserves authored seed positions; geometry may
move when you Check again. A failed solve does not certify which relation should
be removed. Suspend/Resume preserves the draft but restores no solve authority.

## Scope retained

Explicit H/V and fixed-point relations, Line/Circle dimensions, the Rectangle
shortcut, Part geometry/export and bounded rooted-tree assemblies remain the
supported product scope. Arc research and design documents in the source history
are development material; this hotfix adds no arc authoring or runtime support.
See [SOLVER_DOF_GUARD.md](SOLVER_DOF_GUARD.md) for the precise guard boundary.
