# Canonical clevis hinge example

A reproducible backend example using the supported constrained-sketch → Part →
bounded rooted-tree assembly APIs. It does not establish GUI usability or physical
mechanical safety. The three editable Parts and accepted assembly retain the exact
canonical bytes of the independently verified 2026-10-16 baseline.

## Files and checking

- [`base.mcad.json`](../examples/clevis_hinge/base.mcad.json): clevis Part, schema 2
- [`leaf.mcad.json`](../examples/clevis_hinge/leaf.mcad.json): moving leaf Part, schema 2
- [`pin.mcad.json`](../examples/clevis_hinge/pin.mcad.json): plain pin Part, schema 2
- [`assembly.mcad-assembly.json`](../examples/clevis_hinge/assembly.mcad-assembly.json):
  assembly schema 1, embedding those exact Part revisions, explicit literal frames,
  joints and the selected named clearance preset
- [`generate_clevis_example.py`](../scripts/generate_clevis_example.py): deterministic
  canonical authorship, byte checking and optional full native evidence capture
- [`test_clevis_example.py`](../tests/integration/test_clevis_example.py): independent
  loading/analytic expectations, negative controls and generator contract checks

Run from the repository root with a suitable interpreter. The qualified dependency
versions are pinned in `pyproject.toml`; the native cases need OCP and libslvs.
An existing environment can be reused without reinstalling the project: explicitly
point `PYTHONPATH` to this checkout's `src`. For example, set `PYTHON` to its
interpreter path (or use this checkout's `.venv/bin/python`):

```sh
PYTHON=/path/to/qualified/environment/bin/python
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" "$PYTHON" -B scripts/generate_clevis_example.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" "$PYTHON" -B -m pytest -q tests/integration/test_clevis_example.py
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B -m ruff check --no-cache scripts/generate_clevis_example.py tests/integration/test_clevis_example.py
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B -m ruff format --check --no-cache scripts/generate_clevis_example.py tests/integration/test_clevis_example.py
```

The generator's default is **check-only**: author canonical model data in memory,
compare it byte-for-byte with the four checked-in files, and print their hashes and
current source provenance. It performs no geometry replay, creates no report
files, and does not rewrite the examples. This path also works without installed
native packages. Native tests carry the repository's `kernel` marker; they skip
when the required native dependencies are absent. The native-free identity,
kinematics, limit-rejection and generator-contract cases remain runnable.

### Optional external native evidence

Pass an explicit **new directory outside this checkout** to capture all 16 actual
sidecar request/response/process records, canonical copies, a full summary and
SHA-256 manifest. Existing directories are rejected, preserving previous runs.
Keep evidence outside other Git repositories too; no large native meshes, reports,
runtime environments or release binaries belong in source Git.

```sh
OUT="../clevis-evidence-$(git rev-parse --short HEAD)-$(date -u +%Y%m%dT%H%M%SZ)"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" "$PYTHON" -B scripts/generate_clevis_example.py \
  --require-clean --require-commit "$(git rev-parse HEAD)" --evidence-dir "$OUT"
(cd "$OUT" && sha256sum --check SHA256SUMS)
```

`--require-commit` accepts an exact full commit ID and is optional; no historical
HEAD is hard-coded. `--require-clean` rejects tracked changes and nonignored
untracked files. Without it, development runs are allowed but reported as
`dirty_unqualified` whenever either category is present. A clean tracked tree alone
is insufficient when newly authored sources are still untracked.

Provenance records the current commit, tracked-clean and full worktree-clean flags,
changed/untracked paths, a tracked-diff digest, a tree digest and per-file hashes
for tracked plus nonignored untracked files, generator hash, interpreter/platform,
installed distribution versions and imported package directory. File modes and
missing tracked files participate in the tree digest. Parent-process package/module
origins and the subprocess package origin are checked against this checkout;
every sidecar receives its explicit `src` search path. Full native summaries also
include the actual service/native runtime identifiers and numerical policy.
Source commit/tree/diff identity is rechecked before finalizing evidence.

The current code revision and current evidence capture time are separate from the
unchanged baseline model hashes. A post-integration run is new evidence, never a
replacement or relabeling of the original baseline. `clean_committed_tree` describes
source provenance only; it does not mean product, GUI or manufacturing qualification.

The generator only authors supported canonical data, invokes the real production
sidecar and checks results. It does not use prototype assembly evaluators, custom
fixture solids or an alternate geometry engine. Tests load the checked-in files
through `Document`/`AssemblyDocument`, derive their own analytic expectations, and
make negative variants through canonical parameter edits and typed replacements.
They neither import generator assertions nor depend on an external evidence bundle.

## What is actually modeled

All lengths are millimetres. All persisted assembly angles are radians.

The grounded clevis starts as a dimension-constrained 12 × 20 mm four-corner
rectangle on a literal XY plane with origin (−6, −12, −9), extruded 18 mm. The
rectangle has a fixed anchor, four horizontal/vertical edge relations and two
parameter-driven dimensions. A rectangular cutter makes a 10 mm opening between
two 4 mm cheeks, leaving a 5 mm-deep rear web at y = −12…−7. A radius-2.5 bore passes
through both cheeks along world +Z.

The leaf starts as a second dimension-constrained 8 × 20 mm four-corner rectangle
on a literal XY plane at (−4, −4, 0). Its thickness expression is
`slot_opening - 2 * side_gap = 9.5 mm`. A concentric radius-2.5 bore passes through it.
The fixed pin uses a primitive circle and extrusion: radius 2.3 mm, z = −10…10.

Both constrained sketches are solved by real libslvs 3.2 with zero remaining DoF.
Circle/slot primitives are supported engine features; this example does not claim
constrained circle authoring, arbitrary sketch tools, or a GUI-authored mechanism.
All three finished outputs are real canonical feature-history Parts, not mesh
imports or custom process-local solids. Each assembly output is explicitly `body`.
The production service freshly replays these sources and checks one-solid B-rep
validity and its existing mesh gate.

### Explicit tree and literal frames

- Root `base`: grounded at the identity placement
- Joint `hinge`: `base → leaf`, revolute about mate +Z, saved coordinate 0 rad,
  inclusive limits [−π/3, +π/3]
- Joint `pin_fixed`: `base → pin`, fixed, with the implicit zero coordinate
- Base frame `bore_axis`: identity at the bore's fork midplane
- Leaf frame `bore_midplane`: literal position (0, 0, 4.75), identity orientation
- Pin frame `pin_midplane`: identity at the pin midplane

The ±60° limits are authored kinematic bounds, not modeled physical stops.
The leaf's world z translation is −4.75 mm at the neutral pose, centering its
9.5 mm thickness inside the 10 mm opening. The leaf and pin do not have a second
joint between them: that would close a loop. The tree has one structural coordinate,
reported by `rooted_tree_joint_count`; it is not a general mate-solver rank.

Literal frames are explicitly authored numbers. They do not follow a later Part
edit. A regression changes leaf thickness to 9 mm through its canonical parameter,
then preflights an explicit source replacement. The old assembly remains unchanged,
all literal frame/joint/preset records remain unchanged, and the changed leaf's
minimum side gap stays 0.25 mm: its world span becomes −4.75…4.25, rather than
recentering to give two 0.5 mm gaps. Publication remains a separate caller action.
There are no cross-document parameter dependencies or automatic source updates.

The plain pin has no head or retaining clip. Its fixed joint is an explicit
kinematic idealization, not a modeled physical retention design. No contact/friction,
bearing behavior, fastener strength, or manufacturing process is represented.

## Engineering clearances versus numerical settings

Nominal geometric fit allowances:

- 0.20 mm radial bore-to-pin gap; equivalently 0.40 mm diametral difference
- 0.25 mm gap on each leaf side; slot 10 mm and leaf 9.5 mm

The selected `nominal_running_clearance` preset explicitly requires:

- Base ↔ leaf: minimum surface separation 0.20 mm
- Base ↔ pin: minimum surface separation 0.15 mm
- Leaf ↔ pin: minimum surface separation 0.15 mm

These illustrative engineering requirements deliberately leave margin below the
nominal dimensions. They are not a recommended fit class, tolerance stack-up,
allowable wear model, or a manufacturing certification.

Separately, the numerical policy is:

- Linear query tolerance: 0.000001 mm (1e−6)
- Common-volume tolerance: 0.000000001 mm³ (1e−9)
- Display tessellation deflection: 0.05 mm

Display tessellation is not the collision method. Pair checks use native B-reps.
The analytic regression comparison uses 1e−7 absolute tolerance (mm for distance,
mm³ for volume), with relative tolerance 1e−10 in the generator; it is a test
assertion tolerance, not another physical allowance. The tests use small
floating-point allowances when comparing rigid transform coordinates.

## Explicitly checked poses

The complete base coordinate map is always supplied: `hinge = 0`, `pin_fixed = 0`.
Sampling changes only `hinge`, retaining the fixed zero coordinate.

| Sample name | Degrees | Radians |
| --- | ---: | ---: |
| `negative_stop` | −60 | −1.0471975511965976 |
| `negative_forty` | −40 | −0.6981317007977318 |
| `negative_twenty` | −20 | −0.3490658503988659 |
| `neutral` | 0 | 0 |
| `positive_twenty` | 20 | 0.3490658503988659 |
| `positive_forty` | 40 | 0.6981317007977318 |
| `positive_stop` | 60 | 1.0471975511965976 |

All seven poses complete and satisfy the selected requirements. Each queries all
three unordered instance pairs, for 21 pair checks. At every sampled pose, base–leaf
gap is 0.25 mm, both pin gaps are 0.20 mm, and measured common volume is zero.
The separate neutral check also passes. This is evidence only for the listed poses;
the reports explicitly retain `continuous_collision_guarantee: false`.

## Analytical checks and negative controls

Volumes are independently derived from nominal feature dimensions:

- Clevis: 12 × 20 × 18 − 12 × 15 × 10 − π × 2.5² × 8
- Leaf: (8 × 20 − π × 2.5²) × 9.5
- Pin: π × 2.3² × 20

The cutter's extra 1 mm in +Y and 1 mm overshoot at each X edge are outside the
stock; its actual stock intersection is 12 × 15 × 10. The bore removes material
through 8 mm total cheek thickness, not the entire 18 mm height.

Negative controls remain separate request/response evidence; the three nominal
Part files and accepted nominal assembly are not overwritten with them:

1. Oversized pin: radius 2.6 mm via a deliberate −0.1 mm radial-gap parameter.
   Both pin pairs report known interference. Analytical overlap is
   π × (2.6² − 2.5²) × 8 for the clevis and
   π × (2.6² − 2.5²) × 9.5 for the leaf. These reports complete (`ok: true`) but
   fail the configured check (`passed: false`). A successful computation is not
   a successful clearance check.
2. Insufficient clearance: radius 2.4 mm gives a positive 0.1 mm gap, zero overlap,
   and a clearance violation of the named 0.15 mm requirements.
3. No selected preset: the saved preset still exists, but clearing the active
   selection yields `measurement_only` pairs and `passed: false`.
4. Beyond the motion stop: +61° fails closed before native source replay, preserves
   the requested value, returns no effective pose, and never clamps to +60°.
5. Engineering threshold equality: the same nominal geometry is checked against
   minima of 0.25 mm for base–leaf and 0.20 mm for both pin pairs. All pairs return
   `at_threshold`; the report is `checked_with_threshold_contacts`, complete but
   not passed. Equality within the numerical band does not establish a safe fit.
6. Near numerical contact: a 0.0000005 mm (5e−7 mm) radial gap is below the 1e−6 mm
   linear query tolerance. A separate explicitly named interference-only preset
   has zero engineering minimum; both pin pairs return `contact_or_near` and
   `at_threshold`. The report completes but does not pass. This diagnostic request
   does not relax or overwrite the nominal 0.15 mm engineering requirements.
7. Exact-fit contact: pin radius equals bore radius at 2.5 mm under that separate
   interference-only observation. Zero measured gap/common volume still returns
   `contact_or_near`, `at_threshold`, and no pass. Computational completeness is
   retained; these cases are not mislabeled as incomplete native queries.
8. Display-only assembly replay validates sources/placement but retains
   `passed: false`; it is not a clearance-verification request.

## Baseline provenance and limits

The original isolated verification was completed on **2026-10-16**, against code
commit `2419fc89cef578274bd8431c4f431bfc5afbe1b8`, with a verified import origin and
clean tracked source tree. Its independently retained full evidence is outside
source Git. That historical run completed 16 sidecar requests with empty stderr;
15 focused tests passed in 9.10 s; Ruff check/format and 53/53 artifact manifest
checks passed. The baseline runtime was CPython 3.12.14, OCP binding 8.0.1.1,
`cadquery-ocp-novtk` 8.0.1.1.0 and libslvs 3.2. A separate OCCT runtime build was not
exposed by the binding and was not guessed.

The canonical identities are deliberately unchanged:

| Canonical model | SHA-256 |
| --- | --- |
| Assembly | `8a59929cbe9b6f810641f24baa981a50dccdb88b874780e79472e1ccde2370a7` |
| Clevis Part | `db46fce5c0221ae395129b06cd05dc4d9433c6d68058678a49cdd198c74fe785` |
| Leaf Part | `5d8a0b005a6ab9eaddadf4dd52f122afd71883011aa76eae72259317a63bf96d` |
| Pin Part | `8571b305aa4763e0ee50d19917b32e2d0e172dc6f5f4e9f77ca553f2bc0f56e9` |

Nominal analytical/native volumes agreed within the stated assertion tolerance:
2362.92036732051 mm³ for the clevis, 1333.4679361931062 mm³ for the leaf, and
332.38050274980003 mm³ for the pin. All 21 sampled pair queries satisfied their
selected requirements. The negative controls completed with the expected failures
or threshold outcomes. These are the historical baseline observations, not a claim
that every later runtime has already been verified.

The separate literal-frame/source-update test is retained: an explicit changed
Part revision is preflighted without rewriting the original assembly or inventing
frame associativity. Generator contract tests additionally verify read-only default
behavior, current-HEAD provenance, tracked and untracked qualification gates,
foreign-import rejection, canonical drift, output location and overwrite safety.

This example does not qualify GUI authoring, installed ZIP behavior, source-publication
UI transactions, Windows/macOS, closed-loop mechanisms, continuous collision
avoidance, load/stress/fatigue, real fits, or physical safety. No assembly STEP/STL
export or fusion is performed. Native geometry outcomes are numerical and
runtime-dependent; canonical model bytes/hashes are deterministic, while bit-for-bit
native mesh/witness identity across platforms is not promised. See also
[the assembly workflow](ASSEMBLY_WORKFLOW.md), [the assembly service](ASSEMBLY_SERVICE.md)
and [verification limits](VERIFICATION.md).
