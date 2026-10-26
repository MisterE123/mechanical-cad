# GUI qualification fixture: two Cuts, one source-bound workplane

Open `two_cut_source_bound.mcad.json` through Mechanical CAD's existing Open
workflow. The accepted Part is a plate with two shallow slots and a radius-2,
height-2 boss on surviving material. The final Union makes one connected solid.
Native geometry is generated only by the isolated sidecar, not by Blender Python.

1. In Part, open the named project parameter `plate_width`, initially 20 mm.
2. Select **Boss sketch (preserved plane)** in history and open **Review Support**.
   It should show Preserve logical plane / Minimal twist and explain that the
   saved source workplane follows two proven Cuts, without choosing a fragment.
3. Cancel review. Change `plate_width` to 24 mm through the normal parameter UI,
   then let the ordinary replay finish. The two slot positions remain authored
   constants; the boss follows the original plate's source workplane.
4. Reopen Review Support: the same assumption must remain visible, with Strict,
   another support and the existing orientation/reset controls available. Cancel
   must leave the accepted document unchanged. The top source remains split.
5. Save/reopen if desired and freshly replay. Do not treat a saved display as proof.

| Quantity | 20 mm plate width | 24 mm plate width |
|---|---:|---:|
| Logical sketch workplane origin (mm) | (10, 10, 10) | (12, 10, 10) |
| Boss center at its base (mm) | (16, 10, 10) | (18, 10, 10) |
| Second slot supporting body volume (mm³) | 3760 | 4560 |
| Boss extrusion volume (mm³) | 8π | 8π |
| Finished plate volume (mm³) | 3760 + 8π = 3785.132741229 | 4560 + 8π = 4585.132741229 |

The plane origin is not a fragment centroid; it may span the second slot.
The boss's local sketch center is intentionally (6, 0), over surviving material.
Native topology still has three snapshot-only top fragments. The saved source
binding is the authored `block` feature and `block/face/cap.end` semantic face.
The file contains no ledger, transient snapshot handles or cached native shape.

Sidecar verification: `tests/integration/test_cut_chain_support.py` loads this
fixture and checks both widths, volume, original-plane placement and fresh client
contracts. Actual mouse interaction, layout, Undo and package qualification must
be reported separately from those tests.
