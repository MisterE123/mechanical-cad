# Box and two reusable sectors

This development example is one editable Assembly: a 40 × 30 × 10 mm box
and two instances of the same fully constrained quarter-sector Part (R5,
height 10 mm). It needs a backend advertising `mcad.assembly-result/3` and
`mcad.snapshot-sketch3/1`; the delivered 0.6 preview cannot open this workflow.

- `base.mcad.json`: independent box Part
- `sector.mcad.json`: fixed-center, horizontal/vertical-radii, radius-driven sector
- `assembly.mcad-assembly.json`: both embedded Part snapshots, two explicit
  literal seats, +Z slider joints, and a selected 2 mm base-clearance requirement
  for each sector

Open the Assembly in the Assembly workspace and explicitly run Check. Each seat
is at z=10 mm; a slide coordinate of 10 mm puts its sector origin at z=20 mm,
leaving 10 mm between the box top and the sector bottom. Seat A is at x=10,
y=10 mm; Seat B is at x=25, y=10 mm. These frames are literal coordinates and
do not automatically follow geometry changes.

Select the reusable sector Part and open its embedded source as the working
Part. Change `radius` from 5 to 7, regenerate, then explicitly Update All
Instances. Both sector instances change together. Check again: earlier reports
refer to the old source revision. To inspect a known collision, sample Sector A's
slider at `-5, 10`; at -5 mm it overlaps the box. Listed clear poses do not prove
continuous collision freedom. Restore the saved coordinate to 10 mm and Check.

Export an individual Part by opening its embedded source and using Part Geometry
Check and STEP/STL export. There is no Assembly-wide export. STL coordinates are
millimetres; choose millimetres when importing them elsewhere. None of these
checks establishes physical fit, structural safety or manufacturing approval.

## Reproduce the complete project regression

The source-loaded native smoke starts from blank Parts and uses the existing
sector point/constraint owner and registered Part/Assembly operators. It draws
and constrains the sector, reuses it, edits the same radius IDs, updates both
instances, checks explicit poses, preserves an unrelated object, saves a real
`.blend`, and opens it in a separately launched second Blender process. Saved reports are historical
until explicit fresh replay/check. It also exercises one wrong-version response,
one late completion and one failed source update.

Run only with an authorized native process slot and an unused output directory.
The owning process collector must launch and collect both commands serially;
the smoke never launches another Blender process itself. Each lifetime has a
900-second alarm. The project qualification runner uses a shared 1800-second
budget across both lifetimes.

```sh
export MCAD_ROOT="$PWD"
export MCAD_PYTHON=/absolute/path/to/backend/python
export MCAD_SECTOR_ASSEMBLY_DIRECTORY=/absolute/path/to/new/test-output

MCAD_SECTOR_ASSEMBLY_PHASE=save \
/absolute/path/to/blender --background --factory-startup --python-exit-code 1 \
  --python tests/blender_sector_assembly_workflow_smoke.py

MCAD_SECTOR_ASSEMBLY_PHASE=reopen \
/absolute/path/to/blender --background --factory-startup --python-exit-code 1 \
  --python tests/blender_sector_assembly_workflow_smoke.py
```

The output contains `project.blend`, the actual generated Assembly JSON,
the box and both radius revisions as Part JSON, `base.step`, `base.stl`,
`sector-radius7.step`, `sector-radius7.stl` and readable check reports. The owning
collector retains each process's logs. Existing same-invocation writer observations check STEP
readback validity/volume/bounds and the STL payload against the exact writer
mesh. Generated native artifacts stay outside Git. Successful runs print both
`SECTOR_ASSEMBLY_WORKFLOW_OK save` and `SECTOR_ASSEMBLY_WORKFLOW_OK reopen`;
this is headless source-loaded regression,
not installed-package or manual-GUI qualification.
