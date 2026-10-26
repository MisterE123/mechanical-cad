# General line/circle viewport development entry

This records the development path and earlier source-level evidence. The current
source registers the Line/Circle editor through normal add-on lifecycle; see the
[bounded workflow](GENERAL_SKETCH_WORKFLOW.md) for its public entry points.
Released 0.3 archives remain unchanged and do not enable these new tools.

Launch `scripts/blender_general_viewport_dev.py` with native Blender 5.2.2
`--factory-startup --python-exit-code 1` in a distinct QA profile. It creates an
empty QA Part and uses the production New Sketch route. It scripts no geometry.

## Implemented loop under review

- Choose Line or Circle, then two viewport clicks. Endpoint reuse is an explicit
  point-identity pick; pointer motion is analytic and invokes no native work.
- Accepted structural intent schedules a real asynchronous solve. Check/Cancel
  are explicit; no shared-busy rejection queues an automatic retry.
- Dimension selects a line/circle and places a distance/radius annotation. Its
  double-click opens a compact exact raw value/formula field. Enter requests one
  checked acceptance; a consumed profile also receives a full downstream replay.
- Finish asynchronously replays the complete candidate and publishes that exact
  completed result through the shared one-shot transaction. An independent open
  chain saves as editable sketch data; unavailable consumed profiles stay drafts.
- Local Ctrl-Z changes the bounded sketch journal. Blender Undo remains the
  separate canonical transaction. Esc suspends; unfinished proposals and raw input
  retain their existing versioned shared-owner persistence.

`general_session.py` owns only the shared SketchSession subclass and async
acceptance orchestration. `general_viewport.py` owns projection, event routing and
operators. The drawing/input modules remain independent. Importing a module never
registers classes; the normal add-on lifecycle owns registration.

## Evidence and unfinished gates

`tests/blender_general_session_smoke.py` passes 70 real native-headless checks:
circle creation, raw formula edit, invalid arithmetic retention, Cancel, async
Finish, analytic extrusion, consumed-driver downstream validation, same-feature
Part update, exact-base staleness and a saved open chain. Headless registration of
the experimental classes passes. These results are not GUI qualification.

The initial native drawing/keyboard/navigation review established the bounded
circle/formula/upstream-edit loop. The integrated production palette, kind-aware
Resume, retained annotation layout and viewport isolation require a separate
frozen-candidate review. General constraint/deletion controls and broader text
accessibility remain product work. While a dimension is being edited, the
previously accepted outline is retained with its solver fingerprint removed and
an explicit unverified label. It is bound to the unchanged command revision and
is discarded on structural changes or owner retirement. No current DoF is shown
during a pending field. This drawing-only continuity never authorizes acceptance
or export; successful fresh native evidence is still required.

The QA launcher writes a read-only state receipt under the workspace evidence
folder. It is test instrumentation, not a production telemetry feature. Do not
package the development launcher as a qualified user workflow.

### First native GUI findings

On Blender 5.2.2, real pointer creation, circle selection, radius annotation
placement/drag, Finish and a 10 mm Part extrusion passed. This exposed missing
modal double-click synthesis: the label hit was valid but no native DOUBLE_CLICK
arrived. The adapter now recognizes a completed click followed within 350 ms and
4 pixels on the same label; dragging, navigation, another label or a missing
release prevents activation. The native event remains supported. Seven pure
sequence tests and eight native adapter assertions cover this correction; GUI
retest remains required. The 70-check real GeneralSession suite still passes.

The first review used a development-only Edit Selected entry. Current source
routes the ordinary **Edit Sketch** action to the supported matching editor and
retains an explicit Rectangle shortcut. This production routing has separate
native/installed dispatch tests; it is not retroactively covered by that first
GUI review.

### Cancellation/setup repair

Independent review found three owner integration defects: failed cleanup-supervisor
setup could strand a cancelled child lease, Cancel Input could leave a stale text
controller, and Cancel Check could leave that controller's acceptance latch set.
The owner now establishes the shared supervisor before starting any child, closes
input explicitly when discarding its pending edit, and releases the acceptance
latch when cancelling a check. Raw text survives Cancel Check for explicit retry;
held terminal events are still drained by the existing input controller.

`tests/blender_general_failure_smoke.py` passes 29 native checks, including an
injected setup failure before process creation, a real child cancellation through
the development operator, resumed typing, explicit input cancellation and unchanged
canonical/revision data. The 70-check owner suite remains passing. The independent owner audit closed these three corrections on exact 547c5c2;
see [its bounded receipt](audits/general_session.md).


### Retained-outline presentation

The native GUI confirmed a visual jump to creation seeds during invalid input or
Cancel. A display-only retained variant now keeps the accepted outline throughout
that edit. Opening a field, failed arithmetic and Cancel preserve the same radius;
new checked acceptance replaces it. The owner test now has 78 checks, including
that the retained copy has no current solver fingerprint or DoF authority. A
separate pure test preserves immutable source/solver records. Native offscreen
GPU/BLF checks verify the explicit retained status and state restoration.

Numeric annotation details use six significant display digits. The saved value
and compact editor retain the full original value or exact formula. The common
workspace UI hides rectangle-only Dimensions controls when the active owner does
not provide that capability, and labels committed Part status separately from
the current draft. These presentation changes await a fresh actual GUI review.
