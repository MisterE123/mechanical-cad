# MCAD-TNP-SUPPORT-003: Source-bound workplanes through successive Cuts

Status: implemented bounded construction intent, not general face naming.
Search: TNP, successive cuts, multi-stage split, coplanar fragments, deletion,
source workplane, saved anchor, strict support, native ancestry.

## Visible intention

New face-sketch authoring still defaults to Preserve logical plane / Minimal
twist. It additionally binds the saved source frame to an authored feature ID.
Two or three successive ordinary Cuts may trim, split and remove pieces of the
original planar face without dragging the sketch to a fragment's centroid.
The existing Plane assumed / Review Support explanation reports the Cut count,
retains the warning that the plane can span removed material, and offers Strict,
another support, World axes and deliberate frame reset. No fragment is selected
or given a stable identity, including when only one split descendant survives.

## Canonical versus request-local data

The optional `support_intent.source_feature` is the stable authored feature ID
which supplied `source_signature`. It requires that saved planar source signature.
The existing semantic `support_face` names the stable source face at that feature.
New capture walks only the continuous Cut base path back to this proven stable
source, preserving the actual chosen face centroid as the saved anchor and the
original source centroid as its frame baseline. No centroid is used to identify
or rank a face. Both records and the feature ID survive immutable JSON save/replay.

The feature binding is necessary: an older record's saved source signature might
belong to an immediately preceding, already trimmed Cut, not the earliest original
face. Older records without this binding therefore retain their existing exact
and immediate-source single-Cut semantics. They are not silently reinterpreted,
rebaselined or upgraded on review, orientation changes, or unchanged Apply.
Legacy Strict remains Strict. Explicit repair of an old split reference adopts
a current source plane with the existing no-historical-anchor disclosure; where
its immediate base is also split, that explicit repair can establish the new
source binding after proving the complete chain.

Every typed v2/v3 Cut result carries a separate request-only `cut_ancestry` ledger:
version 1 and one record for every face of both current input catalogs. Each record
contains `port`, `source_id`, native `deleted`, and independent lists `modified`,
`generated`, `unchanged` of current output topology handles. Native IsSame binds
all images. Unchanged requires IsSame and not IsDeleted. Modified and Generated
claims are not prioritized or discarded when both exist. Catalog omissions or
aliases fail closed. Result v1 and existing face descriptors remain unchanged.

Snapshot handles occur only inside a freshly replayed, exact-request-bound
ledger. They never enter a model, saved support, authority cache or chosen-face
record. Full Part and solve-only clients independently validate every ledger's
exact base/tool membership, complete source coverage, output membership, unique
handles, bounds and agreement with inherited topology. The pure chain rule is
mirrored byte-for-byte; no OCP import enters Blender.

## Complete chain rule

1. The bound feature must be reached solely through ordinary Cut base edges.
   The source must currently contain exactly one stable planar source face.
2. At every step account for every previously surviving fragment. Keep only
   native Modified or unchanged images with exactly that one source claim.
   A branch with no image is permitted only with explicit native IsDeleted.
3. Include all base and tool sources in collision checks. Reject Generated claims,
   merged images, competing origins and aliased source identities, even when a
   competing solid ancestor's identity has since disappeared. Solid base/tool
   ancestry counts as aliasing; a separately constructed cutter merely using a
   face-supported profile does not inherit that face identity.
4. At least one descendant must survive every Cut. Check every intermediate and
   final descendant is planar, consistently oriented and coplanar with the current
   bound original source. Use the existing 1e-7 normal-distance and millimetre
   coplanarity tolerances, not a proximity score.
5. Transport the saved source-relative anchor and optional minimal-twist tangent
   using that bound original source frame. Partial removal never changes the
   anchor. A final sole fragment stays snapshot-only if its predecessor was split.

Missing survivors, unknown deletion, generated-only ancestry, mixed sources,
noncoplanarity, unsupported intervening modifiers or full plane disappearance
stop support resolution. There is no fallback to the largest/nearest fragment,
a coincident new surface, a tool-generated replacement plane, or saved world data.
Other consumers (blend selections, projections, mates, Shell and Up to Face)
continue to require their own strict stable identities.

## Prepared GUI fixture

[`two_cut_source_bound.mcad.json`](../../../../examples/topology_support/two_cut_source_bound.mcad.json)
is an accepted two-slot plate with a downstream face sketch, boss and final Union.
Change named `plate_width` from 20 to 24 mm: the workplane origin should move from
(10, 10, 10) to (12, 10, 10), while the supporting body's volume changes from 3760
to 4560 mm³. The final Union adds 8π mm³. The [fixture guide](../../../../examples/topology_support/TWO_CUT_SOURCE_BOUND.md)
provides review/cancel steps and exact expectations for separate GUI qualification.

## Evidence and limits

- `tests/integration/test_cut_ancestry_ledger.py`: exact native source/image
  relations for all operands; successive splits, native partial deletion, tool
  ancestry, independent competing relations, bounded missing/aliased catalog
  refusal, and request-local handle reordering.
- `tests/integration/test_cut_chain_support.py`: two/three Cuts, edited dimensions,
  exact volumes, saved nonzero offsets, partial removal, complete disappearance,
  Strict/legacy behavior, fresh-process save/replay, full client and solve-context
  validation, malformed/forged ancestry, new capture and review corrections.
- Existing `test_split_support_intent.py`, `test_support_orientation_intent.py`
  and support-intent unit contracts remain relevant unchanged legacy evidence.

These are native/headless contracts, not GUI interaction, installed-package,
all-operation TNP, manufacturing or arbitrary material-spin qualification.
