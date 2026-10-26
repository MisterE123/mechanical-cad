"""Plain-language in-app help; future features are explicitly labelled."""

from .solid_help_topics import SOLID_HELP_TOPICS

HELP_TOPICS = {
    "workflow.overview": (
        "From 2D profiles to a mechanical solid",
        [
            "Open CAD Workspaces, then New Document. New Sketch opens Line, Circle, Center Arc and an in-sketch Rectangle tool; Rectangle Sketch is a separate constrained shortcut.",
            "Finish Sketch commits its constraints and opens Part. Choose Extrude, check the profile and length, then Apply.",
            "Create another profile and extrusion for a cutting tool. Cut subtracts Tool from Base.",
            "Select the original sketch and Edit Sketch to change its dimensions without losing the downstream part. Save writes portable .mcad.json history.",
            "Assembly reuses accepted Parts with fixed, revolute, slider, cylindrical, planar and ball joints in a rooted tree. Coordinate limits and discrete pose checks are available; general closed-loop solving and load certification are not.",
        ],
    ),
    "sketch.plane": (
        "Sketch plane and position",
        [
            "New Sketch selects XY, XZ or YZ and an offset. Sketch on Face follows a stable planar support. The CAD menu also offers Sketch on Copied Face Plane (Unlinked): a fixed native plane that does not follow source edits. The rectangle shortcut remains on XY.",
            "X and Y place the rectangle's lower-left corner or the circle's centre.",
            "Extrusion follows the profile normal: global +Z for these XY profiles.",
            "Face-attached drawing follows upstream support changes. Project Geometry links earlier sketch lines/circles as construction references; Use Solid Edge links supported straight edges with stable endpoints or full circular solid edges. Circles require a parallel sketch plane; oblique circles, arcs and other curves are unsupported.",
        ],
    ),
    "sketch.support_intent": (
        "Sketch support: explain plane and orientation intent",
        [
            "New Sketch on Face defaults to Preserve logical plane with Minimal twist orientation. The selected current stable planar face and a source-plane direction are captured explicitly. Existing documents without support intent remain Strict exact face. Existing preserve-plane intent without an orientation stays on World axes, including opening Review Support and Apply without changes; no legacy record silently upgrades.",
            "Strict exact support follows the selected face. Preserve logical plane instead follows proven ordinary Cut source-workplane intent even while one exact Modified face remains, so its changing centroid cannot drag the sketch before a split. If that source splits into proven same-source, same-oriented coplanar descendants, the same saved anchor policy continues. Newly captured intent binds that original workplane to its authored source feature, so complete native ancestry can follow it through successive Cuts, including proven partial removal. The saved anchor follows the original source workplane, not a fragment or material patch. Unproven source frames stop for review. It does not pick the largest or nearest fragment and creates no stable face alias.",
            "Minimal twist transports the saved in-plane direction by the shortest rotation from the saved source normal to the current normal. It avoids the reference-axis jump of World axes. It does not infer material spin around the normal or integrate the path through previous edits; the saved baseline makes replay deterministic. World axes keeps the legacy projected-world-axis construction exactly, including its possible abrupt turn when the reference axis changes.",
            "Example: a slot splits the top face of a plate. A downstream sketch can stay on the original top construction plane instead of jumping to one remaining patch's centroid. The plane can span the removed slot; support does not prove that material remains beneath the sketch.",
            "An active assumption remains marked Plane assumed in Feature History. Select the sketch and Review Support to read why, choose Strict exact face, change Supporting solid and Supporting face, or explicitly choose Minimal twist / World axes in Orientation. Local sketch coordinates stay unchanged, so replacement support or a different orientation can move or rotate the sketch.",
            "Nearly opposite source normals have no unique shortest-rotation axis, so Minimal twist stops rather than guessing. In Review Support choose Reset saved frame here to deliberately adopt the current World axes frame and current support anchor as a new Minimal twist baseline. The warning matters: this correction may rotate or move the sketch and downstream geometry. It still requires proven support ancestry; it does not excuse a missing source or different descendant planes.",
            "Strict requires an exact stable face. If the original face has split, select a replacement stable face before applying Strict. Apply validates the complete Part before saving; a failed correction leaves the existing document unchanged. Cancel changes nothing. Blender Undo restores the previous support and policy; Rebuild revalidates restored geometry.",
            "The rule stops for missing or mixed lineage, generated faces, different planes or orientations, unproven source-frame changes, merges, disappearance of the whole original plane, unsupported intervening operations, or ambiguous candidates. Older records without a source-feature binding keep their immediate-source rule rather than silently changing their saved anchor. It cannot promote a fragment into the original face. For an explicit legacy split repair, Preserve logical plane may adopt the current original Cut source's stable plane and centroid after proving its complete descendants. The dialog explains that no historical anchor was saved; this choice is never automatic.",
        ],
    ),
    "sketch.rectangle": (
        "Create a rectangle profile",
        [
            "No viewport selection is needed. Width and Height are measured in millimetres.",
            "X, Y and Z locate its lower-left corner. Width and Height must be positive.",
            "Apply adds a saved profile and visible named parameters to this document.",
            "To revise it, edit those parameters and Regenerate. Blender Undo reverses recent session actions.",
            "This is a dimensioned XY-plane profile, not a general constrained sketch.",
        ],
    ),
    "sketch.circle": (
        "Create a circle profile",
        [
            "No viewport selection is needed. X, Y and Z locate the circle's centre.",
            "Radius is half the diameter, in millimetres. Enter 5 for a 10 mm diameter circle.",
            "Radius must be positive. Apply adds a saved profile and named parameters.",
            "To revise it, edit those parameters and Regenerate, or use session Undo.",
            "Circle outlines in Blender are display tessellations; the CAD profile is an exact circle.",
        ],
    ),
    "sketch.dimensions": (
        "Edit saved dimensions and formulas",
        [
            "Named parameters control the saved profiles and solids. Values use millimetres.",
            "Blender numeric widgets use single precision. For exact typed decimal/formula input, use the Formula text field.",
            "Change a value, then Regenerate to replay dependent features. Dirty display geometry is hidden.",
            "The formula toggle accepts safe arithmetic such as width / 2; it does not run Python.",
            "A formula may reference another named parameter. Cycles, missing names and invalid dimensions fail visibly.",
            "The Rectangle shortcut provides H/V, shared corners, optional anchor and size relations. Drawn lines, circles and arcs support driving dimensions, explicit geometric relations, construction geometry and removable constraints.",
        ],
    ),
    "feature.extrude": (
        "Extrude a profile into a solid",
        [
            "Choose a saved primitive or constrained profile. The selected history profile is a visible, correctable default.",
            "Length is the positive distance in millimetres along the profile normal, which is +Z for XY profiles.",
            "Apply adds a solid feature, keeping the source profile in history. The source dimensions remain editable.",
            "Change its named length and Regenerate, or use session Undo to reverse creation.",
            "Signed negative length reverses the sketch normal. Symmetric extrusion, taper and Through all are not implemented. A depth formula can follow a named thickness parameter.",
        ],
    ),
    "feature.boolean_operands": (
        "Cut one solid with another",
        [
            "Base is the solid you keep. Tool is the solid whose overlapping volume is removed.",
            "Choose two different recorded solids. Verify both dropdowns before Apply; suggested choices can be changed.",
            "Apply creates a new Base minus Tool result. Both original features stay in history.",
            "The tool has finite dimensions; this is not Through all. Enlarge or reposition the tool and Regenerate when needed.",
            "This slice requires one nonempty solid result. Split bodies and invalid or no-effect cuts are rejected.",
        ],
    ),
    "history.edit": (
        "Saved feature history and output",
        [
            "The feature list is saved design history. Earlier features provide inputs to later ones.",
            "Open the small filter drawer below history to search visible names or feature IDs. Clear the search to show all rows; filtering never changes selection or history order.",
            "Select a row and choose Display Selected Feature to inspect that output. This does not delete later features.",
            "Edit named dimensions and Regenerate to replay the whole document. Errors identify failed and blocked features.",
            "Blender Undo only reverses recent session actions; it is different from the portable feature history.",
            "Direct Blender mesh edits are display-only and discarded on Rebuild. History deletion explicitly identifies dependent features before cascading. Arbitrary feature reordering is not provided.",
        ],
    ),
    "intent.suggestion": (
        "Check suggested inputs before Apply",
        [
            "A default is a starting point, not a hidden design decision.",
            "Extrude may suggest the selected history profile. Cut initially suggests the two latest solids.",
            "The dialog shows the exact Profile, Base and Tool. Change any wrong choice before Apply.",
            "Cancel leaves the document unchanged. Automatic sketch constraints are not implemented.",
        ],
    ),
    "units": (
        "Millimetres and Blender display scale",
        [
            "This version uses millimetres for CAD lengths. Enter 25.4 for 25.4 mm.",
            "Known length text fields accept literals such as 10 mm, 2 cm, 1 m, 1 in or 1 ft; angle text fields accept 45 deg or 1 rad. Bare values keep their existing mm/degrees convention.",
            "Use one number and one unit, not width + 2 mm or 1 in + 2 cm. Counts, ratios, axes and quaternion components are unitless. Global project parameters remain untyped: enter formulas in their existing units without suffixes.",
            "Legacy numeric-only widgets and volume tolerances do not gain this text-input support. Unit input is a UI convenience, not a new expression or document language.",
            "CAD millimetres convert to metres by 0.001; display coordinates also account for the scene unit scale.",
            "At default scene scale, a 40 mm part spans 0.04 Blender units. Focus Result isolates and frames it; Whole Scene restores the full scene.",
            "Regenerate after changing scene unit scale. The authoritative CAD dimensions remain in millimetres.",
        ],
    ),
    "error.details": ("Full diagnostic message", []),
    "error.rebuild": (
        "Fix a failed regeneration",
        [
            "The current build did not succeed. Read the error and failed feature in this panel.",
            "Fix the named dimension or formula, then Regenerate. Blocked features depend on an earlier failure.",
            "Failed replay keeps the last-good display as a visibly marked STALE wireframe cache. It is not the current result, is excluded from renders, and has no current volume.",
            "A rejected file load or feature creation keeps your prior document and valid display unchanged.",
            "For a backend or timeout error, check the add-on preferences and retry. Unrelated Blender objects are untouched.",
        ],
    ),
    "persistence": (
        "Save, load and Blender files",
        [
            "Save writes .mcad.json: document identity, parameters, feature IDs and operations. Display meshes are not saved in this CAD file.",
            "Load validates and replays the file before replacing your current document. Invalid files show an error.",
            "Save your work before New, Demo or Load replaces the current model. Use Blender Undo for recent session changes.",
            "The current document also lives in the Blender scene and is retained in .blend files. On reopening, Regenerate verifies its display.",
            "Portable JSON history is authoritative. A .blend mesh alone does not preserve CAD design intent.",
        ],
    ),
    "setup.bundled": (
        "Automatic offline CAD backend",
        [
            "The standalone extension includes its isolated CAD backend. Enable the extension and wait for automatic offline preparation; no Project Root or Python path is required.",
            "Preferences show preparation, ready or failure status. Preparation uses only the installed package and does not download or install dependencies from the network.",
            "Once ready, create a New Document, draw a sketch and extrude it. The native CAD libraries run in a separate process, never inside Blender.",
            "If cleanup cannot be confirmed, native operations stay blocked. Save your work and restart Blender. Disabling and re-enabling the extension cannot discard the retained owner or bypass the failure.",
            "A prepared backend is not geometry evidence. Check or rebuild the current document explicitly; saved reports remain historical until validated again.",
        ],
    ),
    "setup.backend": (
        "Configure the independent CAD backend",
        [
            "CAD modeling runs in an isolated external Python process. Blender never imports the native CAD library.",
            "In add-on preferences, set Project Root to this repository and Python Executable to its prepared .venv Python.",
            "The external environment needs the project's CAD dependencies. It may use a different Python version from Blender.",
            "Then use New Demo or Regenerate to test the connection. Timeout and display mesh tolerance can be adjusted in preferences.",
        ],
    ),
    "verification.geometry": (
        "Build status and geometry checks",
        [
            "Up to date: history rebuilt successfully. Row checkmarks show rebuild success, not a Geometry Check report.",
            "Geometry check: not run means no explicit Check report exists. Use Check, then open Part details for the report.",
            "A solid must pass kernel validity checks and this slice requires one nonempty solid per solid feature.",
            "A valid CAD solid does not by itself verify a watertight display mesh. Mesh quality depends on tessellation tolerance.",
            "Assembly checks measure exact-solid interference and clearance at the specified poses. A selected verification preset supplies engineering requirements; sampled poses do not prove continuous collision freedom.",
            "This status is not manufacturing certification. No structural or load validation is provided.",
        ],
    ),
    "roadmap": (
        "Current scope and planned workflow",
        [
            "Available now: Sketch, Part and Assembly workspaces; viewport lines, circles and the rectangle shortcut; exact driving dimensions; upstream edits; extrusion, cut and portable history.",
            "Available sketch tools include general line/arc loops, circles, holes, construction curves, explicit relations, angle and diameter controls, and previewed trim/extend. Parts support editable solid operations and checked exports. Geometric validity and exact current source evidence remain required; unsupported or ambiguous cases stay visible.",
            "Reusable Part instances support fixed, revolute, slider, cylindrical, planar and ball tree joints, literal or supported planar-face mate frames, motion limits and exact-solid checks.",
            "Assembly verification applies only to its exact accepted sources, saved policy and listed poses. Closed-loop solving and continuous collision checking are not implemented.",
            "Drawing sheets are outside the current scope. No structural or load validation is provided.",
        ],
    ),
}


HELP_TOPICS["geometry.actions"] = (
    "Geometry checks and explicit exports",
    [
        "Finish or cancel any sketch draft first. Each action rebuilds the current committed parameters and feature history in the CAD backend.",
        "Checks require one valid positive-volume solid and a closed oriented manifold tessellation.",
        "A successful sketch solve alone is not a solid check. Select a supported solid output; open sketches and profile-only outputs cannot be exported as solids. Remaining sketch freedom alone does not prove geometry invalid.",
        "Sketch-only output is not an Assembly source. Valid analytic line/arc profiles, including supported nested holes, can be extruded into exact solids and then captured with other Parts.",
        "STEP preserves exact B-rep geometry. STL is checked binary triangles; select millimetres when importing it. Float32 encoding must stay within min(0.00001 mm, 0.1 × tessellation tolerance); a valid large solid can pass STEP and fail STL precision.",
        "Choose an export file explicitly. The file selector asks before replacing an existing file; a symlink entry is replaced without changing its target.",
        "Failed geometry leaves the prior export untouched. UNKNOWN means an export may already have replaced the file but its completion could not be validated. OUTDATED retains a confirmed earlier write after current CAD publication was rejected. Neither outcome retries automatically; inspect the file and deliberately run again if needed.",
        "Saved reports are historical metadata. Reopening a scene, Undo/Redo or a changed backend requires fresh verification; an earlier successful replay is not a current Geometry Check.",
        "Blender Undo does not undo exported files. Save .mcad.json or .blend to retain editable feature history.",
        "These checks do not establish manufacturability, wall thickness, tolerances, structural strength or assembly motion.",
    ],
)


HELP_TOPICS["sketch.viewport_rectangle"] = (
    "Constrained viewport rectangle",
    [
        "Click two opposite corners on global XY. The lower-left corner in sketch coordinates and its X/Y location are shown.",
        "The tool explicitly adds H/V edges, shared corner points and driving width/height distances. In Dimensions, turn off Fix rectangle position to remove the anchor and leave translation free.",
        "Releasing position seeds the same point IDs from the last visible solution, so removing only the anchor keeps its placement. Changing size at the same time may move a free rectangle; inspect Apply's result.",
        "Enter 60, 60 mm or 6 cm for the same length. Exact decimals and named formulas are accepted; units inside formulas are not. Apply solves only the draft.",
        "Actual solver status and remaining degrees of freedom appear after solving. Fixed position normally gives 0 DoF; free translation gives 2. An unverified preview claims neither.",
        "Finish commits one schema-2 constrained feature and returns to Part. Editing the original rectangle preserves its ID and rebuilds downstream solids.",
        "Leaving Sketch suspends the draft in its original scene. Resume restores exact typed input, including invalid text, only against the original committed revision; its preview and DoF remain unverified until Apply or Finish. Esc, Cancel or Discard deliberately removes the draft.",
        "Save .blend to retain suspended or active draft input separately from feature history; .mcad.json saves only committed design. Undo/Redo keeps the draft but can make its base stale. Restore the original document or explicitly Discard; the editor never automatically rebases.",
        "This shortcut supports its bounded rectangle definition on XY. Use New Sketch for Line/Circle drawing and direct distance/radius labels; use the general editor for other planes and relation editing.",
    ],
)


HELP_TOPICS["sketch.general"] = (
    "Lines, circles, arcs and driving dimensions",
    [
        "Choose Line, Circle or Center Arc, then draw in the sketch plane. Hold Shift at a Line’s second endpoint to add an explicit Horizontal/Vertical constraint in sketch-local axes; release Shift for a free line. Off-axis existing points are not moved or reused. Center Arc takes three clicks: center, start and end. Existing geometry and its local history are preserved; adding the arc is one Undo step.",
        "Use existing point chooses an exact endpoint or center when several identities overlap. Reusing its ID connects geometry; drawing at the same coordinates does not secretly merge points. Shift-select two points to add Coincident explicitly.",
        "Press D or choose Dimension. Click a circle center or sketch point, then a straight reference line, then place the label and type a perpendicular offset. Offsets are unsigned: the current center placement seeds the side. To change sides, local Undo until the new offset is removed, use Select to drag the center across the reference, then dimension again. Repeat against a second edge to locate a hole. Two points instead create straight-line distance (not horizontal/vertical). A curve perimeter creates radius; a line interior creates length. Esc cancels an unfinished selection; after cancelling numeric input, local Ctrl-Z removes the newly added dimension and its construction helpers. Double-click a label to edit it. Select two lines for a driving angle in degrees. Set Diameter enters a circle or arc diameter, stored explicitly as radius = diameter / 2. Values may use named formulas.",
        "Placing a dimension opens its value field immediately: type a value or formula, then Enter for checked acceptance. Esc cancels the value edit and retains the placed dimension. Double-click an existing label to edit it again. Invalid text stays recoverable. Drag a label to move its annotation without changing geometry. Labels are saved in the Blender scene on Finish.",
        "Shift-select two lines to add Parallel, Perpendicular or Equal. Equal also supports two circle radii. Tangent supports an arc and line sharing one exact endpoint; Circle-line tangent is a separate relation to an infinite supporting line. Point on line, Midpoint and Concentric have their own selection rules and contextual help. The relation inspector exposes stable identities, removal and editable fixed coordinates.",
        "Construction curves are cyan dashed references: they participate in solving and dimensions, but not solid profile boundaries. Toggle selected curves between construction and ordinary geometry. Keep a closed ordinary boundary for a solid profile.",
        "Check reports the actual solver result and remaining freedom. Closed line/arc loops and circles can form profiles, including non-touching holes and multiple regions. Crossings, ambiguous contacts and branched boundaries are rejected rather than guessed. A supported open line/arc chain can be saved as editable sketch data.",
        "Finish saves the checked sketch and rebuilds its dependents. An existing-sketch edit that breaks supported downstream sketch references can transfer to an unapplied repair proposal; the accepted Part stays unchanged until all repairs succeed. Other failed dependent rebuilds retain the draft. Successful constraint solving alone does not guarantee that a particular profile or solid operation is valid.",
        "Sketch planes may be XY, XZ or YZ with an offset, a supported stable planar face selected with Sketch on Face, or the saved plane of an existing sketch. Dimensions always use local plane coordinates in millimetres. Solid-context display alone creates no projection or attachment; use the explicit source-selection tools.",
        "Reverse sweep changes CW to CCW or vice versa without swapping endpoint identities. The complementary arc changes the boundary and can change area or volume. Camera orientation does not change the saved direction.",
        "Trim and Extend move a straight-line endpoint to a finite line, circle or directed arc boundary. Arc hits must lie within the chosen sweep. For curved boundaries, the nearest crossing from the chosen endpoint is used; tangent contact is refused. Review the preview before Apply. Constrained targets and unsupported intersections remain unchanged with a readable explanation; relations are never silently discarded.",
        "Esc outside a text field suspends the draft. Resume preserves exact input against the original Part revision. Local Ctrl-Z edits the sketch journal; Blender Undo edits committed history. No automatic source or model Git commit is performed.",
        "Incomplete arc boundaries remain editable drafts. Profile-only output is not a solid export or Assembly source. Complete a valid solid before exporting STEP/STL or capturing it for Assembly.",
        "Select a line, circle or arc and use the inspector Length/Radius/Diameter (REF) actions for read-only measurements without solver constraints. Arbitrary relation retargeting remains unavailable. The compact field has no IME composition or screen-reader text integration.",
    ],
)


HELP_TOPICS["sketch.constraints"] = (
    "Explicit sketch relations",
    [
        "Select a line to see Horizontal and Vertical tools. These add persistent relations in the sketch plane. Pointer placement and snapping alone never add a hidden constraint. An exact existing relation is inspected rather than duplicated.",
        "Choose Points on the left to pick endpoints and circle/arc centers separately from curves. Distinct overlapping point IDs remain ambiguous. Select a line, circle or arc and use its exact-kind Start, End or Center inspector control to select the point. Selection alone never accepts a Line/Arc point input; use the separate Use existing point picker for that.",
        "Point on line and Midpoint use a selected point plus a line. Concentric uses two circles; Circle-line tangent uses a circle plus a line. Their contextual question buttons explain infinite-line versus finite-segment behavior and exact identity requirements.",
        "Fix here anchors a point at its current checked position. Fix at origin separately asks to move it to sketch-plane (0, 0) mm; connected geometry can move. An existing fixed relation is inspected, never silently replaced.",
        "Select a relation in the inspector to remove only that relation. With a current successful Check, removal starts from its solved point positions and circle radii. Remaining degrees of freedom come from the next real Check, not from the number of deleted relations.",
        "Without a current solution, Remove using authored positions is a separate explicit recovery choice. It preserves the saved authored point/radius seeds, which may differ from an old displayed outline. Review the named relation before Apply. Undo sketch restores the exact prior intent; a new Check is always required.",
        "Conflict candidates are native diagnostic suggestions bound to the current request and raw input revision. They are not proof of which relation is wrong or permission to delete it. Failed sketches stay editable drafts and cannot Finish until the sketch and dependent features succeed.",
    ],
)


HELP_TOPICS.update(SOLID_HELP_TOPICS)


HELP_TOPICS["sketch.position_relations"] = (
    "Position and tangent relations",
    [
        "Symmetry: Shift-select two distinct points and one ordinary or construction straight line in any order. The points cannot be endpoints of that axis. Both points become exact mirror images across its infinite supporting line, at any angle, not merely centered around it. The axis can move unless separately constrained; a collapsed axis is rejected. This does not create mirrored curves or duplicate geometry.",
        "Shift-select a point and a line for Point on line or Midpoint. Selection order does not matter. Use the Points tool or the curve inspector's exact endpoint/center controls to choose the intended point identity.",
        "Point on line places the point on the infinite line through the selected endpoints. It does not force the point inside the finite segment. Midpoint instead places it exactly halfway between the two endpoints. A line's own endpoint cannot be used for either action.",
        "Concentric circles joins the two selected circle centers while leaving their radii independent. Circles already sharing the same center-point identity need no additional relation. Use Equal separately if the radii should match too.",
        "Circle-line tangent makes the selected circle tangent to the infinite supporting line. The contact may be beyond the displayed segment endpoints. This is an exact native solver relation, not a visual approximation. Geometry may move to either valid side according to the existing geometry and constraints.",
        "Arc tangent remains a separate action for an arc and line sharing one exact endpoint identity. It is not silently replaced with circle tangency. All these relations operate within the sketch's local plane, including an associative face sketch.",
        "Apply runs a fresh native Check. Conflicting fixed points or dimensions can prevent a solution; inspect the reported relations and remove the intended one, or Undo sketch. A failed check keeps the draft and does not publish a successful Part. Select a relation in the inspector to remove it; Undo and Redo retain exact local history.",
    ],
)


HELP_TOPICS.update(
    {
        "sketch.projection": (
            "Project Geometry / Use Solid Edge",
            [
                "Project Geometry links lines/circles from explicitly chosen earlier sketches. Use Solid Edge offers an earlier Source solid, then Pick Edge on that source's temporary body. Pick a highlighted straight edge or full circle away from corners. Both create construction references, not new profile boundaries.",
                "One sketch can mix several earlier sketches and solids. Repeat either source chooser without Finish or reopening. Each reference retains its own source on Check/rebuild; matching face labels on different solids do not identify the same reference. The temporary picking body does not change active output or accepted geometry; Esc returns to the sketch without adding a reference.",
                "Circle planes must be parallel to the sketch plane. Oblique circles, partial arcs, other curves, collapsed lines and ambiguous identities are rejected, not guessed. Source-driven points and circle radii cannot be independently edited or lose their managed drivers.",
                "To locate a hole from an edge, choose Dimension, select its center and a straight projected line, then place and edit the perpendicular offset. A second dimension can locate it against another edge. Inspect the selected sources before accepting them.",
                "Missing or split source faces require explicit reference repair; moving a Blender display mesh cannot repair CAD identity. Replace Reference retains the selected reference's source and analytic kind. Eligible unapplied edits can keep multiple explicit repairs with proposal Undo; only a complete successful rebuild changes the accepted Part. Cancel a wrong pick and select the intended supported edge.",
            ],
        ),
        "feature.preview": (
            "Extrusion preview is not Apply",
            [
                "Cyan outlines preview Extrude Sketch and Add/Remove creation settings over the unchanged accepted Part. Blind, Symmetric and Remove Through All share the same candidate settings as Apply.",
                "Profile, target, direction and depth are editable assumptions. Review those fields, especially inward/outward direction on face sketches. Symmetric depth is TOTAL depth; Through All Remove runs in one chosen direction.",
                "Changed input clears the old preview. Failed or incomplete previews say so. Preview edges are not selectable CAD references, and editing arbitrary existing features has no creation preview.",
                "Apply runs a fresh guarded check before publishing. Cancel or Esc removes the preview without accepting the proposed geometry. A preview is not manufacturing or assembly-clearance evidence.",
            ],
        ),
        "assembly.start": (
            "Assembly: capture, insert and update Parts",
            [
                "Create a valid Part, then New Assembly from Part. Explicitly confirm grounding the first instance at world origin. Insert Child Instance reuses a definition or explicitly captures the working Part.",
                "Choose parent, child and mate frames before Apply. Frames may be literal coordinates or attached to supported stable planar faces. The assembly is a rooted joint tree, not a general closed-loop solver.",
                "Open an embedded source in Part to edit it, then explicitly Update All Instances. A changed working Part does not silently replace accepted assembly sources. Save the assembly separately from the Part.",
            ],
        ),
        "assembly.faces": (
            "Mate by Faces: facing defaults and corrections",
            [
                "Pick a stable planar parent face, then a non-grounded child face. Picking isolates one named component; Previous / Next target changes which component is available without moving it.",
                "A NEW face pair assumes face centroids and deterministic axes, flipping the child connector 180 degrees about local X so outward normals face each other before authored motion. This is not a guess at a hole center or proof of contact.",
                "Choose Parent/Child handle to correct either connector. Flip reverses its normal; Roll turns 90 degrees; RGB handles or X/Y/Z plus a number set offsets in mm. Pick face replaces its support. Existing attached offsets/orientation are retained on support replacement; saved joints are not flipped on reopen.",
                "Apply replaces the child's incoming joint, not a second constraint. Existing motion/limits are retained; Edit changes them. Reset motion explicitly zeros motion and removes limits. Unsupported kind changes fail rather than silently discard settings.",
                "The boundary outline is an UNCHECKED placement preview, not collision/contact/clearance evidence. Apply freshly replays; run explicit pose checks afterward. Cancel leaves the accepted assembly unchanged. Missing or ambiguous support needs explicit repair.",
            ],
        ),
        "assembly.motion": (
            "Joint motion and pose checks",
            [
                "Fixed, Revolute, Slider, Cylindrical, Planar and Ball joints have explicit frame and motion inputs. Inspect named axes and limits instead of assuming free Blender transforms are CAD motion.",
                "Revolute angles use degrees in the UI; slide distances use millimetres. Scalar revolute/slider motion can be edited in the viewport. Cancel discards the preview; Apply commits a checked candidate.",
                "Run checks against accepted sources and the intended saved policy/poses. Interference and clearance results apply only to those discrete poses, not the entire motion path. Unchecked or stale reports are not passing results; no load or manufacturing certification is provided.",
            ],
        ),
        "assembly.export": (
            "Save Assembly / Export Assembly STEP",
            [
                "Save the assembly document to retain reusable Parts, joints and editable intent. Export Assembly STEP freshly checks the saved pose and writes named reusable Part definitions with instance placements in millimetres.",
                "STEP contains geometry and placements, not editable feature history or joints. Choose the file explicitly and review replacement confirmation. Blender Undo cannot undo an exported file.",
            ],
        ),
        "feature.import": (
            "Import STEP Solid",
            [
                "Import STEP Solid accepts one supported valid solid and stores the source bytes in the CAD document. The imported feature can feed subsequent Part operations; it does not recover the original author's parametric feature history.",
                "Choose the source file explicitly. Unsupported or invalid geometry is rejected rather than converted from its display mesh. Save the CAD document for editable downstream history; STEP export remains geometry-only.",
            ],
        ),
    }
)


HELP_TOPICS["sketch.reference_dimensions"] = (
    "Read-only reference measurements",
    [
        "Select one authored line for Length (REF), or one circle/arc for Radius (REF) or Diameter (REF), in the sketch inspector. These labels add no solver constraint and cannot overconstrain a sketch. Arc diameter measures its supporting circle, not arc length.",
        "Every label says (REF). Current solved geometry supplies the measurement; an unverified draft shows ~ and unsolved estimate instead. No measured number or formula is saved. Changes to geometry update the displayed measurement.",
        "Double-click explains that the label is read-only; it never opens a value field. Use Dimension for a driving length/radius or Set diameter for a driving diameter instead. Drag a reference label to change its placement only.",
        "Remove Reference (the X beside its inspector entry) removes only the label. Local Undo/Redo edits sketch geometry, not reference label placement. Missing targets stay unavailable and are never rebound by proximity; restoring the same authored ID can restore the measurement.",
        "Finish saves reference metadata in the Blender scene, separately from the Part. Scene Undo/Redo restores committed metadata. Save .blend preserves accepted references and suspended draft labels; .mcad.json does not carry scene annotations. This first slice has no reference distance between separate points, angle, arc length or reference formulas.",
    ],
)
