# 0.7.0 integrated standalone CAD preview candidate

Status: **candidate preparation, not a public release**. Exact successor
installer/manual-GUI qualification and dependency distribution materials remain
pending. Redistribution rights review is **OPEN**. Windows testing is deferred;
its public execution path remains closed and unqualified. Earlier archives stay
immutable. See [installation status](INSTALL.md) and
[distribution materials](STANDALONE_DISTRIBUTION_MATERIALS.md).

## One offline installation

The target is one self-contained extension ZIP for native Blender 5.2.2 LTS on
Linux x86_64: Install from Disk, enable, then automatic offline backend preparation.
The ZIP includes the isolated CPython 3.12/OCCT/SolveSpace sidecar. No separate
backend setup, source extraction, Python installation, runtime download, package
manager or manual backend paths are required in the standalone user workflow.
Native CAD remains outside Blender's Python process. Earlier internal Linux
installer evidence does not qualify the exact 0.7 candidate bytes.

## Integrated bounded workflow

- Constrained XY sketch lines/circles, direct dimensions, editable Parts and
  extrusions, plus the explicit opt-in one-arc/two-radii sector workflow.
- Bounded sectors retain shared point IDs, a fixed center, H/V and radius
  constraints, one profile and one extrusion. Reviewed radius and extrusion
  height remain 1–1000 mm in the supported XY, zero-origin domain.
- Mixed box-and-sector Assembly capture and reusable instances; edit working
  Parts, then explicitly update the accepted source revision for all instances.
- Explicit literal mate frames and fixed/revolute/slider joints in a rooted tree;
  current-pose and explicitly listed-pose clearance checks against fresh solids.
- Save/reopen editable Part and Assembly data, then replay/check for current
  evidence. Export supported individual Parts as STEP or validated STL.

Follow [the box-and-sector project](BOX_SECTOR_PROJECT.md). Frame coordinates do
not follow changed Part dimensions automatically. Listed clear poses do not
prove continuous collision freedom. Checks/exports are bounded geometry gates,
not structural, physical-fit or manufacturing certification.

## Limits and source correspondence

No Assembly-wide export, arbitrary multi-arc profiles, holes, trim/extend, broad
constraint editor, face-picked mates, nested assemblies or closed-loop mate
solver is added. Native conservative rejection retains recoverable draft state;
stale display caches cannot authorize geometry checks or export.

The versioning step was metadata/documentation only over integrated source
`eb9b51caab77c94e92c32a2d75042f756ab83012`. Production Python changes are limited
to the core/add-on version literals and the two existing exact-version checks in
the source install verifier and bundled child bootstrap. Kernel, solver, runtime
logic, operation capabilities, guarded evidence and publication behavior are
unchanged. A subsequent display-only Preferences credit block supplies the
required third-party copyright acknowledgements and points to the included
license/source files. It performs no filesystem or backend work. Test-side
finite equivalence restores exact historical bytes without changing earlier
hashes, fixtures or tamper assertions; compatibility tests distinguish supported
sector Assembly sources from unsupported profiles and preserve legacy wire
behavior. Full native regression and exact installed qualification are recorded
separately before release claims.
