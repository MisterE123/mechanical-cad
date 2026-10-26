# ADR 0005: versioned sketch capabilities and typed evaluated outputs

Status: accepted for the next development slice; not a released UI capability.

## Decision

Keep Part schemas 1 and 2 and the embedded sketch schema-1 default unchanged.
New line/circle authoring explicitly opts into embedded sketch schema 2. Its
required `circles` list contains stable IDs, point-center references and numeric
radius seeds. A radius dimension is one authored constraint; its native compiler
uses a diameter internally without creating a second saved driving dimension.
Migration preserves authored IDs, expressions, order-independent identity and seeds.
Unknown embedded versions fail explicitly.

A successful sketch solve and an available extrusion profile are different facts.
The process-local output algebra therefore distinguishes `SketchOutput`,
`ProfileOutput` and `SolidOutput`. A sketch has either `AvailableProfile` with a
real kernel face or `OpenProfile` with a specific reason and no shape. The legacy
`Replay.shapes` projection contains actual handles only. Failed and blocked
features never publish an output. Native handles remain inside the sidecar.

The first supported incomplete region is one connected, nondegenerate,
nonintersecting, unbranched line chain. Other region-policy failures retain real
successful solver evidence but do not become a successful open output. This is a
bounded region policy, not a limitation of the solver's mathematical constraint
vocabulary. An underconstrained supported region can succeed with its true DoF.

A dependent extrusion requests the profile port. An open input blocks it with
`profile_unavailable`, while the sketch itself remains valid. An active open sketch
cannot pass geometry checks or export: it returns `not_a_solid`, preserves prior
files, and has no volume. A valid independent active solid can still export.

## Wire compatibility

The process envelope remains protocol 1. Replay/check/export request an explicit
`result_version: 2` to receive typed output discriminants. Omitted or explicit 1
retains the legacy result contract for legacy data. Embedded schema-2 data cannot
silently downgrade; requesting legacy output fails with an upgrade explanation.
Unknown versions fail before native geometry work. New-result responses echo the
version at the envelope and replay levels.

`solve_sketch` is a separate explicit action requiring result version 2, a detached
candidate document and selected constrained feature ID. It resolves the same
project expressions, calls libslvs and performs a pure region readiness check.
It does not import OCCT, replay downstream geometry, write files or commit drafts.
The complete request fingerprint binds omitted/default/numeric-type differences.
Successful solve plus an unavailable profile remains an `ok` solve response;
failed solve has no solved data, DoF or profile readiness result.

The new request path applies bounded JSON-tree and original numeric-token guards.
Legacy accepted numeric spellings and serializer/hash behavior stay unchanged.
Blender-side validators are native-free, strict, source-bound evidence checks;
they do not pretend to independently reproduce the native solver or OCCT.

## Geometry and identity

A circle is analytic, built on its explicit normalized temporary workplane. Local
+U is its parameter-zero seam convention. The authored quaternion is unchanged.
Only actual construction history supports `side.circle.<entity-id>` and cap face
roles. The seam convention is not a persistent seam-edge reference. Existing
primitive circle role `side.circle` is unchanged.

## Publication and remaining integration

New independent open sketches may be committed only after successful solving and
full replay. Editing a consumed sketch into an open profile keeps the recoverable
draft and blocks Finish with its dependent-feature explanation. Publication must
retain existing exact-base, Undo, stale-cache and save/reopen guarantees.

At this core milestone the released rectangle UI remains unchanged. General
entity editing, direct native dimension UI, typed sketch display and new-result
assembly reuse require separately qualified integration. Existing assembly wire
responses remain legacy; unsupported new source replay fails closed until its
versioned evidence negotiation is implemented. No general sketch editor, arbitrary
multi-region selector, closed-loop assembly solver or manufacturing certification
is claimed by this ADR.

## Open analytic path extension

Result version 3 now admits validated planar nonbranching open line/arc chains
as the existing unavailable-profile sketch output (`open_profile`). They remain
non-extrudable. Sweep consumes the genuine solved sketch and constructs exact
trimmed circular edges. Check and replay independently classify connectivity,
coincidence, intersections and degeneracy using the same native-free geometry
policy in core and Blender. Closed-region readiness is never inferred from
successful path admission. Existing canonical schema and expressions are unchanged.
