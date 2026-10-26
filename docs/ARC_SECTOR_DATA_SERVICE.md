# Bounded sector data-only service

The bounded result-v3 service now solves and extrudes a constrained sector and
rebuilds it after a radius edit. The exact frozen source passed the service,
owner-rejection and full regression gates below. Version 0.5.2 remains the latest
usable release; this source milestone is not an add-on arc workflow.

## Practical example

`examples/sector_profile_data_only.mcad.json` contains one circular arc and two
radial lines, followed by one extrusion. Its shared point, line, arc, feature and
relation IDs are persistent. The center is fixed; horizontal/vertical relations
constrain the radii; the arc's radius relation retains the expression `radius`;
the extrusion retains the expression `height`.

The qualified service example solves and replays the document at radius
5 mm and height 10 mm, then changes only the canonical parameter `radius` to
7 mm and solves/replays again. Authored point seeds, expressions, relation IDs and
feature IDs remain unchanged. A successful native solve produces fresh solved
coordinates. A supported replay produces a new sector profile and extrusion.
Both solves report zero remaining degrees of freedom. The resulting valid
single solids have five faces and volumes 196.34954084936206 and
384.84510006474966 mm³, respectively. The resulting JSON and mesh are data,
with no production publication token.

An explicit protocol-1 `solve_sketch` request selects `result_version: 3`, the
complete Part document, and `feature_id: "profile"`. A Part `replay` request
selects `result_version: 3`, the complete document and the ordinary bounded
`linear_deflection` option. Part documents retain schema 1 or 2; only the embedded
sketch uses schema 3. A third Part schema is not introduced.

The dormant `service_v3.DataOnlyJob` composes the existing prepared request and
sidecar transport with strict result-3 receipt and inner-response validation.
Every operation has a fresh nonce. The captured backend selection is checked at
launch, poll and consumption, then again after validation. Cancellation/error
cleanup retains ownership until the child is reaped. No retry or replacement
backend is selected. This module is not imported by the live add-on entry point
or its owners; it is exercised through the isolated data-service harness.

## Supported geometry

- One arc plus exactly two radial lines, joined by shared endpoint IDs.
- Exact center-to-endpoint ray dot product at most zero in the solved sketch
  passed to profile construction; both arc directions are retained.
- Radius and extrusion height in the inclusive range 1–1000 mm.
- Exact necessary endpoint-discrepancy bound of 1e-9 mm, followed by the complete
  incidence/root/membership, native representation, trace and mass checks.
- Native sector replay accepts exact signed-permutation frames at zero world origin.
  Tested local center offsets are supported. Pure solve readiness does not
  pretend that a valid arbitrary plane is necessarily supported by native replay.

Coincidence-only joins, arc/chord segments, arbitrary multi-arc loops, holes and
other feature graphs are outside this service slice. Unsupported geometry stays
explicitly unsupported; authored coordinates are not rewritten to make it pass.

Canonical coordinates remain authored data. The qualified native adapter uses
an explicit, bounded mapping to canonical-circle endpoint representatives,
inside the fixed incidence cells, with one shared native vertex per endpoint
ID. See `ARC_SECTOR_NATIVE_MILESTONE.md` for the native projection policy and the
distinction between exact pure bounds and empirically qualified kernel mass
measurements. No service-specific tolerance widening is permitted.

## Solve, readiness and replay are distinct

A successful solve may have an unsupported profile. In that case the solve
remains successful, with truthful solved data and `profile_check.ready: false`.
It is not recast as a solver failure or an accepted open arc chain. A failed
solve supplies no usable DoF, solved geometry or readiness. Replay rejects an
unsupported sector or placement instead of constructing a different region.

Arc-empty schema-3 sketches retain the genuine original schema and use the
existing line/circle geometry behavior. Original embedded-schema-1/2 documents
and omitted/result-1/result-2 requests retain their prior behavior. The fixed
legacy differential corpus checks exact ordinary response bytes. Fresh guarded
receipts separately describe the actual selected backend and its capabilities;
those identity fields are not frozen historical responses. No result is
downgraded to fool a legacy validator.

## Conservative periodic-representation limit

A successful solve and pure sector readiness do not guarantee native replay.
The native adapter still requires its declared trim interval exactly. In a
retained service case, an unconstrained outward-seeded arc solved successfully
with five degrees of freedom to an exact quarter-sector. OCCT subsequently
returned the same-length interval shifted by exactly one stored binary64 turn.
The existing native field guard rejected that representation; the profile
failed and the extrusion was blocked, with the genuine solver report retained
and no mesh, topology or solid output.

That original required-positive attempt remains recorded as failed. It is not
counted as a successful test after changing its expectation. Separately declared
fixed-center/H/V controls constrain the intended branch, and the radius-edit
example also has a driving radius relation and zero remaining degrees of
freedom. Robust validation of alternative periodic native representations is a
later usability improvement, not part of this service qualification. No modulo
acceptance, tolerance relaxation, retry or geometry repair was added.

## Authority and unsupported actions

Result 3 supports only data-only sketch solve and Part replay. Geometry checks,
STEP/STL export actions, Assembly operations and canonical snapshots do not gain
result-3 support or capabilities. Unsupported guarded requests fail admission;
unsupported unguarded result-3 actions reject before ordinary action mutation.

The production `GuardedEvidence` boundary and Part, Rectangle, General and
Assembly publication/current-read paths remain v2-only. A valid result-3 packet,
including a legacy Rectangle solved through result 3, cannot grant production
current state, solved-position seeds, publication or export authority. Private
legacy-shaped data helpers are not a substitute for those owner gates.

## Qualification status

- Qualified prerequisite: bounded native sector milestone `30383a1`, including
  the original 70 positive cases and complete predeclared negative gates.
- Frozen final service source: 1,125 files; Ruff and formatting pass for 428
  Python files, with 4,282 focused unit controls and 35 native-free legacy
  comparisons.
- Actual final-source service gate: all 109 outcomes executed afresh. This is
  56 other focused outcomes, three exact historical Assembly rejection responses
  and 50 original legacy stdout/exit comparisons. No reused rows or unrun cases.
- The genuine radius-edit solves/replays, standalone profile display and selected
  profile display with a downstream extrusion all pass. Display tessellation is
  deferred until analytic construction and inspection finish; it cannot add
  display-only edge representations before the extrusion's retained-profile check.
- Production owner rejection: 36 controls pass using four genuine result-3
  packets (sector/Rectangle × solve/replay), plus a genuine result-2 positive
  control. Real owner methods are exercised with isolated native-free host ports;
  this is not Blender RNA or GUI qualification.
- Final Git-free full regression: 10,174 tests and 19,597 subtests passed in
  376.36 seconds, plus Ruff/format. All processes were collected. Fourteen bounded
  generated bytecode files were preserved separately and the exact source was
  restored. The existing non-failing pytest iterator-parametrization deprecation
  is retained.

The first service extrusion failure, the later underconstrained periodic-range
failure, and the first full regression's three failures remain separate retained
records. The Assembly repair restores its original bound version rejection;
the obsolete unknown-version fixture now uses 4 and adds an explicit version-3
positive. Existing wire assertions remain intact. Source-inventory tests verify
exact new/changed paths and restore the original bytes before their unchanged
historical digest; the qualified kernel and all current owner modules are exact.

## Frozen evidence anchors

- Service source manifest: 10bb96946af1e326ddf06983cc45c2772a51cd5148a4bd8bd19bcc65202aa9b3
- Fresh 109-case completion: 1b6048e7abda22ce7fd26f850ac8c23004cdb5f16c09b63637d0221048c77999
- Independent fresh service review: 3a4bc02dc818c003823787f436081b1d1e2faecd3e950fc35cc5f275b88888db
- Actual radius-edit packet: 413a1e50a3014381a9aa7cec6682ec8b3bb8118b0645e54307c97ce20dc9309c
- Full regression completion: 5d5c30be088b9249fe9c4479cb8f2d0675c1e5206590207b45539a6173923d7f

The companion evidence retains raw requests/responses, strict client validation,
process collection and pre/post source/runtime identities. Final coherent Git
source/archive correspondence is recorded by the independent extension. It is
not inferred from the unchanged release version literal.

No installed-ZIP or GUI arc qualification is claimed by these data-service gates.
