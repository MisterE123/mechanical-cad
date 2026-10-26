# Scene-only sketch annotation layout

`blender_addon/mechanical_cad_blender/sketch_annotation_store.py` is a pure,
strict codec for saved dimension-label placement. It does not create a Blender
property, edit an editor session, publish a Part, or own a scene transaction.
Those callers must explicitly store the successfully returned text.

The canonical Part feature graph remains unchanged. This metadata never stores
expressions, literal dimension values, geometry, solver evidence, a source hash,
or command-journal entries. Moving a label cannot change canonical source identity
or manufacturing meaning. The codec imports neither Blender, core CAD modules,
nor native libraries, and never invokes a process or solver.

## Version 1 format

```json
{
  "schema_version": 1,
  "kind": "sketch_annotation_layout",
  "documents": {
    "canonical Part document ID": {
      "sketch_feature_id": {
        "distance_constraint_id": {
          "kind": "distance",
          "refs": ["point_a", "point_b"],
          "display": "distance",
          "offset": [12.5, -4]
        },
        "radius_constraint_id": {
          "kind": "radius",
          "refs": ["circle_id"],
          "display": "radius",
          "offset": [3, 7.25]
        }
      }
    }
  }
}
```

The first key is the canonical Part document ID, not a Blender object name, a
source hash, or an assembly-instance ID. The second is the containing feature ID,
not the embedded sketch ID. Constraints and references use their stable IDs.
Identical feature/constraint names in separate Parts or features are independent.
Document IDs preserve all characters exactly, without trimming or Unicode
normalization. Their validation follows the Part's nonempty-text rule; whitespace
is not an automatic replacement for another identity.

Only `distance` and `radius` placements are supported. `display` must exactly match
`kind`. Distance references are two distinct point IDs in their original order;
radius references contain one circle ID. A constraint cannot reference itself.
`offset` is a signed `[u, v]` displacement in millimetres in the sketch's local
plane axes. The renderer owns the label's default anchor. Screen pixels, Blender
unit scale, and transformed world coordinates are not persisted here. This codec
does not itself implement a renderer or arbitrary-workplane editing.

All fields are required, and no additional fields are accepted. Empty nested
feature/document maps are allowed and consume their applicable count budgets.
The empty string is the explicit empty-store sentinel. Other non-JSON or
whitespace-only strings are errors, not an empty-store fallback.

## Public API

- `validate(raw) -> None` validates the entire saved store without a feature or
  sketch. An empty string is valid. This is suitable for preflight before a
  caller's scene transaction.
- `annotations_for(raw, document_id, feature_id, sketch) -> AnnotationLookup`
  validates the entire store and the supplied structural sketch definition. It
  accepts supported embedded sketch schemas 1 and 2 without migrating them. It
  validates expression storage, but never parses or evaluates expression text.
  The caller supplies the canonical owning IDs and the corresponding feature's
  sketch; the function cannot verify ownership from a standalone sketch object.
- `replace_annotations(raw, document_id, feature_id, annotations) -> str`
  validates and replaces exactly that feature's complete placement map. All
  unrelated documents/features remain semantically unchanged. The new complete
  store is validated and bounded before its serialized text is returned.

`AnnotationLookup` is frozen and exposes independently detached dictionaries:

- `annotations`: only compatible placements, directly matching the annotation
  dictionary shape in `GeneralSketchAuthoringState`.
- `unavailable`: constraint ID to frozen `AnnotationConflict`. Each conflict has
  `state` and a detached `binding` containing its complete original placement.
- `all_annotations`: all original placements, including unavailable records.

Every access returns fresh copies; changing an accessor's result cannot change
another result, the input sketch, or the saved text. No returned binding shares
mutable containers with caller input. Private dataclass backing fields are
implementation details.

### Compatibility and retention

A placement is available only when the current constraint has the same stable
ID, exact kind, and exact ordered references. `missing` means that stable ID is
absent. `changed` means its kind/references changed, or the ID now belongs to an
entity or workplane rather than a constraint. Reversed distance references are
conservatively `changed`; they are never silently remapped. A geometrically
identical new entity/constraint with a different ID does not heal a missing
binding. Exact restoration of the original signature makes it available again.

Changes to dimension values, expressions, coordinates, or workplane placement do
not invalidate an otherwise identical binding. These values are never used as
identity evidence. As elsewhere in the model, stable IDs must not be recycled for
unrelated identities. If an external producer reuses the same document, feature,
constraint, and reference IDs with the same signature, this layout-only format
cannot distinguish it from an intentional restoration; it has no historical
identity ledger or geometric fingerprint.

Lookup never edits or filters saved text. Incompatible entries remain recoverable
through `unavailable` and `all_annotations`; the caller should show their status.
To move compatible labels while retaining unavailable metadata:

```python
lookup = annotations_for(raw, document_id, feature_id, sketch)
replacement = lookup.all_annotations
replacement[constraint_id]["offset"] = [u, v]
candidate_text = replace_annotations(raw, document_id, feature_id, replacement)
# Publish candidate_text through the caller's transaction only after success.
```

The caller must check that the target is available before applying an ordinary
move, or explicitly authorize repair/replacement. `replace_annotations` checks
metadata shape, not historical relation provenance; it takes no sketch argument
and cannot independently prove where a binding originated.

Passing only `lookup.annotations` deliberately removes unavailable entries from
that feature. Passing `{}` explicitly removes that feature's placements and its
document map if it becomes empty. Both are caller-requested replacements, never
automatic cleanup. No records are evicted to make room, including stale records.

## Strict boundary and limits

The complete store has these limits:

- 2 MiB of UTF-8 text, on both read and write
- 128 documents
- 256 features per document, and 1,024 features in total
- 512 annotation placements per feature, and 4,096 in total
- Document IDs: 1–128 Unicode code points, encodable as valid UTF-8
- Feature/constraint/reference IDs: the existing ASCII stable-ID grammar,
  `[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}`
- Offset coordinates: finite JSON integers or floats in the inclusive range
  −1,000,000 to +1,000,000 mm; booleans and numeric strings are rejected

The byte budget can be reached before a count limit. Read parsing reuses the
shared strict JSON boundary: duplicate keys, nonfinite constants, overflowed
floats, numeric tokens longer than 128 characters, and nesting deeper than 32
are rejected. UTF-8 checking also rejects escaped lone Unicode surrogates.
Unknown versions, kinds, fields, and malformed unrelated records fail closed.
There is no implicit migration, alias resolution, or best-effort field removal.

Direct replacement objects are validated through a fixed-depth, count-bounded
schema before copying or encoding. Cyclic or shared mutable annotation containers
are rejected, including otherwise benign aliases; callers should provide ordinary
detached JSON trees. Large/deep malformed values cannot trigger unbounded
recursive traversal or exponential shared-tree expansion.

Successful serialization is deterministic compact JSON with sorted keys and
unescaped valid Unicode. Integer versus float offset types, finite float values,
negative floating zero, IDs, and ordered references are retained. A serialized
store read and replaced with `all_annotations` produces identical serialized
bytes. Existing noncanonical whitespace/key order may be canonicalized on a
successful replacement; unrelated records are preserved semantically, not as
individual raw substrings.

All public failures raise readable `AnnotationStoreError` (`ValueError`). Inputs
and saved text remain untouched. The caller must retain original text on failure
and publish no partial replacement. This pure API does not itself provide scene
compare-and-swap, Undo, file persistence, or a geometry/publication transaction.

## Verification

`tests/unit/test_sketch_annotation_store.py` covers isolation across two Parts and
two features, preserved unrelated records, exact round trips, detached/frozen
results, unchanged canonical source hash/geometry/formulas/command history,
missing and rebound bindings, explicit retention/removal, strict JSON failures,
invalid Unicode/nonfinite values, cyclic/shared-object hazards, count and byte
caps, atomic failures, and import with Blender/core/native libraries blocked.
These are pure codec tests. They do not establish Blender registration, scene
slot wiring, `.blend` reopening, viewport usability, or installed-package behavior.

## Blender publication and recovery

The scene's `mechanical_cad.sketch_annotation_json` stores this text separately
from `document_json`. Opening an existing general sketch restores only compatible
placements; unavailable bindings remain saved and produce a short recovery notice.
Resuming an unfinished draft uses its own exact UI snapshot instead of replacing
it with the last accepted layout.

Finish prepares a complete bounded replacement before native work. The Part
publication intent captures both the old layout text and its proposed replacement.
The completed response must still match the canonical scene, owner, workspace,
configuration, source bytes, and old layout. Canonical Part, display, and layout
then publish through the same rollback transaction. A layout write failure restores
the exact prior fields and display objects while retaining the editable draft.
A late external layout change blocks publication without overwriting that change.

Layout-only Finish preserves canonical Part bytes and native geometry identity.
Blender Undo/Redo restores accepted placements. Saving/reopening a `.blend`
preserves accepted layout and a separate suspended or failed draft. Standalone
`.mcad.json` files deliberately contain canonical design data only; these
scene-specific placements are not included in that format.

Reproduce the native publication, compound failure, Undo/Redo and separate-process
reopen gate from the repository root:

```sh
MCAD_ROOT="$PWD" MCAD_PYTHON="$PWD/.venv/bin/python" \
  "$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python tests/blender_sketch_annotation_smoke.py
```

`BLENDER` must name the tested Blender 5.2.2 executable. The script launches a
fresh process using that same executable and checks both success markers.

## Explicit Restore Sharp Corner retirement (unreleased)

A normal missing binding is still a warning. Restore Sharp Corner alone may add
this optional field to its exact required radius annotation, preserving every
original `kind`, `refs`, `display`, and `offset` value:

```json
"retirement": {"schema_version": 1, "reason": "restore_sharp_corner"}
```

The complete binding must be radius-kind, have one distinct stable target ID,
radius/diameter display and bounded finite offsets. Unknown fields, reasons,
versions, booleans as versions, reference annotations and other kinds fail closed.
The fixed-size nested object consumes the existing annotation/store count and
byte budgets. No expression, geometry, journal, or solve evidence is added.

A scene store containing the extension requires envelope version 2. Readers
continue to accept version 1 unchanged; ordinary writes remain version 1. Adding
retirement explicitly promotes the store to version 2, and subsequent writes do
not silently downgrade it. Older readers reject version 2. Draft UI2 uses the
same explicitly versioned optional binding extension; its strict old reader
rejects the additional field. UI1 rejects retirement. No canonical schema,
command opcode, native execution permission, or solver authority changes.

The binding is `retired` only when both its driver and target IDs are absent.
Any reappearing ID is `changed`, even with an equivalent signature: metadata is
not identity provenance and cannot silently heal a reused ID. Retired bindings
are retained in `all_annotations`/`unavailable`, but not compatible `annotations`.
They remain in the editor's stored UI and are excluded only from display and
conflict warnings; all other unavailable geometry and bindings still warn.
Collapsed Sketch details explains retained retired radius labels. Fully defined,
DoF, stale geometry and failure status remain in their usual main-panel locations.

Accepted Restore adds the marker through the detached authoring transaction.
Matching local Undo removes only that marker and restores exact original label
data; Redo adds it again. User-hidden labels are never recreated. Generic Delete
keeps its separate existing label-removal semantics. Resume retains the marker;
Finish publishes it atomically with layout and Part; reopening loads it without
requiring the discarded local journal. Explicit removal of a loaded retired
placement is not undone by merging the old accepted layout on Finish.

Retirement is saved historical UI intent, not proof of external provenance. A
strict reader can validate its shape and current identity absence but cannot
prove an external producer actually ran Restore. It does not reserve IDs or
change canonical geometry. Old unmarked missing entries are not automatically
reclassified, because there is no surviving evidence to justify that inference.

Pure tests cover exact label preservation, Undo/Redo, Resume, Finish-format
readback and reopening without command history, unknown/invalid metadata,
legacy-version isolation, user-hidden labels, and genuine missing/reused-ID
conflicts. These tests are not native Blender, GUI, ZIP-install, Windows, or
exhaustive release qualification.

### Bounded Linux lifecycle and GUI observation (2026-10-25)

Source-loaded Blender 5.2.2 passed the updated removal-owner smoke and separate
suspended-draft reopen checks. `blender_retired_annotation_finish_smoke.py` then
verified real Part-level Blender Undo/Redo: original exact canonical/layout1
bytes and active diameter placement return on Undo; exact sharp-corner source
and retired layout2 return on Redo. Finish followed by another Blender process
preserved those bytes and reopened the retired label without recovery warning
or inherited solve authority. All processes used `--python-exit-code 1`; explicit
success markers and zero exit codes were checked.

Actual cloud-desktop GUI input separately verified Resume and fresh Check,
Fully defined / 0 DoF and Current solved sketch with no incomplete-display or
missing-label warning, the collapsed retirement explanation, Ctrl-Z restoration
of the exact diameter label with offset `[4, 7]`, Ctrl-Shift-Z retirement, and
Finish rebuilding the consumed Part. The finished GUI file was saved under a
new name and independently read back in a fresh process, checking exact Part
and layout bytes. An unchanged legacy, unmarked missing-layout control still
showed its existing unavailable/retained notice when edited. That control was
not silently migrated and was closed without overwriting its source fixture.
The stricter missing-overlay and reused-ID collision cases were exercised by
pure renderer/codec tests, not additional interactive GUI actions.

Artifacts, logs, original suspended and finished GUI fixtures are retained in
`cad_engineering_evidence/retired_annotations_20261025` beside the source
worktrees. The GUI bootstrap only registers the source, arranges the view and
observes state; fixture authoring and the native lifecycle harness are scripted,
not represented as mouse-created geometry. One misdirected Save As text entry
went to the parent Blender window, was cancelled, and the Part view was restored;
the separately saved final file passed exact canonical/layout readback afterward.
No GUI result depends on that accidental input. Blender was closed cleanly.
These are bounded source-loaded Linux observations, not installed-ZIP, full-suite,
performance, or Windows qualification.
