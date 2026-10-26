# 1.15.0 Windows integration candidate

This candidate integrates guarded bundled Windows setup, runtime capture and
currentness with the existing Linux workflow. External Windows Python selection
remains unavailable. Native OCCT and SolveSpace stay in the owned sidecar.

Fresh bundled Windows preferences use a finite 240-second timeout. Linux and
unbundled defaults remain 60 seconds. Saved explicit values are never migrated
or overwritten. Cancellation, process ownership and cleanup guards are unchanged.

Earlier Windows test host candidate sources passed native Blender background creation,
live-child cancellation, stale-result rejection, STL/STEP, save and independent
reopen. Separate fresh-default and saved-preference checks passed. These results
are source-specific: current-source installer, responsive Replay and Edit Gear
Pair qualification must be reported separately, not inferred from older builds.
Interactive Windows GUI, Undo and arbitrary launcher configurations are not
qualified. Restricted AppContainer launcher visibility fails closed.

The delivered 1.14 Linux files are unchanged. No full historical-suite pass,
universal topological naming, manufacturing fit, strength or continuous collision
guarantee is claimed. All 42 inherited material/source declarations remain
unresolved; packaging is not legal or source-correspondence clearance.
