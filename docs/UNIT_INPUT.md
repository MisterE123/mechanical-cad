# Typed lengths and angles

Current-source UI support, not a new canonical formula language or release receipt.

Known length text fields accept one decimal/scientific number with `mm`, `cm`,
`m`, `in` or `ft`: `10 mm`, `2cm`, `1e-3 m`, `1 in`, `-2 ft`.
Known angle text fields accept `deg` or `rad`: `45 deg`, `1 rad`.
Both also accept integer fractions with explicit units: `1/8 in`, `1 1/2 in`,
`-1 1/2 in`, `1/2 deg` or `1/2 rad`.
Suffixes are lowercase; spaces before a suffix are optional. Signs and zero are
parsed, then the existing field's positivity and range checks still apply.

## Fraction grammar

A fraction is `[sign]numerator/denominator unit`; a mixed number is
`[sign]whole numerator/denominator unit`. All three components are unsigned ASCII
integers. The optional leading `+` or `-` applies to the entire quantity, so
`-1 1/2 in` means minus 1.5 inches, not minus 0.5 inches. Denominators must be
positive. A mixed number's fraction must be proper (`0 <= numerator < denominator`);
`1 3/2 in` is rejected rather than guessed. Simple improper fractions such as
`3/2 in` are accepted. Zero and leading zeros are allowed, subject to field bounds.

Spaces or tabs are allowed around `/`, before the suffix and at either end; at
least one space or tab separates the whole part from its fraction. No internal
newlines, Unicode spaces, decimal/exponent components, signed denominators,
parentheses or additional arithmetic are accepted as fractional unit literals.
The explicit lowercase supported suffix is mandatory. Bare `1/2` remains the
existing formula text in formula-capable fields and is still rejected in pending
Line/Circle creation fields, which only accept literals.

## Where this works

- Pending Line length and Circle diameter after Tab, subject to their existing
  positive literal bounds and fresh owner/solver acceptance gates.
- Rectangle Sketch width/height and general-sketch distance, radius, diameter and
  driving angle input, including editing existing dimension labels.
- Part text-field dimensions in create/edit dialogs: extrusion depths and planar
  end offsets, face-profile sizes/offsets/angle, radii, chamfers, shell thickness,
  transforms, pattern spacing/angles and revolve dimensions. Sweep placement roll
  accepts angle literals, but not named formulas, as before.
- Assembly joint coordinates/limits and samples, mate-frame XYZ and XYZ rotations,
  gear phase, clearance distance and linear verification tolerances. Assembly
  fields remain numeric-only, not parameter-formula fields.

Lengths become millimetres and Part/sketch angles become degrees. Assembly angles
pass through the existing degrees-to-radians conversion exactly once. Saved
features and drivers contain the normalized number, not a unit expression; no
schema migration is required. Editing an unchanged value preserves its original
numeric precision/type or exact formula text.

## Deliberate limits

This first slice accepts **one number and one unit**, not dimensional arithmetic:
`width + 2 mm`, `1 in + 2 cm`, `2 * (5 mm)` and compound units are rejected.
Existing formulas such as `width / 2` are unchanged, using the field's existing
units. A parameter named `mm` remains a parameter: `2 * mm` is a legacy formula,
not multiplication by a unit.

Global project parameters have no declared physical dimension. Their ordinary
Formula fields retain the existing unit conventions and do **not** accept unit
suffixes. Counts, ratios, direction vectors, flags and quaternion components are
unitless. Volume tolerances remain bare cubic-millimetre numbers. Legacy
numeric-only primitive widgets do not gain unit-text support; use their existing
numeric input or the supported text-field editing workflow.

Wrong dimensions (`45 deg` in a depth), mixed/unknown units, nonfinite unit values
and normalized magnitudes above 1e12 fail rather than guessing. Existing tighter
limits still apply. Failed draft input stays available for correction, and a
failed committed edit does not publish partial geometry.

## Bounded fractional-input evidence

Pure focused tests cover parser grammar, signs, all suffixes, invalid fractions,
field bounds, unchanged source types/precision/formulas and detached candidates.
The pending Line and Circle tests retain rejected `1/0 in` through local-recovery
encoding and restore, then correct to `1/8 in`. The Line candidate's distance is
3.175 mm; the Circle candidate's canonical radius and radius driver are 1.5875 mm
(diameter halved once), with diameter display retained. Snapshot round-trip and
Undo/Redo retain these values. Candidate preparation does not create solver
proof or mutate the live draft. Existing owner and fresh solve gates are unchanged.

These are pure draft/parser demonstrations, not native solver, Blender GUI,
installed-archive or platform qualification. No canonical schema, parameter
language, unit preference or legacy numeric-widget change is introduced.

### Prepared Blender checks (not an execution receipt)

`tests/blender_fractional_unit_smoke.py` is a bounded source-loaded registered-owner
fixture. Run separate Blender processes with `MCAD_FRACTION_PHASE=save`, then
`resume`, one `MCAD_FRACTION_BLEND` path, source `MCAD_ROOT`, sidecar
`MCAD_PYTHON`, workspace-local `TMPDIR`, and `--python-exit-code 1`.
The expected terminal markers are `FRACTION_UNIT_SAVE_OK` and
`FRACTION_UNIT_RESUME_OK`. It types through the input controller, checks fresh
native solved geometry, preserves an exact legacy formula, and saves/reopens a
rejected pending raw value without restoring runtime acceptance authority.
Preparation or a successful static compile is not proof that these markers ran.

`scripts/blender_fractional_units_gui.py` prepares ordinary interactive source
sketch UI and writes observation-only `current.json` to
`MCAD_FRACTION_GUI_OUTPUT`. After the shared GUI slot is explicitly granted:

1. Start Line, pick its first point, move to a nonzero direction and press Tab.
   Type `1/0 in`, press Enter, and inspect the retained error/text and geometry.
   Correct to `1/8in`; verify the solved distance is 3.175 mm.
2. Start Circle away from the line, pick its center and press Tab. Repeat invalid
   denominator and correction; verify diameter 3.175 mm, radius 1.5875 mm and
   diameter annotation. Capture actual field/error/result screenshots.
3. Check Undo/Redo and ordinary save/reopen. An unfinished field must Resume
   with exact raw text but require fresh acceptance. Optional
   `MCAD_FRACTION_GUI_BLEND` opens the saved file for explicit UI Resume.

The watcher observes state; it does not simulate mouse/keyboard events, accept
geometry, or turn scripted owner assertions into an interactive GUI claim.

### Source verification, 2026-10-25

The bounded fixtures above were executed with source parser commit
`96cd1f8ca37bae6fe3f801515aa9b7b480844df5` plus prepared harness commit
`652251bcab7e9a0501f4ef3678ccabe32cb989ce` and the harness-only corrections
recorded alongside this receipt. Blender was Linux 5.2.2 LTS, hash `d13f752e3b9c`.
Both separate background processes exited successfully with
`FRACTION_UNIT_SAVE_OK` and `FRACTION_UNIT_RESUME_OK`.

Actual cloud GUI mouse/key interaction verified pending Line and Circle input:
`1/0 in` retained the failed raw field and proposal without adding geometry;
select-all correction to `1/8in` created a solved Line at 3.175 mm and a Circle
at diameter 3.175 mm, canonical radius 1.5875 mm. The GUI showed both dimension
labels and the radius value. Circle Undo removed only the Circle; Redo restored
it. Ordinary Save As preserved the draft, both GUI processes closed normally,
and fresh-process reopening presented a suspended draft. Explicit Resume showed
unverified orange geometry; Check restored solved blue geometry and the same
values. The combined open Line/Circle sketch correctly reports unavailable
profile boundary; this is dimensional-authoring evidence, not an extrusion test.

The native owner fixture separately checks valid legacy formula `width / 2`
without rewriting it. An initial fixture attempt used leading whitespace in that
formula and failed the existing canonical arithmetic evaluator; the fixture was
corrected rather than changing formula semantics. A first shell GUI launch had
no display environment; the actual GUI was then launched from the cloud desktop
terminal. Neither attempt is counted as a successful run.

The observation-only watcher's initial line distance used Blender's float32
`Vector`, displaying 3.1749991829938664 in its JSON despite the exact canonical
3.175. The watcher now uses Python `math.dist`; after reopen the solved distance
was 3.1750000000000007 and the circle radius 1.5875. This correction affects only
test observations, not geometry or parsing.

Evidence retained outside Git under `cad_engineering_evidence/fractional_units_20261025`:
- `save.log` / `resume.log`, native two-process `fractions.blend` and JSON fixture.
- `fraction-gui.blend`, `gui.log` / `gui-reopen.log`.
- `gui/` invalid/solved screenshots and JSON observations, Undo/Redo observations,
  saved screenshot, and reopen suspended/unverified/freshly-solved screenshots.

SHA-256 of native `fractions.blend`:
`b11fd874a6f4269fe4817ddadbbee64f9cf2e51298b90e100c3477d05e5cd3b8`.
SHA-256 of interactive `fraction-gui.blend`:
`11db397cd5efdba4299619631f21d1aa6653091e8d83203aa02599efaeaa5a27`.

Focused pure verification: 333 tests plus 113 subtests passed, changed-file Ruff
and diff checks passed. This is source-loaded bounded Linux evidence only, not
an installed archive receipt, full historical-suite run, Windows qualification,
new release or exhaustive GUI proof. Existing numeric widgets and formulas keep
their original semantics; acceptance still requires the existing fresh gates.
