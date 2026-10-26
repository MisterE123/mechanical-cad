# MCAD-TNP-BLEND-001: Selected blend surface owns exact generated identity

Fixture: Selected box-edge chamfer and circular cylinder fillet.

Mutation: Change profile size and blend size; save and reopen.

Native construction is the proof, not geometric similarity. New surface identities
belong to their creating feature. Test coverage: `tests/integration/test_selected_blend_surface.py`
and `tests/blender_selected_blend_surface_smoke.py`. These establish targeted native and headless
Blender behavior, not full interactive or installed-package qualification.

Ambiguous histories remain unavailable. Use Edit Feature to correct its authored
selection, opening or size; no snapshot index becomes persistent identity.
