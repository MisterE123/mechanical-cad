# Extrusion end conditions (development)

Extrude Remove now offers **Through All** as a saved end condition. Choose Along
or Opposite sketch normal explicitly. It starts at the sketch plane and removes
through the selected target in that direction, not in both directions. A sketch
inside a body therefore removes only material ahead of its plane. A direction
away from the body fails visibly instead of silently succeeding.

The canonical `extrude_through` tool has `direction` (+1 or -1) and explicit
`profile` and `base` DAG inputs. On every replay, native exact B-rep bounds
conservatively size its temporary tool beyond the target. No tessellation, guessed
fixed depth or generated depth parameter is saved. Target thickness and attached
face/workplane changes are therefore reevaluated. The following ordinary Cut
retains its unchanged single-solid validity and measurable-removal checks.

Edit the Remove feature to change its profile, direction, target or end condition
between Blind and Through All. The same tool ID is retained. Shared tools require
explicit shared-edit consent. Tool and cut changes use one existing atomic Apply;
failed geometry or a stale dialog leaves the canonical model unchanged. A direct
edit of the Through All tool displays its end condition and explicit direction.

Existing one-sided `extrude` models and v1 responses for them are unchanged.
Through All is available for current ordinary/analytic planar profiles, including
supported face sketches and arbitrary normals. The specialized result-v3 sector-form
profile contract (one arc and two radial lines, including newly drawn sectors)
is rejected explicitly rather than bypassing its bounds. Stable
wall identities still require native one-image construction/boolean provenance;
ambiguous splits/merges remain unresolved. Through All does not use an end face; it is not Up to Next.

Evidence: `tests/integration/test_extrusion_through_all.py` checks exact volumes,
thickness changes, serialization, directions, rotated associative faces and real
v2/v3 sidecar evidence. `tests/blender_through_all_smoke.py` checks native Blender
Apply, linked edits, no fake depth in the dialog, failed-Apply rollback and
fresh-process `.blend` reopening. Headless checks do not establish interactive GUI
or packaged-installer qualification. Frozen release artifacts are unchanged.

## Symmetric / Mid-plane

Extrude Sketch and Add/Remove Extrusion also offer Symmetric / Mid-plane.
Depth is the **positive total depth**, with half on each side of the sketch plane.
The canonical `extrude_symmetric` feature stores the profile and total length
expression. It stays centered when the depth or sketch plane changes. Native
profile-copy translation and prism history retain only explicit one-image
boundary provenance; no extra user sketch or guessed offset parameter is saved.

Edit Feature switches a standalone or linked extrusion between Blind and
Symmetric, retaining the same feature identity and atomic rebuild behavior.
Through All remains Remove-only. Existing one-sided models are unchanged.
`test_extrusion_symmetric.py` checks exact centered bounds, volumes, direction,
current drawn circles and closed analytic arc loops through the real solver and
v3 transport. `blender_symmetric_extrusion_smoke.py` exercises native creation,
editing, invalid-depth rollback, saved intent and fresh-process reopening.

## Up to planar face

Extrude Sketch and Add/Remove Extrusion now offer **Up to planar face**. Choose
an explicit earlier target solid, then one stable planar face from that solid's
current exact face catalog. The target may differ from the Add/Remove base. The
dialog shows the exact solid/face identity and directly discloses the construction
assumption: **stop at the face's infinite supporting plane, not its finite
boundary**. It does not search for the next intersecting face or trim the profile
to the selected face outline. This deliberately permits an independent reference
body beside the modeled part.

The face must be parallel to the profile plane and ahead in the explicitly
selected Along/Opposite sketch-normal direction. Offset accepts millimetres or
an existing parameter formula. **Positive extends past the plane along travel;
negative stops short.** Offset may not rescue a face behind the sketch, and must
leave a positive reach. Wrong direction, curved/nonparallel, missing, split or
ambiguous faces fail visibly. No nearest-face substitution or hidden source
change occurs.

The backward-compatible canonical kind is `extrude_to_face`:

- `inputs`: exactly `profile` and `target`; target is an earlier solid feature.
- `params`: required literal numeric `direction` of +1 or -1; optional `offset`
  scalar/formula, default 0. No blind length or derived depth parameter is saved.
- `end_face`: required stable semantic ID, scoped to the exact target. Snapshot
  and pending IDs are not accepted.

Every native replay resolves that exact face and computes directed distance from
the actual profile and target planes. Source-position, profile-workplane and
parameter changes therefore recompute the extrusion. The resulting cap and walls
use the ordinary prism's proven construction provenance, owned by the extrusion;
the end cap does **not** inherit the target's face identity. Legacy records,
serialization and expression meaning remain unchanged. Older readers reject the
new kind rather than converting it to a frozen blind extrusion. Assembly sources
using this end condition require full result-3 replay evidence.

Creation uses the existing detached cyan exact preview. Changing target, face,
direction or offset invalidates prior preview evidence; Cancel cannot publish it.
Apply performs fresh exact replay and one atomic publication. Edit Feature shows
the saved source/face/direction/offset, including on linked Add/Remove. It can
switch the same standalone tool between Blind, Symmetric and Up to planar face,
or switch linked tools among those modes and Remove-only Through All. Shared
tools retain explicit shared-edit consent. Editing uses the existing atomic
whole-document rebuild, not a new live editor preview. Untouched formulas and
numeric types are preserved; changing this tool does not rewrite project
parameter definitions.

Limits: only ordinary supported planar profiles and parallel stable planar end
faces; the specialized result-3 sector-form profile remains explicitly rejected,
as for Symmetric/Through All. End-face selection is the existing stable face
catalog dropdown, not a new viewport click-to-face workflow. No Up to Next,
nonparallel/curved-face termination, finite-face trimming, general ambiguous
reference recovery or automatic migration is claimed.

Evidence: `tests/integration/test_extrusion_up_to_face.py` asserts exact geometry,
source edits, signed offsets, exact source qualification, real split rejection,
rotated planes, linked Add/Remove, persistence and native/client/assembly gates.
`tests/unit/test_up_to_face_contracts.py` covers strict native-free contracts and
adversarial evidence. `tests/blender_up_to_face_smoke.py` covers actual operators,
no-op precision/formulas, visible controls, failed-Apply preservation, and a
second-process `.blend` reopen. `tests/blender_up_to_face_preview_smoke.py` covers
fresh exact preview, input invalidation, cancellation, stale context and Apply.
These are source-loaded native headless checks, not GUI or installer qualification.


A successful upstream feature/sketch edit that breaks only supported references
can be retained as an unapplied proposal. **Replace End Face** explicitly chooses
another earlier stable parallel face without changing direction, offset or
profile. Cancel keeps the proposed edit; full successful replay is required to
accept it. See [staged repair](STAGED_EDIT_REPAIR.md#explicit-up-to-face-end-reference-repair).
Missing or split targets are still failures until this explicit correction; the
logical sketch-plane split rule is not applied to extrusion termination.
