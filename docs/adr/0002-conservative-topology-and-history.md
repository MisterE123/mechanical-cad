# ADR 0002: Persistent semantic references must fail closed

Status: accepted for the experimental 0.1 slice, 2026-10-16.

A face's mesh index, OCCT enumeration position or nearest geometric signature is
not stable design identity. A valid regenerated solid can still carry the wrong
downstream design intent if references are silently rebound.

Use construction provenance (stable feature ID and semantic role) only when the
adapter explicitly marks it stable. Preserve exact and unambiguous operation
lineage conservatively. A split, merge, missing entity or unknown lineage is a
structured unresolved result, even if one candidate happens to look close.
Geometry may rank visible suggestions, which require an explicit correction.
Keep tests in the hierarchical regression catalog; planned cases never count as
passing tests. Store no resolved face index as a canonical design reference.

Version 0.1 exposes and tests this resolver foundation but does not yet let a user
attach a sketch or fillet to an arbitrary picked face. The supported feature graph
uses whole-profile/whole-solid IDs. Face-level authoring must wait for real workflow
regressions and explicit ambiguity UI.

Separate software Git history, saved feature DAGs and session Undo. Any future
Git-backed model history is opt-in, revision-aware and never writes to an external
user repository without authorization.


## Ordinary Cut tool-face extension (2026-10-23)

A single Cut can propagate an authored stable tool face when native Modified
history, or exact unchanged IsSame identity with no deletion, has one output face
and that output has one source. IsSame ignores orientation deliberately: the tool
surface becomes an oppositely oriented cavity wall. Geometry signatures and face
normals are regenerated from the output, never copied from the tool. Explicit
`tool_modified` / `tool_unchanged` provenance distinguishes this from base ancestry.
Tool IDs shared with base ancestry are not promoted. Generated-only, split,
merged, unknown and patterned histories remain unresolved. Full Part transport
checks the actual tool source, status, identity and one-image evidence before a
picked blend or planar-face reference may consume it. Native tests cover bounded
through/blind holes, edits, selected blends and failure cases; no general naming
or interactive GUI qualification is implied.

Cut tool-face lineage is enabled for typed result v2/v3 replay only. Omitted
or explicit result v1 retains its historical snapshot-only tool-wall output.

## Transient single-click blend edges (2026-10-23 development)

The opt-in `edge_catalog` sidecar action is separately guarded by
`mcad.edge-catalog/1`; omitted/v1 and ordinary v2/v3 replay schemas do not change.
Its exact-input response includes a freshly validated typed replay plus bounded
native display polylines with explicit adjacent stable face IDs. OCCT IsSame
adjacency, not coordinates or tessellation diagonals, establishes the pair. Only
one native shared edge, exactly two distinct stable adjacent faces, and supported
line/circle curves are admitted. Seams, degeneracies, multiple shared edges,
unstable references and unsupported curves are omitted.

The transient viewport picker binds that replay to the current accepted Part,
validates the entire displayed mesh, rejects modified/stale/instanced geometry,
and revalidates retained guarded evidence on click. Screen proximity only picks
among these native catalog entries; ray-cast visibility and a distance margin
reject hidden or ambiguous targets. A pick stores only the existing face-pair
blend intent, which the kernel resolves again on replay. No persistent edge ID,
new saved model field, or general naming claim is introduced. Two-face picking
and advanced named/all-edge dialogs remain available.


## Explicit planar Shell opening (2026-10-23 development)

Shell's optional `opening_faces` is an immutable list containing exactly one
stable semantic face ID in this slice. Omission retains the old closed-cavity
serialization and native operation. The open path resolves only unique stable
retained face provenance and checks planarity before passing the actual native
face to `MakeThickSolidByJoin`. A real split or deleted lid cannot be rebound to
another current face. No heuristic or stored mesh index resolves the opening.

The viewport picker reuses the existing exact document/display binding and
acceptance-time evidence guard, then hands a stable face to the atomic Shell
dialog. Thickness expressions and the opening survive Edit Feature and save/reopen.
Open Shell does not promote newly created wall/rim topology into stable identities.
Tests establish native geometry and headless operators, not interactive GUI or
installed-package qualification. Legacy closed-shell snapshot face/triangulation
ordering already varies between unchanged native runs; no ordering change is
introduced as part of this feature.


### Open Shell outer-face extension

A non-opening stable input face may retain its ID only when the open Shell output
has exactly one IsSame face, the source is not deleted, Modified is empty, and no
other source's IsSame/Modified/Generated ancestry claims that output. Duplicate
source identities also fail closed. Generated offset walls are new surfaces, not
identity images of the surviving outside face; the removed lid's Modified rim is
explicitly excluded. Only this unchanged outer identity gets image_count=1.

Strict clients require an authored open shell, unchanged/stable one-to-one source
provenance, a non-opening source ID and exact source signature equality in full
Part replay. Sketch and mate-frame resolution reuse that stable outside identity.
Closed Shell continues to publish snapshot-only topology without this branch.
Native tests cover exact IsSame ancestry, thickness/dimension edits, attached side
sketches, supported mate workplanes, ambiguous source refusal and forged evidence.

## Selected blend surface construction (2026-10-23 development)

Typed v2/v3 replay can expose `blend.surface` owned by a selected-edge Fillet or
Chamfer feature. This is a newly constructed surface, not the identity of either
neighboring face. The authored face pair must resolve to exactly one native edge;
OCCT Generated(edge) must have exactly one output face, with no inherited-face or
other edge/vertex Generated claim. Missing, split, tangent-chain shared, competing
and all-edge histories retain snapshot-only generated faces. Legacy v1 is unchanged.
The transport checks the saved pair, stable source membership and single-image
provenance. Neither geometry similarity nor an enumeration index chooses identity.

The semantic intent is “the surface created by this feature's selected edge”.
Editing that selection intentionally retargets its downstream surface; editing
size follows the regenerated surface. The face picker and in-app blend Help
explain this and point to Edit Feature for correction. A planar chamfer can support
a face sketch; a curved fillet cannot. Supported straight/full-circle boundary
references may use the new face together with an adjacent stable face, still
subject to unique native adjacency and strict endpoint identity. No general
fillet-chain, imported-face or automatic ambiguous-reference repair is claimed.

## Explicit logical-plane intent exception (2026-10-23 development)

The original fail-closed rule remains the face-identity contract. A separate,
versioned construction-intent rule now lets constrained face sketches preserve
the original logical plane across a complete same-source ordinary Cut split.
All descendants must be coplanar, consistently oriented, native-history-backed,
and bound to the current stable source in the Cut base. No descendant is selected
or promoted to a stable identity. The saved anchor is transported relative to
the current original stable source workplane using its established projected-world-axis
frame convention, not arbitrary rigid/material-spin matching. Width, position and
normal changes are covered where this source is proven. Missing source or inconsistent
planes still require correction. The common plane may span removed material.

New UI-authored face sketches visibly default to this saved intent; legacy records
remain strict. Why/change-selection controls and ordinary Undo make the assumption
inspectable and correctable. A strict edit that would fail still follows atomic
valid-candidate commit rules, requiring a valid replacement or cancellation.
This is a deliberate response to the user's instruction to act on reasonable,
visible, correctable intent, not a generic heuristic-to-stable conversion.

Full rule, field semantics, refusal cases and native/client evidence:
[MCAD-TNP-SUPPORT-001](../regressions/topology/support/MCAD-TNP-SUPPORT-001.md).


### Placement continuity before and after a split

Preserve-plane intent also applies to a proven one-image Modified/unchanged Cut
face. Stable face identity does not override the separately saved placement
policy: otherwise an asymmetric cut's changing centroid could drag the sketch
before it splits, then jump back on split. Decision evidence distinguishes
`identity_status: stable|split` from the assumed `preserve_plane` frame policy.
Legacy Strict is unchanged. Native notch 10→14→22→14→10 mm regression verifies
a saved nonzero source-relative anchor throughout, including save/replay.
Legacy world-axis orientation retains its historical threshold discontinuity.
The explicit saved-tangent policy below addresses that separate frame-intent
case without inferring material spin.
## Feature-owned open Shell inner walls and lip (2026-10-23 development)

Typed v2/v3 replay exposes an inner offset face only when one stable non-opening
source face has exactly one native Generated output face and no Modified output.
The opening's lip instead requires exactly one Modified output and no Generated
output. Every source face participates in collision checks, including unknown
sources: duplicate IDs, multiple images, shared source claims and an unchanged
outer-face identity reject promotion. Closed Shell and legacy v1 keep their
existing behavior. Retained outside faces still use the separate IsSame rule.

Each new surface belongs to the Shell feature. Inner-wall roles encode
`shell.inner.` plus SHA-256 of the complete semantic source ID. The one lip has
the explicit `shell.opening_lip` role, meaning the lip of this Shell's current
selected opening. Both retain the source ID, relation and counts in provenance. The digest is a collision-resistant
encoding of authored identity, never a hash of geometry or a face index. This
keeps nested modifiers' names bounded and unambiguous. Native-free clients bind
it to the authored opening, current base source, stable ancestry and one image.

The intention is the offset of the named source face, or lip of the named opening,
under the current Shell thickness. Size/thickness edits follow that construction;
deliberately changing the opening moves the same lip intent to the new opening.
Inner-wall identities still depend on their original source face. Picker feedback and Shell Help
explain how Edit Feature changes it. Actual planarity gates face sketches; actual
line/full-circle adjacency and endpoint signatures gate projections. No nearest
surface search, general offset naming or ambiguous-source recovery is claimed.


### Explicit baseline-relative minimal-twist orientation

New Preserve logical plane authoring saves a source tangent. The frame follows
the shortest rotation between saved and current source normals, avoiding the
old projected-world-axis threshold switch. This is a visible construction
assumption, not material spin or cumulative path integration. Existing records
without orientation retain the historical convention, and Strict is unchanged.
Near-antiparallel normals refuse because no reliable unique rotation axis exists.
Review Support permits World axes or a deliberate current-frame reset with a
movement warning. Native topology remains unchanged; only the independently
validated logical sketch frame carries the transported tangent. See case 002.
## Explicit projected-reference replacement (development)

The bounded history editor may replace one saved construction reference with a
fresh same-source, same-analytic-kind selection. It retains authored target and
constraint identities, and evaluates only that reference's managed drivers.
Optional boolean `reverse` on line projection rows records explicit endpoint
correspondence; canonical native endpoint signatures are not reordered or relaxed.
Full replay still rejects changed signatures and publication still requires the
whole Part to succeed. Read-only upstream closure permits review when a downstream
reference fails. See [workflow and limits](../PROJECTION_REFERENCE_REPAIR.md).

## Feature-owned hole-pattern occurrence surfaces (2026-10-23 development)

Typed v2/v3 Linear/Circular Hole Pattern may own `pattern.copy.<zero-based index>.<source-ID SHA-256>`.
The index is the authored placement ordinal, never native face enumeration or a
nearest physical hole. The existing saved pattern specifies placement; downstream
face references save occurrence/source intent. Native transform and composed Cut
history must prove one stable source, one Modified/unchanged image and no competing
claims. Intersecting cutters conservatively exclude both occurrences. Splits,
missing occurrences, generated-only history and unknown sources are not promoted.
Legacy v1 and fused whole-solid patterns are unchanged. Circular count/sweep edits
can move the same occurrence; reducing Count removes later references rather than
rebinding them. Human labels and pattern Help explain this correctable assumption.
See [MCAD-TNP-PATTERN-001](../regressions/topology/pattern/MCAD-TNP-PATTERN-001.md).


## Explicit parallel face-plane extrusion termination

`extrude_to_face` saves an exact earlier solid input and stable semantic end-face
ID. Native replay requires one stable planar face parallel to the profile and
ahead in the selected normal direction. The visible assumption is that the face
supplies an infinite construction plane; its finite boundary is not used. A
travel-relative offset is independent saved formula intent. This does not relax
face identity or use preserve-plane split intent: missing, split and ambiguous
end faces require correction. The prism's cap/wall names remain owned by the
extrusion's actual construction, never inherited from the selected target face.
See [end-condition contract](../EXTRUSION_END_CONDITIONS.md).

## Source-bound successive Cut workplanes (development)

New preserve-plane capture additionally saves the authored source-feature ID for
its source signature. Complete native Modified/unchanged/deleted ledgers may then
compose across consecutive ordinary Cut base operations. All input faces, tool
claims and surviving fragments participate at every step; ambiguous/generated
claims, aliases, incomplete survival, noncoplanarity and unsupported operations
refuse. Partial deletion is permitted only with explicit native deletion evidence;
full source-plane disappearance refuses. No descendant gains a stable face ID.

Ledgers and their snapshot IDs remain request-local typed replay evidence. Only
the authored feature binding is saved, avoiding ambiguity about which older Cut
centroid supplied the baseline. Unbound legacy records retain immediate-source
semantics without automatic migration. Existing review controls disclose and
correct the assumption. See [case 003](../regressions/topology/support/MCAD-TNP-SUPPORT-003.md).


## Explicit staged extrusion-end correction

Only known Up to Face target-reference gates receive a repairable typed error;
unexpected native failures are not recategorized. A user may explicitly replace
one failed `extrude_to_face` target solid and stable semantic end face within a
retained edit proposal. The catalog is derived from current guarded replay and
preserves the authored direction/offset/profile. It excludes later/descendant
sources, nonparallel, unstable and invalid-reach choices. No heuristic suggestion
or silent binding is used. The infinite-plane assumption remains visible.

Partial progress requires successful native evaluation of that extrusion; only
full successful Part replay publishes the proposal. The initial failed graph
bounds downstream eligibility if retargeting severs the original dependency,
not geometric identity. Existing bounded intent-only Save/Resume/Undo carries the
ordinary authored fields and freshly validates all states. No new persisted
native or face-snapshot authority, identity promotion or general recovery claim.
See [MCAD-TNP-END-001](../regressions/topology/end_face/MCAD-TNP-END-001.md).

## Multiple explicit planar Shell openings (2026-10-24 development)

`opening_faces` accepts 1–64 distinct stable planar IDs. Every ID resolves against
all source descriptors, then requires one stable native face. The entire request
fails if any identity is missing, split, ambiguous, aliased or nonplanar. There is
no subset fallback or nearest-face repair. Native B-rep validation and full-Part
atomic publication remain unchanged.

For multiple openings, a uniquely proven Modified rim is named by
`shell.opening_lip.<sha256(source ID)>`, so enumeration
or selection order cannot exchange rim identity. Existing singleton lips retain
`shell.opening_lip`, and closed cavities retain their
old operation. Moving between singleton and multiple modes can require explicit
repair of downstream lip references; no migration or inferred rebinding occurs.
See [workflow, evidence and limits](../MULTIPLE_SHELL_OPENINGS.md).

## Explicit multiple-edge blend sets (development)

Fillet and Chamfer optionally save `edge_pairs`, a canonical bounded set of
stable semantic face pairs. Every pair resolves to one unique native shared
edge before constructing a blend; duplicate native edges and any unresolved
member fail the complete operation. The field is mutually exclusive with legacy
`edge_faces`; omission keeps historical all-edge intent. No persistent edge
index or nearest-geometry repair is introduced. Typed multi-edge generated surfaces now require one native Generated(selected
edge) image and no other input face/edge/vertex claim, including unknown faces.
Each multiple-selection role hashes canonical JSON of the complete sorted face
pair, not native enumeration or geometry. Singleton selection preserves
`blend.surface`; larger sets use `blend.surface.<pair digest>`. Thus switching
single/multiple modes requires explicit reference repair; a removed pair never
rebinds to another selected edge. Split, merged, shared-chain and competing
histories stay unnamed. Legacy v1 and legacy single-edge behavior are unchanged. See
[MULTIPLE_EDGE_BLENDS](../MULTIPLE_EDGE_BLENDS.md) for workflow and limits.


## Explicit reflected solid (2026-10-24 development)

Mirror Result is a canonical unary solid feature with a world-space plane origin
and normal. Native OCCT reflection copies exactly one solid; the source remains
history, not an implicit second body or automatic fuse. The existing modifier
ledger preserves only proven one-to-one Modified images of already-stable source
faces, with output signatures recomputed. Previously split/unknown identities
remain unresolved. Client validators bind that evidence to the actual source.
Planar output normals account for an indirect UV frame after reflection rather
than assuming the plane axis is the oriented surface normal. This preserves
outward sketch-support intent; semantic role names remain authored source roles,
not current world-space extrema. See MIRROR_RESULT.md and its native tests.

## Isolated Boolean cleanup recovery (2026-10-24 development)

Union and Intersection run on a native deep copy of the combined operand graph,
including curves and surfaces. The compound preserves shared topology; its Add
operation's temporary child Free flag is restored immediately. Original operands
and their remembered provenance remain the authoritative source. Every source
face must have exactly one distinct native Copy Modified image, agree with
ModifiedShape, belong to its copied operand, and have no deletion, Generated or
competing copy claim. No face enumeration or geometric matching establishes this
map. The existing Boolean lineage gates consume copied native faces with their
original source descriptors; split, generated, merged and aliased identities are
not promoted.

If optional SimplifyResult raises Standard_Failure, discard that entire builder,
copy graph and history, then repeat the exact Boolean on new deep copies of the
original inputs, without cleanup. Initial build, retry, validity and single-solid
failures still fail the feature. Other cleanup exceptions propagate. Successful
cleanup remains enabled. This is not a general native-error recovery mechanism.
The bounded duct regression checks original serialized B-reps remain identical
through a real cleanup failure, and verifies the retry receives pristine distinct
copies. Focused tests cover normal geometry/lineage, failed retries, disconnected
results, and refusal of missing, split or generated ancestry.
