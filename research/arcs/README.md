# Circular-arc contract probes

These small research programs exercise the pinned native dependencies directly.
They are not production geometry, a profile validator, a new accepted file format,
or GUI qualification. The integration contract is
[docs/NEXT_SKETCH_ARCS.md](../../docs/NEXT_SKETCH_ARCS.md).

The initial evidence used released source `1a27e74` on Linux, CPython 3.12.14,
slvs 3.2 and cadquery-ocp-novtk 8.0.1.1.0. The independently prepared reports retain
alternatives and limits; the integration contract records the selected policies.
No extra dependency or network operation is needed for these probes.

## Reproduce from the repository root

Use the project's configured sidecar environment with the sketch extra installed.
Choose a fresh output directory. The native solver probe isolates each case in a
child process; this is intentional and takes longer than the kernel probes.

```sh
export PYTHONDONTWRITEBYTECODE=1
export MCAD_ROOT="$PWD"
export MCAD_ARC_EVIDENCE="$(mktemp -d)/kernel"
mkdir -p "$MCAD_ARC_EVIDENCE"
.venv/bin/python research/arcs/solver/probe_arcs.py \
  --output "${MCAD_ARC_EVIDENCE%/kernel}/solver.json"
.venv/bin/python research/arcs/kernel/probe_contract.py
.venv/bin/python research/arcs/kernel/probe_boundaries.py
.venv/bin/python research/arcs/kernel/probe_lineage.py
.venv/bin/python research/arcs/kernel/verify_evidence.py
```

Expected markers: solver **65 checks passed** in its JSON `checks` summary;
kernel **97 bounded evidence assertions passed**. Read each program's result
and exit status; a source change or different runtime can alter observations.
The original results in each `reference/` folder are immutable comparison evidence,
not substitute fresh test results. Re-running does not modify those files.

- [Solver observations and official sources](solver/FINDINGS.md)
- [Profile/kernel observations and scope](kernel/FINDINGS.md)

All code uses the project's GPL-3.0-or-later license. Native libraries retain their
own licenses as recorded in the repository's third-party notices.
