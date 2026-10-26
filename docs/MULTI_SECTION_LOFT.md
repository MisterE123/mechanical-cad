# Explicit ordered multi-section Loft

Development feature, not a new installer or interactive GUI qualification.

## Workflow

Create and position closed sketches first. In Loft, retain **Two sections** for
legacy start/end behavior, or choose **Ordered section list**. The list starts
with those two profiles. **Add** appends the first unused available sketch
(change its dropdown as needed); it does nothing when no unused sketch exists.
Select a row and **Remove**, **Move up**, or **Move down**. Removing stops at two,
adding stops at sixteen, and moves stop at either end. Review the entire order
before Apply. Edit Feature restores the saved list and allows the same changes.
Switching back to Two sections explicitly replaces the list with the displayed
start/end choice. Apply commits only a successful whole Part replay; Cancel
leaves accepted intent unchanged.

Order is traversal, not merely display. The kernel never sorts by height or
proximity. Every section is a distinct profile feature with one valid filled
closed outer wire, no inner holes and no multiple regions. The authored planes
and orientation remain unchanged. OCCT may reconcile wire orientation/edge
correspondence; this is not a user-controlled seam mapping.

Ruled 0 requests OCCT smooth interpolation through the sections; Ruled 1 uses
ruled spans between consecutive sections. Smooth does not promise G2 continuity,
particular endpoint tangency or absence of overshoot. There are no guide curves,
point sections, periodic closing sections or seam/alignment controls. Incompatible
or invalid native construction is refused, as are disconnected/multiple solids
and volume at or below 1e-9 mm³. A valid native result is not certification of
aesthetics or manufacturing suitability.

## Canonical contract

The optional `loft_sections` field is exactly `{ "version": 1, "ports":
["section_1", "section_2", ...] }`, with 2–16 ports. The corresponding `inputs`
map contains exactly those profile dependencies. The port list, not JSON object
key order, defines traversal. The port sequence is explicit and validated; mixed legacy start/end inputs,
unknown versions/fields, duplicate profile IDs and missing ports refuse. Each
port's ordinal is a section position, never a persistent face identity.

Omission preserves the existing two-section start/end representation and replay
entrypoint. No legacy file is migrated automatically. Core immutable snapshots
and both Blender canonical-envelope validators retain the new intent exactly.
Typed replay consumes every section as a real profile output, not a mesh.
New Loft-generated faces remain unnamed; no nearest-geometry or enumeration-based
persistent topology claim is introduced.

## Focused evidence

- `tests/unit/test_loft_sections.py`: bounded versioned records, immutable round
  trips, native-free mirrored validators, explicit order, legacy omission and
  invalid/mixed/dependent inputs.
- `tests/integration/test_multi_section_loft.py`: exact three-section ruled volume,
  smooth validity, 2/16-section endpoints, middle-profile edit, reverse traversal,
  holes/solid-section rejection, zero-volume rejection, conservative topology,
  exact STEP export across typed v2/v3 boundaries and embedded assembly replay.
- `tests/blender_multi_section_loft_smoke.py`: native source-loaded creation,
  legacy omission, restored editing, list add/remove/move, duplicate rejection
  without mutation, order reversal, Save, independent reopen and upstream rebuild.
  Both processes passed with explicit markers on Linux Blender 5.2.2. The RNA
  scripting path supplies named collection rows; EXEC does not inject hidden
  default sections before an explicitly supplied collection.
- Existing Loft tests in `test_connected_solid_features.py` retain two-section
  smooth/ruled frustum volume and canonical replay coverage.

No broad-suite, Windows, installer or interactive GUI claim follows from these
focused checks. Interactive list presentation, actual pointer Apply/Cancel and
Undo/Redo remain GUI qualification work.
