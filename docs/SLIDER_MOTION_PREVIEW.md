# Independent slider motion preview

Development after frozen 1.29.0 adds **Preview Slider Motion** beside an existing
independent slider in Assembly → Joints & motion. Connector editing remains a
separate command. This is source-only; the frozen 1.28/1.29 installers are unchanged.

The detached editor accepts a plain numeric displacement in **millimetres**, with
±1 mm buttons along the existing mate +Z axis. Revolute drivers retain degrees in
the UI and radians in the canonical document. No new schema, evaluator or protocol
is introduced. The existing full assembly replay produces the transient ghost;
other joint coordinates, connectors, limits and source parts are unchanged.

Authored limits and the canonical finite ±1,000,000 mm bound are enforced. Invalid
or pending input removes the usable ghost and disables Apply. Apply requires the
exact current full preview and existing owner/document/backend/lease guards.
Cancel discards the draft without publishing it. Navigation is still explicit.
Motion preview is not contact, collision, dynamics or manufacturing verification.

## Bounded verification (2026-10-25)

- 96 focused draft, owner/currentness, overlay and UI tests pass; Ruff/diff checks pass.
- Blender 5.2.2 with the OCP sidecar: 35 create/preview/limit/Cancel/Apply/save
  checks, 16 separate-process reopen checks, and 9 revolute regression checks pass.
  The reused three-block example moves child `a` from 100 to 125.5 mm, exactly 25.5 mm,
  while root and child `b` remain unchanged; solid volume remains 1000 mm³.
  Revolute 30° still evaluates to π/6 and the expected rotation.
- Actual GUI: separate slider shortcut, typed 125.5 mm full-assembly ghost,
  301 mm authored-limit refusal, disabled Apply, and Cancel preserving exact
  accepted JSON/current display were observed. The final layout keeps both ±1 mm
  labels fully visible beside the exact numeric field. A fresh 125.5 mm draft was ready.
- Actual GUI Apply was blocked by tool authorization before execution. Unchanged
  accepted JSON was verified and the transient draft canceled. GUI Apply/Undo/Redo
  remains unverified pending specific approval; native tests are not a substitute.
- Initial bound-window keyboard simulation omitted some digits; native desktop
  key input correctly entered the complete value. No production workaround added.
- One reopen harness label assumed an operator rather than a Python helper; the
  test label was corrected and the failed and passing logs retained. Blender's
  thumbnail-cache warning did not prevent the verified .blend save/reopen.

Evidence: `evidence/slider-motion-20261025/`, including raw native reports and
checks, GUI receipts and screenshots. No aggregate-suite rerun, Windows or new
exact-installer qualification is claimed. Existing broad-suite limitations remain.
