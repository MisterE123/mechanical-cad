# Assembly joint types

Insert Child Instance offers six joint types. Each relates the child's named mate frame to the parent's named mate frame in a rooted assembly tree. Edit Joint Coordinate changes its saved coordinates and limits; all instances are replayed through the exact solid backend before a change is accepted.

- **Fixed:** no relative motion.
- **Revolute:** one right-hand rotation about mate-local +Z.
- **Slider:** one translation along mate-local +Z.
- **Cylindrical:** independent translation along +Z and rotation about +Z.
- **Planar:** independent translations along mate-local X and Y, plus rotation about +Z. The two mate planes retain zero relative Z offset.
- **Spherical / Ball:** three rotational degrees of freedom around a fixed mate-frame center. Angles are composed X, then Y, then Z (Rz · Ry · Rx).

Translations are entered in millimetres. Rotations are entered in degrees and saved as radians. Each movable axis has optional inclusive lower/upper limits. Lower must be strictly below upper; invalid coordinates reject the operation without changing the accepted assembly. Ball-joint limits bound Euler components, not a physical cone angle. Euler parameterizations have singularities; this is forward positioning, not an inverse dynamics or orientation solver.

## Authoring and verification

1. Capture the first Part with explicit grounding.
2. Define literal mate frames or associative stable planar-face frames as needed.
3. Insert a child, choose its parent and named frames, then select the joint type and enter each axis.
4. Edit Joint Coordinate exposes independent coordinates and limits. Gear-driven revolute angles are read-only; their limits remain editable. Saving/reopening a blend preserves these values.
5. Sample offers each independent movable axis separately. Every sample retains all other independent authored coordinates and re-derives gear followers. Only listed discrete poses are checked; no continuous collision guarantee is implied.

For cylindrical, planar and ball joints, use named frame editing for connector placement. Interactive viewport connector dragging currently supports fixed, revolute and slider joints only. Assemblies remain rooted trees: closed-loop mate solving, contact dynamics, springs and physical joint-load certification are not provided. Existing revolute joints can now have explicit [gear coordinate relations](ASSEMBLY_GEAR_RELATIONS.md), with signed ratio/phase and a read-only derived follower. This is not physical tooth contact.

## Native checks

- `tests/blender_assembly_cylindrical_smoke.py`: create/edit cylindrical joints, reject out-of-limit rotation, sample both axes while retaining the other coordinate.
- `tests/blender_assembly_multiaxis_smoke.py`: create/edit planar and ball joints, independent bounds, sample all six independent coordinates, save/reopen the blend without losing axes or limits.

## Correcting an insertion

Select a non-root instance and choose **Remove Component…**. The dialog names the selected component, all descendants, incoming/dependent joints, and each affected clearance requirement. Long previews have numbered pages. Removal keeps reusable Part definitions and embedded sources, so the Part can be inserted again.

Clearance requirements involving removed components are removed. Presets left with no clearance requirements are deleted rather than converted to a weaker policy. If that was the active preset, verification returns to measurements-only until another preset is selected. The dialog explicitly discloses this change. Other requirements and presets stay unchanged.

The grounded root cannot be removed. Cancel is non-mutating; a changed assembly invalidates an open removal preview. Apply replays the detached candidate before publishing it, and a failed replay retains the original branch. This is an undoable Blender operation and the accepted result survives save/reopen.
