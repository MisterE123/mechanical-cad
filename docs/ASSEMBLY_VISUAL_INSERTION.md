# Fixed visual Insert-and-Mate (development)

This extends Preview Before Insert; that earlier milestone did not provide
visual mating. The new fixed-joint option constructs a detached new child and
incoming joint, then replays the complete insertion seed before face picking.
Parent and New child are explicit, named pick targets. Stable planar semantic
faces alone can become saved supports. Curved, missing, ambiguous and cross-face
edge hits refuse; tessellation indices are never saved as identity.

Default picking considers every candidate component and visible foreign scene
geometry. Coincident/obscured targets refuse rather than guess. **Highlighted
only** is an explicit opt-in: the named cyan target is shown through other
geometry and the panel states that other geometry is ignored. Its own nearest
surface and semantic checks remain strict. Switching targets resets this mode.
No camera, component transform, selection or display visibility is changed for
picking. Named-connector insertion remains the alternative without face picking.
Quad View is deliberately refused, including switching into it mid-session.

The picker is a bounded CPU projection of validated seed meshes and poses, held
separately from Blender objects. Accepted display exclusions use captured,
revalidated object identities, not tags copied onto foreign objects. The new child
never becomes an accepted-owned object until final Apply. The default total
picking budget is 24,000 triangles across instance copies; exceeding it refuses
rather than silently discarding potential blockers. Geometry preparation is not
performed per draw.

Both faces form an atomic detached JointDraft edit. Rejected pairs retain the
prior candidate but revoke ready authority. Stable generated frame/instance/joint
IDs survive retries. Picking is frozen during final replay; restarting explicitly
returns to the immutable seed view and discards picked supports. Final Apply
freshly replays and compares complete geometry/topology/source/pose to the final
ready projection, not the seed. Original accepted Assembly/raw working Part and
live context/backend remain the publication base throughout. Cancel leaves no
new child, joint, source, definition or support frames. No saved schema changes.

## Current verification scope

- Detached composition/wrapper: 25 real-kernel checks; only new child moved by
  the selected cap pair, while all prior instance poses, joints and sources stayed
  exact. Failed second-face selection preserved the prior candidate.
- Native Blender owner: 44 checks plus 9 independent saved-file reopen checks.
  Controlled viewport-ray ports exercised the actual pick method, default overlap
  refusal, explicit highlighted-only reset, nonpublishing seed/final replay,
  Cancel and one atomic Apply. Exact child placement and geometry persisted.
  These are not a substitute for the actual registered-dialog GUI journey.
- Combined focused insertion/source-preview/motion/JointDraft tests: **356 passed**;
  Ruff clean. Static review found a wrong-view risk in Quad View; constructor and
  live-context regressions now verify its explicit refusal.
- Native exact-reference foreign occlusion passed **11 checks**, including a
  foreign object with copied ownership tags and hidden/unhidden behavior. A
  separate attempted Quad View toggle in headless Blender crashed before its
  success marker; crash evidence is retained and that toggle was not repeated.
  Actual Quad View behavior remains unqualified beyond the pure guard tests.
- Actual registered-dialog GUI: coincident-origin reuse refused default picking;
  explicit highlighted-only picked Parent then New child, resetting the opt-in
  between targets. Both cap.end picks produced the expected adjacent full ghost.
  Cancel preserved exact Assembly, working Part, accepted report and empty
  operator history. Final ready wording was clarified to describe the full
  Assembly, not the now-inactive picking isolation; 82 focused owner/source/
  insertion checks passed after that change. Fresh GUI Apply produced current
  four-instance geometry and one child-modal operator-history entry. Undo and
  Redo restored the exact original/applied graphs and working Part. History
  correctly marks display dirty pending fresh replay; explicit Rebuild restored
  current geometry. The exact GUI file was saved (SHA-256
  `c7f7e0e9520b009d080cd731def0517c19548e986972159d3ba77ca1f2b0288f`).
  Independent reopening passed **22 checks**: exact graph/working Part and four
  poses; coincident connector origins and physical face centroids; opposing
  outward normals; source width 20, volume 2000; unchanged prior joints and file
  bytes. No mesh-ID warning appeared in this run; the earlier diagnostic remains
  unresolved. This is not an installed release.

Frozen 1.28/1.29 installers remain unchanged. Full aggregate, Windows and exact
package-install qualification have not been rerun. The earlier insertion Undo
mesh-ID decrement diagnostic remains open; no speculative cleanup change is
included. The separately denied slider GUI Apply/Undo is not exercised.
