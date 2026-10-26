# Informational open-sketch status

During a current checked sketch draft, a validated `profile_check` with
`ready: false` and native `open_profile` now reads **Open sketch · close a loop**, with an informational icon. Solver status and actual DoF remain
separate and unchanged. This is not an error just because it has no filled area.

This is presentation only. The current owner still obtains exact-bound evidence
through `current_solution_response`; v2/v3 bridge validation checks the open
code against source connectivity. There is no inference from entity counts,
visible geometry, solver success, or diagnostic prose. Other profile codes keep
the existing warning. Pending, missing, stale, failed-solve and failed-build
presentations are unchanged. Expanded details retain the complete native reason.

Open sketches can remain saved sketches. This change does not enable Extrude,
assert native solid validity, or promise suitability for every path operation.
Saved-sketch profile eligibility and operation guards are untouched.

## Focused source verification

- 126 compact-status / saved-sketch Extrude unit and real draw-port tests passed.
- Two native integration cases passed: the horizontal one-Line geometry from the
  retained 2026-10-24 axis-lock GUI evidence, using result versions 2 and 3. Both
  reported `open_profile`, false profile readiness and 3 DoF, survived exact
  request/response bridge validation, and replayed as a saved sketch with an
  unavailable profile. The saved-profile helper still rejects extrusion readiness.
- Changed-file Ruff checks passed.

These are source tests, including native solver/replay and simulated draw ports,
not a new interactive GUI, installed archive, full historical-suite or Windows
qualification. Frozen releases are unchanged.
