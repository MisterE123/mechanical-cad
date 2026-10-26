# Printable external spur gear pair

Assembly → **New Printable Gear Pair** is one Apply/Cancel configurator. It does
not require an existing working Part. The working Part is untouched. Replacing
an existing Assembly requires the explicit replacement checkbox; save it first.
Cancel or an invalid candidate leaves the accepted Assembly unchanged.

The main controls are driver/driven teeth, module (mm), shared thickness (mm),
bore diameters (mm), and total pair **circular pitch-circle backlash** (mm).
The live numeric summary shows shaft spacing and signed B/A angular ratio.
**Advanced tooth profile** expands pressure angle (degrees), root clearance
(a module multiple), and involute profile tolerance (mm). Its collapsed summary
still shows the actual values, including custom values loaded by Edit Gear Pair.
Opening or closing either disclosure preserves every draft input; the controls
do not reset or change saved parameters. **How it works and printing** reveals
the assembly and fit explanation. Replacement confirmation, the non-printable
reference-base warning, lack of an interference check, and fit/strength limits
remain visible with details closed. There is no provisional
3D geometry preview in this first configurator; Apply uses the existing guarded
native sidecar transaction asynchronously and publishes only a complete valid result.
The dialog closes while **Creating gear pair** shows elapsed time and **Cancel
Creation**. You can navigate; Esc or Cancel stops the request without changing
the accepted Assembly, its save path, display or previous check. Changing the
original workspace, Part, Assembly, backend, units, history or admitting a newer
edit rejects late results. Replacing an Assembly is bound to the exact revision
you confirmed, not whatever document is current when work finishes.

Backlash is divided equally between the two Parts as pitch tooth-thickness
reduction. It is not radial clearance, bore allowance or a guaranteed measured
normal gap. Root clearance adds root depth; it does not change shaft spacing.
Bore diameters are literal finished CAD dimensions, with no printer shrinkage
compensation. Fit depends on printer, material, orientation and postprocessing.

## Automatic assembly

- Two independent editable `spur_gear` source Parts and instances.
- Shaft axes parallel to world/local +Z, profiles in XY, thickness along +Z.
- Centers at (0,0,0) and (module × (teethA + teethB) / 2,0,0).
- Two revolute joints rooted to a tiny **Reference base — NOT FOR PRINT** Part
  below the gears. This is only the required grounded graph reference, not a
  bearing, shaft or printable mounting solution.
- Driver A starts at zero, with tooth 0 centered on +X. Driven B starts at
  pi + pi/teethB radians, so its inward-facing direction is a tooth gap.
  This phase is included once, in the gear relation offset. For odd tooth
  counts it is equivalent to zero modulo tooth pitch; do not replace this
  formula with a universal half-pitch rotation.
- Driven B angle = −teethA/teethB × driver A angle + starting phase. The signed
  ratio follows the actual parallel mate-local +Z axes, not a visual shortcut.

Apply validates the complete native solids and rooted assembly. Replay is NOT
an interference/contact check or manufacturing certification. Use **Check Pose**
and explicit sampled motion checks when evaluating a chosen fit. Even passing
sampled native checks do not prove continuous collision freedom, usable contact,
strength, wear, loading, bearing design or printable tolerances.

## Edit and print only the gears

The assembly shows **Open Gear A (…) Part** and **Open Gear B (…) Part** buttons.
Opening uses the normal confirmation to replace the working Part; save that
Part first. Then use **Export CAD STL** (millimetres) or **Export CAD STEP**.
These exports freshly replay the selected single gear source and do not include
the reference base. Whole-Assembly STEP export, in contrast, includes every
instance including the reference base; do not treat that as a gear-only print.

The gear's named parameters remain editable in the normal Part parameter editor.
After an intentional source edit use **Update All Instances**. Assembly center
distance, ratio and phase are authored values, not hidden live links to source
parameters. For module or tooth-count changes, prefer **Edit Gear Pair** while
the generated structure is intact, rather than updating only one gear's source.
If you have customized the assembly, edit its mates explicitly or create a new pair. Bores and
thickness can be edited independently, but verify the resulting assembly.

## Bounded first implementation

Only unshifted external spur pairs, no helical/internal/rack gears, hubs, keyways,
profile shift or undercut generation. Conservative minimum tooth counts depend
on pressure angle. The involute uses tolerance-bounded cubic curves with analytic
tip/root arcs in a closed native B-rep, not an analytic involute surface. Straight
below-base transitions and sharp root corners remain; no cutter-generated fillet
is claimed. Tooth flanks remain snapshot-local topology rather than falsely
stable curve-segment references.
See [Spur gear geometry](SPUR_GEARS.md) for native parameter bounds and details.

## Historical polygon baseline verification

Focused tests cover all odd/even phase combinations and native common-volume
checks for 20/40, 19/37 and 20/37 teeth with 0.2 mm total backlash plus an
18/60-tooth pair with zero backlash and zero root clearance. Each native pair is
checked at driver fractions 0, 0.17, 0.49 and 0.83 of one tooth pitch; these
16 poses showed no common volume above 1e-9 mm³ at 0.05 mm profile tolerance.
The default 20/40 pair at 0.01 mm profile tolerance additionally had zero
common volume and 0.09597536 mm minimum separation at the starting pose.

Native Blender 5.2.2 background smoke exercises creation, invalid-input refusal,
replacement protection, no-op dialog cancellation and opening a single embedded
gear Part. This is not manual GUI, installed-ZIP or two-process persistence QA.
Creation now uses the shared cancellable Assembly process owner. Focused native
Blender 5.2.2 tests cover asynchronous default creation, running and ready-result
cancellation, newer-dialog rejection, Open during creation, exact preservation
of working Part and dormant intent, and a fresh-process accepted-Assembly reopen.
The earlier polygon replay took tens of seconds, but starting Apply
returned in 0.013 seconds in the development runtime instead of blocking it.
No per-Apply interference calculation runs; **Check Pose** remains explicit.
The synchronous Assembly edit API retains its existing guarded transaction
semantics. Scripted gear operator EXEC now returns RUNNING_MODAL and must be
allowed to finish or cancelled. Background modal pumping is not GUI usability
or interactive modal Undo/Redo qualification.

## Curved geometry and Windows evidence

The curved constructor preserves the canonical parameters, center spacing,
signed ratio and odd/even phase formula above. It pins the pitch-circle points
and refines small-backlash curves within the requested tolerance upper bound.
See [spur gear geometry](SPUR_GEARS.md) for the vector approximation proof.

On Windows test host, Windows CPython 3.12.10 with the unchanged pinned kernel passed 24
native sampled poses: 20/40, 19/37, 20/37 and 19/40 at total backlash 0.2 mm;
18/60 at zero backlash and zero clearance; and 18/200 at zero backlash and
clearance 0.25. Driver fractions were 0, 0.17, 0.49 and 0.83, with requested
profile tolerance 0.01 mm. Every sampled common volume was zero. This remains
sample evidence, not continuous contact or collision-freedom certification.

Windows core replay, backlash edits and individual gear STL/STEP exports passed,
including filenames under a directory with spaces and non-ASCII text. A Windows
flush failure was fixed by reopening the completed owned export temporary with
write access before fsync. Strict geometry and atomic replacement checks remain.

The Blender Windows runtime admission gate remains closed. Native Blender 5.2.2
registration, pure candidate generation, failed-Apply state preservation and
absence of OCCT/SolveSpace imports were checked; successful live UI creation,
installed ZIP, manual GUI and persistence are not qualified. See the exact
[Windows development result and remaining boundary](GEAR_WINDOWS_DEVELOPMENT.md).

## Edit the configured pair together

Use **Edit Gear Pair** above the gear-Part buttons to reopen the same controls,
prefilled from the accepted pair. Apply regenerates both solids, shaft spacing,
tooth phase and ratio atomically through the cancellable native owner. The driver
A angle, assembly/source/Part/joint identities, custom display names and save path are
retained. Default gear names update their tooth counts; custom names are untouched.
The working Part (including an already opened gear) is untouched. Reopen a gear
Part explicitly to export its new accepted revision. Existing checks become
unchecked after success; run Check Pose again. Failure, Cancel and stale results
leave accepted geometry, path and checks unchanged.

The shortcut recognizes only the exact generated external-spur template, with
its generator/source IDs, embedded feature expressions, source hashes, reference
base, frames, rooted shafts and mesh relation. Names, the independent driver
angle and saved verification intent may differ. It does not infer pairs from
meshes, matching names or arbitrary two-gear assemblies. Modified geometry,
frames, ground placement, joint limits, extra instances or altered ratios/phases
are refused with guidance to edit Parts/mates individually or save and create a
new pair. No new document schema is introduced. Template recognition is not an
authenticity certificate or manufacturing guarantee.
