# Ventilated enclosure: datum-driven primary model

Development-source CAD example, not manufacturing, airflow, strength or fit
certification. The new Loft, Hole, replay-admission and contact-policy capabilities
are not all in delivered Linux 1.17. Use the explicitly identified next checkpoint
or matching current source. Native runtime: Blender 5.2.2 LTS; OCCT Python package
cadquery-ocp-novtk 8.0.1.1.0. See source_attribution.json for source-specific evidence.

## Primary deliverables

- Ventilated enclosure current-source.blend: editable Part and Assembly scenes.
- ventilated_body_datum.mcad.json and removable_duct_cover_datum.mcad.json:
  independent canonical, editable Part graphs.
- Matching *_datum.step and *_datum.stl: one printable solid per file.
- ventilated_enclosure_datum.mcad-assembly.json and .step: the intended seated
  two-part assembly, using an explicit named-pair numerical contact policy.
- alignment_report.json, final_hole_axes_report.json and datum_assembly_report.json:
  measured alignment, exact geometry, STEP readback and policy evidence.

Files without the _datum suffix retain the earlier grouped-Hole or 0.2 mm-gap
experiments. They are regression/alternative examples, NOT the recommended primary
construction. The original grouped-Hole .blend is preserved under repros/.

Core validation and two-process native save/reopen qualification are complete.
Native Load, named diameter edit/restore, Part and seated-assembly STEP exports,
and saved-source regeneration pass; see native_datum_create/reopen.json. The
headless reopen uses the native synchronous replay service because the live Replay
operator is deliberately modal. Live GUI evidence is recorded separately.

## Design

The base is 100 × 70 × 35 mm, with a 2.4 mm open-top Shell, four selected corner
fillets, selected bottom chamfers, seven bottom ventilation slots, two stiffeners,
four posts and four blind pilot bores. The 3.6 mm cover has four counterbores and
an integrated four-section hollow duct. Outer radii are 24/24/20/16 mm at
Z=-1/5/24/43 mm. Separate inner sections subtract a named 2 mm radial allowance.
Smooth interpolation is explicit; the allowance is not constant-normal thickness.
No generated Loft face is used as a persistent reference.

Primary mount centers are (7,7), (93,7), (7,63), (93,63) mm. Cover bores are 3.2 mm,
with 6.4 mm counterbores 1.6 mm deep. Base pilot diameter is 2.6 mm. These are
illustrative dimensions, not a fastener standard or proven fit. No hardware is
modeled. The 1 mm underside duct lip requires thoughtful print orientation/support.
STL coordinates are millimetres; STL itself does not store units.

## Editing without moving the mounting axes

Primary holes use ordinary datum-circle, extrusion and Cut features, not the
centroid-relative grouped Hole editor. Edit named parameters or the individual
features. This is deliberate construction intent, not a guessed face repair.

- Change width, depth and mount_edge in BOTH independent Part sources.
- mount_diameter, counterbore_diameter and counterbore_depth control the cover.
- pilot_diameter controls the base pilots. The mount_depth formula cover+1 ensures
  the ordinary bore tool extends beyond the cover in the tested construction.
- height controls the base. The assembly lid-seat frame is a named literal datum:
  explicitly change its Z coordinate to the new height, then update the sources.
  It is NOT automatically driven by a Part parameter.
- wall, vent_count and vent_pitch change the base. duct_middle and duct_wall change
  the cover's outer/inner Loft sections. Check current geometry after each edit.
- datum_three_mounts_edit.mcad.json demonstrates removing one mounting feature
  group. It has three bores and an intentionally unused fourth base post; no
  structural claim follows from that example.

Measured primary center error: nominal 0 mm; diameter changes approximately
7.1e-15 mm; simultaneous 110 × 76 × 40 mm dimensions and 8 mm edge offset
approximately 1.42e-14 mm. Final BRep cylindrical axes also coincide after both
diameter and size edits (not merely the input profile centers). Both sources were
edited consistently. The corresponding
assembly height datum was explicitly updated from 35 to 40 mm before checking the
edited assembled pose. These are bounded tested edits, not arbitrary-range proof.

## Intended contact is not a clearance pass

The lid is seated at Z=35 mm, with no artificial gap in the primary assembly.
The named base/lid requirement explicitly accepts the numerical contact band at
zero requested clearance. Replay admission is 1e-5 mm; query policy uses 1e-5 mm
linear tolerance and 1e-7 mm³ volume threshold. These are numerical settings,
NOT print allowances or certified error bounds.

The actual report remains complete, measured common volume 0, distance 0,
checked_with_threshold_contacts, and passed=false. The separate policy_accepted
flag is true. This allows the guarded STEP export without inventing a clearance
pass, proving exact contact, or promising no physical penetration. Other pairs
are not exempted. Any source/policy change requires a fresh check.

STEP readback contains two valid solids. Local-reference exact material volume is
80,306.528056 mm³, with nominal bounds [0,0,0] to [100,70,78] mm (about 1e-7 mm
numerical bounds expansion). Individual material volumes are 51,157.524557 and
29,149.003499 mm³. Ordinary global-origin inspection can differ slightly from the
kernel's local-reference exact-volume calculation; the latter is used for the
STEP comparison, not a relaxed geometric acceptance threshold.

The earlier ventilated_enclosure.step / .mcad-assembly.json deliberately use a
0.2 mm gap. They are retained as an explicitly labeled alternative only. The
strict seated experiment and its export refusal remain available separately.

## What this complex model exposed

1. Ruled duct/plate Union produced a valid raw Boolean but OCCT cleanup threw
   Courbes non jointives. The first retry proposal was rejected because failed
   cleanup can mutate shared operands. The reviewed 704ba38 correction isolates
   operands and composes proven copy ancestry. Both compact and full ruled repros
   now pass; see corrected_boolean_replay.json. The primary smooth duct remains a
   different design, not a disguised workaround or claim about ruled continuity.
2. Assembly Load's old 1e-6 mm default rejected native stored tolerances just above
   that value. Explicit persisted replay admission fixes the workflow; geometry and
   verification tolerances were not silently weakened.
3. Strict seated contact was correctly not a clearance pass. Explicit named-pair
   contact intent now permits export while preserving that measured distinction.
4. Successive grouped Hole centers follow changing support-face centroids. The
   original nominal model aligns, but the tested first-hole diameter edit shifts
   later centers by up to 0.041702 mm; the tested size edit shifts up to 5.899170 mm.
   This is documented local-frame behavior, not a broken topology identity guard.
   The primary datum-driven construction avoids it. Original sources and native
   workflow are retained for regression, not silently compensated at every edit.

Tessellation is checked at 0.1 mm deflection, including watertightness, consistent
orientation and vertex manifoldness. Invalid wall, invalid inner radius and
missing explicit blend identity refuse and block downstream geometry as intended.
Long-history interaction remains a development performance concern. No full-suite,
Windows, exhaustive UI, structural, airflow or manufacturing qualification is claimed.

## Bounded live usability evidence

The cloud Blender session opened the saved primary file, used the actual modal
Replay control, and changed Stale to Current. Check Pose and its confirmation
produced current evidence with Passed No, Contact policy accepted Yes, Complete
Yes and Threshold contact Yes. gui_contact_policy.png records the distinction.
Focus CAD and viewport/sidebar navigation were exercised. Check Pose required
several screens of sidebar scrolling, and long labels truncate at default width;
these are discoverability concerns, not additional geometry defects.

Harness mistakes were corrected and retained separately: comparing a float32
Blender display property against an exact-volume tolerance, unpacking a tuple
source-update return, and expecting a modal Replay operator to finish synchronously.
They are not counted as product bugs.

The separately editable base was also regenerated and checked in the live Part
workspace; gui_base_interior.png shows its vents, ribs/posts and Geometry Passed.
