"""Current feature help shared by modal editors; plain data, no native imports."""

_COMMON = [
    "Dimensions accept numbers or named parameter formulas. Apply rebuilds the complete dependent history; a failed result leaves the preceding model unchanged.",
    "Edit Feature changes saved inputs and dimensions. Blender Edit Mode changes only a display mesh and is not a parametric CAD edit.",
]

_DESCRIPTIONS = {
    "extrude": (
        "Extrude",
        "Choose a closed profile, Depth in millimetres and direction. Normal follows the sketch normal; Reverse runs opposite. Advanced signed depth supports formulas. Up to planar face instead uses an explicit stable earlier face plane and offset, with the same controls in Add/Remove. This creates a solid, not an automatic join or cut.",
    ),
    "extrude_symmetric": (
        "Symmetric / Mid-plane Extrusion",
        "Enter a positive total depth. Half is extruded on each side of the authored sketch plane. Edit Feature retains this centered intent as depth or plane changes. The total is not a per-side distance.",
    ),
    "extrude_through": (
        "Through All Extrusion",
        "Remove extends from the sketch plane in the selected direction through the chosen target solid on every rebuild. It follows thickness changes without a depth formula. This is one-sided, not both directions. Edit the Remove feature to change the end condition, direction or profile; failed Apply leaves the model unchanged.",
    ),
    "extrude_to_face": (
        "Up to planar face",
        "Choose an explicit earlier target solid and one stable planar face, parallel to the profile plane. The extrusion stops at the face's infinite supporting plane, not its finite boundary. Along or Opposite defines travel direction; the target must be ahead. Offset is a formula in millimetres: positive extends past the plane along travel, negative stops short. The exact target and face are saved and reevaluated after source edits. Missing, split, ambiguous, nonparallel or behind-direction faces fail without guessing another face. The resulting cap belongs to the extrusion, not the target. Available for standalone Extrude and linked Add/Remove. Creation has exact cyan preview; Apply and editing rebuild atomically and Cancel preserves accepted geometry. If an upstream edit breaks this target, Replace End Face in the retained proposal chooses an explicit earlier solid and valid parallel face while preserving profile, direction and offset. Cancel keeps that unapplied edit; Discard abandons it. Only full successful replay accepts the repairs. Not Up to Next, curved-face trimming or a universal naming solution.",
    ),
    "union": (
        "Union / Add",
        "Choose Base and Tool solids. They must touch or overlap so the result is one connected solid. For a sketch boss, Extrude Add creates its depth and join together.",
    ),
    "cut": (
        "Cut / Remove",
        "Subtract the Tool solid from Base. Place the tool where material must be removed. Extrude Remove creates depth and cut together. A standard outward face sketch defaults inward; offset or flipped planes require an explicit direction. Edit Feature also exposes linked extrusion depth.",
    ),
    "intersection": (
        "Intersection",
        "Keep only material shared by Base and Tool. An empty or disconnected result cannot be accepted as one Part.",
    ),
    "revolve": (
        "Revolve",
        "Rotate a closed profile around a world-space axis. XYZ gives axis origin; Axis XYZ its direction. Angle is degrees. A full revolution has no artificial start/end caps.",
    ),
    "fillet": (
        "Fillet",
        "Hover a supported edge, click once, then enter Radius in millimetres. Shift-click starts an explicit edge set on one body; further clicks toggle, Enter reviews, and Esc cancels. One size applies to every selected edge and any invalid member rejects the entire operation. Edit Feature → Reselect replaces the complete set. Each uniquely proven generated surface follows its saved face pair across size edits. Removing that pair removes its reference; switching between single and multiple selection modes may require explicit reference repair. Shared tangent-chain, corner and ambiguous surfaces remain unnamed. F switches to single-edge two-face selection; advanced all-edge and named-face choices remain. Apply checks exact adjacency. Unsupported or ambiguous faces are not guessed, and an excessive radius fails without a partial blend. A single selected edge can own one proven generated blend surface, reusable for supported edge references. Curved fillets are not planar sketch supports. All-edge or ambiguous generated surfaces remain unavailable. Edit the blend selection to change its intent.",
    ),
    "chamfer": (
        "Chamfer",
        "Hover a supported edge, click once, then enter Distance in millimetres. Shift-click starts an explicit edge set on one body; further clicks toggle, Enter reviews, and Esc cancels. One size applies to every selected edge and any invalid member rejects the entire operation. Edit Feature → Reselect replaces the complete set. Each uniquely proven generated surface follows its saved face pair across size edits. Removing that pair removes its reference; switching between single and multiple selection modes may require explicit reference repair. Shared tangent-chain, corner and ambiguous surfaces remain unnamed. F switches to single-edge two-face selection; advanced all-edge and named-face choices remain. If an upstream change makes the selected faces ambiguous, repair the selection explicitly. A single selected edge can own one proven generated bevel surface: click its planar face to attach a sketch, or use its supported boundary edges as references. It follows the selected edge and Distance on rebuild. Edit the blend selection to retarget it. All-edge or ambiguous generated surfaces remain unavailable.",
    ),
    "mirror": (
        "Mirror Result",
        "Choose XY, XZ or YZ and enter the signed Offset in millimetres or a formula. Choose Custom plane for an arbitrary nonzero normal and origin. Opening or drawing the dialog preserves authored expressions; selecting a preset explicitly changes the normal. Only the reflected solid is the result: the original remains editable history, not a second body. No fusion, negative mesh scale, or inferred face selection. Edit Feature changes the plane or source; Cancel leaves the original unchanged.",
    ),
    "transform": (
        "Move / Rotate",
        "Rotate about world X, Y, Z in that order, then translate XYZ in millimetres. This is an editable feature, not a free Blender object transform.",
    ),
    "linear_pattern": (
        "Linear Solid Pattern",
        "Repeat and fuse the whole solid using the XYZ spacing vector. Count includes the original. Copies must join into one Part; use Linear Hole Pattern for separated cuts.",
    ),
    "circular_pattern": (
        "Circular Solid Pattern",
        "Repeat and fuse a solid around the specified world axis and angular sweep. Count includes the original. Copies must remain connected.",
    ),
    "linear_cut_pattern": (
        "Linear Hole Pattern",
        "Choose Base and a cutting Tool, then Count and XYZ spacing. Count includes the original tool. Tools can be separated; the remaining Base must be one valid solid. Proven separate walls follow their numbered authored placement and original tool face through size/spacing edits. Copy 1 is the original tool. Reducing Count removes later copies and blocks their references; overlapping or ambiguous walls are unavailable. Edit Feature changes placement intent, never matches the nearest hole.",
    ),
    "circular_cut_pattern": (
        "Circular Hole Pattern",
        "Repeat a cutting Tool around the specified world axis. Angle is the total sweep: 360 degrees omits its duplicate endpoint; partial sweeps include both ends. Count includes the original. Proven separate walls follow their numbered authored placement and original tool face, not a physical hole. Copy 1 is the original. Changing Count or Angle moves the same placement; removing a referenced copy blocks downstream features. Overlapping or ambiguous walls are unavailable. Edit Feature corrects placement intent.",
    ),
    "shell": (
        "Hollow / Shell",
        "Click a stable planar lid, then enter inward wall thickness for an open enclosure. Edit Feature changes thickness, opening, or Closed cavity mode. Shift-click multiple stable planar faces, then Enter to review the checked opening list. Missing, split or duplicate references and impossible offsets fail without changing the Part. Multiple-opening rims follow their explicit source face identities; changing between one and multiple openings can require explicit downstream repair. Proven unique inner walls and the lip retain feature-owned identities through thickness edits. Pick a planar inner wall to sketch or use supported boundary edges as references. Curved walls are not planar sketch supports. The lip follows the current selected opening: deliberately changing the opening also moves attached lip references to the new lip. Inner walls instead retain their original source wall. Edit Feature corrects opening or thickness. Split or competing native ancestry stays unavailable.",
    ),
    "loft": (
        "Loft",
        "Choose two sections or an explicit ordered list of 2–16 distinct closed single-wire profiles. Add, remove, or move a selected row to change traversal order; sections are never sorted geometrically. Ruled 0 requests smooth interpolation; 1 joins consecutive sections with straight spans. Holes, guide curves, seam alignment and persistent generated face identities are not supported.",
    ),
    "sweep": (
        "Sweep",
        "Choose one closed section (holes allowed) and a solved open planar line/arc path. Center at path start moves the filled-area centroid, not the sketch origin or bounding-box center, to the smallest endpoint ID after explicit coincidence. It aligns the section normal with the first tangent and section +U with the path-plane normal, then applies the literal roll angle. Positive roll turns +U toward +V about the travel tangent. Reverse path traversal starts at the other endpoint; it is not merely a section-normal flip. This saved construction rule is not stable face identity. Source sketches stay unchanged. During creation, wait for the cyan exact boundary preview and its viewport status before Apply; accepted geometry stays visible. The preview has no selectable identity. Apply runs fresh exact work; Cancel or changed source, context or backend retires it. Keep authored placement preserves original section coordinates, as all older Sweeps do. Edit Feature exposes the same choices without live preview. Automatic placement needs one planar region, optionally with holes; separate islands, closed paths, whole-circle paths and 3D splines are unsupported.",
    ),
    "sketch_face_rectangle": (
        "Rectangle on Face",
        "Choose a stable planar face. Width/height and local offsets are measured in its frame, centred on the face with outward normal. The support follows upstream changes.",
    ),
    "sketch_face_circle": (
        "Circle on Face",
        "Choose a stable planar face. Radius and local offsets are measured in its frame, centred on the face with outward normal. Negative extrusion normally points into its solid.",
    ),
    "sketch_rectangle": (
        "Rectangle Profile",
        "Create an XY rectangle from width, height and lower-left XYZ. For drawn geometry on another datum or a face, use New Sketch or Sketch on Face.",
    ),
    "spur_gear": (
        "Printable Spur Gear",
        "A single external spur gear uses module in millimetres, tooth count, pressure angle, thickness, bore and per-gear backlash. Use New Gear Pair for two compatible editable gears with automatic centre spacing and assembly relations; Edit Gear Pair keeps those coordinated. Editing this individual source feature does not automatically update a pair's other gear or assembly spacing. The tooth flanks use a bounded cubic approximation to an involute with analytic tip/root arcs, not an exact involute or manufactured root fillet. Conservative tooth and undercut guards reject unsupported dimensions. Backlash and bore allowances require a printer-specific fit trial; a valid solid is not strength or contact certification. Export the gears without the reference base, which is not for printing.",
    ),
    "sketch_circle": (
        "Circle Profile",
        "Create an XY circle from radius and centre XYZ. For a constrained or face-attached circle use the drawn sketch tools.",
    ),
}

SOLID_HELP_TOPICS = {
    "feature." + kind: (title, [description, *_COMMON])
    for kind, (title, description) in _DESCRIPTIONS.items()
}
