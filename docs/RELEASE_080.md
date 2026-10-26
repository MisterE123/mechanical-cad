# 0.8.0 visual joint placement candidate

This development increment adds visible connector placement to the integrated
Linux x86_64 Blender 5.2.2 LTS standalone workflow. The delivered 0.7.1 installer
and its evidence remain unchanged. Windows remains deferred and unqualified.

## One visual joint workflow

Pick two existing Assembly instances, move their labeled RGB connector handles,
choose Fixed or Slider, inspect the gold child/subtree preview, and Apply. The
preview explicitly names the child's existing incoming joint being replaced.
Slider motion follows the parent connector's positive Z arrow; distances use mm.
Cardinal alignment, Flip and Roll 90° avoid quaternion entry. Cancel discards the
preview; an applied edit uses ordinary Blender Undo/Redo. The same joint can be
reopened for editing, saved, recovered after reload, checked and exported to STEP.

Literal connectors stay in canonical Part-local coordinates. Shared frames are
copied on write so another instance of a reused Part is unaffected. There is no
face attachment, surface inference or silent geometric repair. The fixed/slider
preview does not add a general mate solver, closed loops or arbitrary mechanisms.
Existing revolute and advanced literal-frame controls remain available.

Only Apply invokes the existing guarded Assembly transaction. A current replay
is not a pose check; checked Assembly STEP still requires the explicit saved-pose
verification workflow. An unfinished visual preview is not saved as model data.
Loading, history changes or lost originating context retire the transient editor.

## Qualification status

Focused pure geometry/owner/layout tests and registered/native/installed GUI
qualification are recorded as they complete. At this source revision, exact
0.8.0 installer and real mouse/keyboard validation are pending. Headless adapter
tests do not substitute for that interaction review. No Windows claim is made.
