# Rectangle in the drawn sketch editor

Choose **Rectangle** (or **R**) inside a drawn sketch, then click two opposite
corners. The purple preview follows local U/V on the current datum or attached
face plane. The second click accepts one closed loop with four shared corner IDs,
four ordinary editable lines and four explicit horizontal/vertical relations.
These relations appear in the existing relation history. No nearby point is
silently snapped or reused.

Use **Dimension**, select a horizontal or vertical side and place its driving
length. Placement immediately opens the value field; type a value or expression
and press Enter. Double-click an existing dimension to edit it later. Width/height
entry during the initial gesture is not yet implemented. The rectangle is not a
locked primitive: its four lines use the same relation and dimension tools as
other drawn geometry.

Esc or **Cancel proposal** discards only an unfinished rectangle. Suspended
proposals retain both observed corners without pointer capture; **Continue**
resumes explicitly. Accepted rectangles are a single local Undo/Redo step.
Check and Finish use the unchanged native solver and guarded publication path;
finished loops can be extruded along their datum or attached face normal.

Evidence: `test_general_rectangle.py`, rectangle cases in
`test_general_sketch_draft_native.py` and `test_attached_sketch_authoring.py`,
and native Blender `blender_general_rectangle_smoke.py`. Headless seam checks
are not a claim of interactive GUI usability verification.
