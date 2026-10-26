# Parametric printable spur gears (bounded prototype)

`spur_gear` is a native solid-producing feature, with no inputs. Its canonical
numeric parameters accept the same bounded arithmetic expressions as other
features and survive history edits, JSON save/replay and solid STEP/STL export.
Geometry is rebuilt in the OCCT sidecar; Blender never imports OCP. Tooth zero
is centered on +X; the axis is +Z and material occupies z=0 through thickness.

Required parameters: `module` in mm, integer `tooth_count`, `thickness` in mm.
Defaults: `pressure_angle=20` degrees, `bore_diameter=0` mm, `backlash=0.1` mm,
`clearance=0.25`, `profile_tolerance=0.01` mm. Clearance is a dimensionless module
multiplier, NOT a length. Backlash is this gear's pitch-circle tooth-thickness
reduction, NOT the pair total. At standard center distance, a pair's nominal
circular backlash is the sum of the two reductions. Neither is axial clearance.

## Geometry and limits

Unshifted, external, full-depth straight spur gears only. With module m, teeth z,
pressure angle a, pitch radius rp=mz/2, base radius rb=rp cos(a), tip radius
ra=rp+m and root radius rr=rp-m(1+clearance). Circular pitch is pi*m; pitch tooth
thickness is pi*m/2-backlash. Involute parameter t=sqrt((r/rb)^2-1), involute angle
is t-atan(t), and half tooth angle at radius r is pitch_thickness/(2rp) + tan(a)-a
minus that involute angle. Angles in these formulae are radians.

We conservatively require z >= ceil(2/sin(a)^2): 18 teeth at 20 degrees, not 17.
This rejects undercut designs instead of pretending to implement profile shift
or a cutter-generated root. Module is 0.1–100 mm; z <= 200; angle 14.5–30 degrees;
thickness 0.1–1000 mm; reduction 0–0.5m; clearance 0–0.5m. Bore leaves at least
one module of radial material after profile error. This is a geometry guard,
NOT a load-bearing design rule. Thin/pointed tips and overlapping tooth sectors
are rejected. A conservative 6000-segment legacy polygon preflight remains in
place; the curved constructor also rejects profiles exceeding 6000 native edges.

Below the base circle each flank extends radially to the root circle. This is
NOT a trochoidal generated root or fillet. Root corners are sharp. No hub,
keyway, helical, internal, bevel, rack, shifted, or undercut gears are supported.
A supported pair needs matching module/pressure angle and correct phase and
center spacing; geometry alone does not certify a pair's contact performance.

## Approximation, precision and topology

The output is a valid watertight OCCT B-rep with cubic Bezier approximations of
the involute flanks and analytic circular tip/root arcs and bore. It is NOT an
exact analytic involute gear. STEP retains the cubic curves and circles. STL
additionally has ordinary export mesh and binary rounding errors; choose its
tessellation independently. Canonical parameters and saved document schemas are
unchanged. Fresh replay now produces curved flanks within the authored tolerance
instead of the older polygon; exact old face counts, volumes and mesh bytes are
not retained. The legacy polygon sampler remains an independent reference.

`profile_tolerance` is between 0.0001 mm and min(0.1 mm,0.05m). Each span [a,b]
uses cubic Hermite interpolation of vector involute
f(t)=rb*(cos(t)+t*sin(t), sin(t)-t*cos(t)) and its endpoint derivatives.
Bezier poles are f(a), f(a)+(b-a)f'(a)/3, f(b)-(b-a)f'(b)/3, f(b).
The pitch parameter tan(alpha) is always an exact span endpoint, preserving
the authored pitch-circle tooth thickness when backlash is edited.

The internal accuracy budget is min(profile_tolerance, max(1e-6 mm, backlash/10)),
where backlash is the **per-gear** reduction. This only refines the requested
upper bound near nominal contact. It is not a minimum measurable clearance or
contact guarantee. Very small-backlash profiles may have more spans and take
longer than ordinary printable pairs. A coarser cubic prototype failed a sampled
zero-backlash overlap check; that result was not accepted.

For completeness, f''''(t)=rb*(-3cos(t)+t sin(t), -3sin(t)-t cos(t)), so
M=max||f''''||=rb*sqrt(9+b^2). Cubic Hermite has a **vector** positional bound
M*(b-a)^4/384. Separate scalar mean-value remainders in each coordinate would
not justify this norm bound. On normalized u,s in [0,1], its Peano kernel is

```
K(u,s) = s^2(1-u)^2 [3u-(1+2u)s]/6       if s <= u
         u^2(1-s)^2 [(3-2u)s-u]/6       if s >= u
```

Both branches are nonnegative. The integral over s is u^2(1-u)^2/24 <= 1/384.
Apply the triangle inequality to (b-a)^4 integral K(u,s) f''''(a+(b-a)s) ds.
This proves the vector norm bound, including the base-circle endpoint where
f'(0)=0. Each actual subdivided interval is rechecked before native work;
tests independently evaluate dense vector errors and the kernel integral.
Analytic tip/root arcs and straight below-base joins have no curve approximation
error. The bound concerns nominal 2D construction before floating-point/native
tolerances, not printer accuracy, volume accuracy, contact or surface finish.

Ordered positive X/Y control points and polar angles prove each canonical Bezier
flank increases radius and angle within its endpoint cone. Bernstein's positive
weights preserve this order; rotation/reflection preserve the geometry. Ordered
tooth sectors and strictly positive tip/root gap angles make the closed profile
simple; failed control-polygon proofs reject the design. OCCT then validates the
face and single solid. Only start/end
caps and the bore have stable face IDs, proven by prism construction history.
Flank segment faces deliberately remain snapshot-local/unknown: changing tooth
count or subdivision must not silently guess a persistent face identity.

For printing, export in millimetres, calibrate bore fit/backlash for the printer
and material, and prototype a pair before use. Material, orientation, layer
height, shrinkage, wear, lubrication and duty cycle are not modeled. No strength,
load capacity, noise, durability, fit, safety-critical, or contact guarantee.

## Sources and implementation provenance

Formula references (consulted 2026-10-23):
- KHK manufacturer gear-dimension reference:
  https://khkgears.net/new/gear_knowledge/gear_technical_reference/calculation_gear_dimensions.html
- Jönköping University Applied Mechanics, spur gears (involute and conservative
  no-undercut derivation): https://mechanics.ju.se/MachineElements/spur-gears.html
- KG STOCK GEARS manufacturer technical data (undercut discussion):
  https://www.kggear.co.jp/en/wp-content/themes/bizvektor-global-edition/pdf/TechnicalData_KGSTOCKGEARS.pdf
- NIST DLMF, interpolation (background; vector kernel derivation is above):
  https://dlmf.nist.gov/3.3
- OCCT native Bezier curve construction:
  https://occt3d.com/dev/doc/refman/html/class_geom___bezier_curve.html

FOSS precedent surveyed: FreeCAD Gears https://github.com/looooo/freecad.gears,
whose repository declares GPL-3.0. No source code from that implementation is
copied, vendored or executed, and FreeCAD is not a runtime dependency. This is
an original implementation of the formulae and interpolation bound above,
under this repository's GPL-3.0-or-later license. Existing OCCT dependency and
its notices remain unchanged.
