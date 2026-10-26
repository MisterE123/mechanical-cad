# Closed sketch regions and holes

Development support now includes multiple closed line loops and analytic circles
in schema-2 sketches and arc-empty schema-3 sketches. Draw an outside contour and
inside circles or closed line contours, then Finish and Extrude as usual. Interior
boundaries become actual through-holes; a nested contour alternates filled/empty
by nesting depth. The rule does not depend on drawing direction or record order.

Examples supported by the real solver/replay/kernel path:
- A rectangular mounting plate with multiple circular holes.
- A rectangular enclosure wall with an inner rectangular opening.
- A washer/annulus with a dimension-driven outside radius and a bore.

Shared point IDs or explicit coincidence relations close line boundaries. Merely
placing separate endpoints at the same coordinates does not join them. Crossing,
overlapping and touching loops are rejected explicitly, including tangent circles
and a circle touching the outside contour. Boundary entity IDs are preserved as
side-face provenance when extruding, including hole walls.

All closed regions are selected by the sketch's even/odd fill rule. A disjoint
sketch or nested solid island can be saved/displayed, but the current Part replay
requires exactly one connected solid per feature. Extruding those disconnected
regions reports `unsupported_solid_count`; it never silently picks a region.
Individual-region selection remains separate work. General mixed line/arc
boundaries are described below; existing supported single-sector behavior remains.

The focused checks cover pure classification, native-free result validation,
actual OCCT volumes and hole side-face roles, negative native extrusion, and saved
parametric schema-2/schema-3 annulus replay/edit. They are not GUI qualification or
a claim of a complete 1.0 CAD release.

## General mixed analytic curves

Schema-3 sketches now also support closed mixed line/arc contours, including
semicircle-and-chord shapes, rounded plates/capsules, major arcs, multiple arc
contours, and analytic circles as interior holes. Geometry remains exact OCCT
circular arcs rather than tessellated polygon substitutes. Endpoint identity and
explicit coincidence determine connectivity. An arc must have consistent endpoint
radii; crossing, overlap and nonadjacent contact fail explicitly. Ordinary closed
curves use the same nesting rule and preserve line/arc/circle authored side roles.

The generic analytic path handles construction curves by excluding them from
profiles while retaining them in solved sketch data. The historical certified
single-sector path is retained for its original source form; generic profiles
have their own distinct `analytic_regions` output kind and strict bridge checks.
The pure analytic classifier is vendored identically into the native-free add-on;
a source-equality regression prevents the two trust-boundary copies drifting.

Actual focused checks cover a rounded plate with a circular bore, saved solver
replay, editable bore size, downstream solid transform, arbitrary workplane, and
STEP export. These checks do not replace actual Blender interaction testing.
