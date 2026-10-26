# MCAD-TNP-SHELL-001: Open Shell inner wall and lip own exact native construction

Fixture: 20×15×10 open enclosure and cylindrical cup.

Mutation: Change wall thickness and base size; deliberately change the selected opening; save and reopen.

Native construction is the proof, not geometric similarity. New surface identities
belong to their creating feature. Test coverage: `tests/integration/test_shell_generated_surfaces.py`
and `tests/blender_shell_inner_surface_smoke.py`. These establish targeted native and headless
Blender behavior, not full interactive or installed-package qualification.

Ambiguous histories remain unavailable. Use Edit Feature to correct its authored
selection, opening or size; no snapshot index becomes persistent identity.

The `shell.opening_lip` reference means the lip of the current selected opening.
An explicit opening edit moves that reference; current opening provenance must
still be exact and unique. Inner-wall references do not switch to a new source.
