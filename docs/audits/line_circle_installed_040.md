# 0.4 release qualification receipt

Complete preview archive SHA-256:
`f72b0df540fe7bf0f8f9b449eb25c222639c72275f398f3f31a53395a99b2516`
(5,493,703 bytes, 103 payload files). This documentation receipt was committed
after packaging; the released source and all archive bytes remain unchanged.

Source: `4b53129c5aa27bb97fd5f130233431e2d04d7e13`.
Installable ZIP SHA-256:
`7d1b6fe99cea43ee13fc0ebb238d331d15e5a6a57d65004d5096fcfe77d37307`.

Qualified on Linux x86_64 with official native Blender 5.2.2 LTS, build
`d13f752e3b9c`, CPython 3.12.14, cadquery-ocp-novtk 8.0.1.1.0 and slvs 3.2.
Other operating systems and Blender versions are not qualified. Blender 5.2 is
the declared minimum.

## Automated gates

- Final committed source: Ruff/format, 2,899 pytest tests plus 19,597 subtests.
- All 31 native suite entrypoints in `scripts/run_checks.sh` passed, followed by
  both real application-exit/owned-child-reaping gates. The complete log ends
  `FINAL_CHECK_EXIT=0`.
- Exact ZIP installed into a separate fresh Blender script/config directory:
  blank New Document, Part checks, assembly checks, all 116 New/Edit/Resume and
  capability-dispatch assertions, version/assets and module-root checks passed.
- Every one of the 597 files installed in the GUI profile matches the ZIP bytes.
  All 806 source archive files match their Git blobs. The 83-commit Git bundle
  clones cleanly and passes `git fsck --full`.
- The GUI-authored saved example was independently opened in a fresh background
  process using the installed package. Load invalidated cached state, replay
  preserved exact canonical/annotation bytes, and geometry checks passed. The
  input `.blend` file was not rewritten.

## Native installed GUI

The reviewer used a clean ordinary Blender profile, visible Preferences → Install
from Disk, enabled 0.4.0, configured the pinned sidecar and used normal controls.
No source registration launcher or scripted geometry was used for this gate.

Passed: visible New CAD Document; New Sketch; Circle center/radius clicks;
Dimension selection/placement; double-click compact field; exact `5 * 2` Enter
acceptance once; Finish; 10 mm extrusion; normal Edit Sketch with automatically
restored annotation and isolated old mesh; invalid `5 / 0` retention and Esc;
`5 * 3` acceptance; Finish rebuilding the same `sketch_1` and `extrude_1` to
7068.583496 mm³ displayed volume. Legacy Rectangle drawing, workspace suspension,
normal Resume and Cancel also passed without changing the cylinder.

A diagnostic focus trace found `WINDOW_DEACTIVATE` while Preferences was still
frontmost. The editor correctly suspended raw input. Closing Preferences through
its normal title-bar control restored main-window focus and editing worked;
production source was not changed. This is a focus-loss retention observation,
not an ignored input failure.

`installed-circle-part.blend` is the resulting R15 × 10 mm example, with exactly
those two feature IDs, no unfinished draft, and the radius expression `5 * 3`.
SHA-256: `644d566bf097c3de0dbfc2ce27a6f78025ce06a31896dc6f90c06dcd2c6ad54b`.
The screenshots show the earlier R10 editing/Part pair and the later R15 rebuild.
The separate source-reviewed open-wire file and screenshot belong to the earlier
source-loaded GUI gate, explicitly identified in their receipt.

A further fresh native restart opened the saved file as DIRTY. Visible Rebuild
restored the R15 cylinder; normal Edit restored the exact saved annotation offset.
An uninstrumented double-click and Enter accepted once. The original saved file
remained unchanged. The separate installed GUI report records these checks.

## Scope and limitations

This is a line/circle sketch preview. The core solver supports more constraint
kinds than the editing UI exposes. Line distance and circle radius drivers,
exact raw expressions and existing compatible constraints are supported. Arcs,
trim/extend, construction tools, diameter/reference dimensions, multiple regions,
holes and context/reference geometry are not exposed. The custom text field has
no IME composition or screen-reader integration. Dense-label, all-input-device
and maximum-cap performance qualification remains open.

The first outside click suspends raw input and consumes its release. Use Reopen
or a subsequent explicit Cancel Input. The natural GUI solve finished before a
Cancel Check click could be qualified; cancellation evidence comes from the
independent real-process/native lifecycle gates, not that mouse attempt.

An open sketch can be valid editable geometry without a solid. Existing assembly
verification remains bounded to rooted trees, literal mate frames and specified
poses. No continuous collision, structural/load analysis, physical fit or
manufacturing certification is implied. See START_HERE and the workflow docs.

The released 0.3 complete archive is unchanged; its independently rechecked
SHA-256 is `a315fbec83eceb395e73251b0ee780a9d592ceb80094743fc6bff7d40f115c59`.
