# Independent arc-core audit evidence

This compact set records a read-only independent audit of the preserved first arc-core slice and its repaired integration on immutable 0.5.1. Read REVIEW.md for findings, their dispositions and qualification limits. MANIFEST.json lists every retained file and its SHA256, plus exact source hashes reviewed at capture. The original preservation ZIP and larger raw logs remain in the engineering evidence archive; they are not duplicated here.

## Reproduce

Use the pinned Linux CPython/native environment from the project (slvs 3.2). These scripts load only the source selected through PYTHONPATH; they do not edit the source checkout or use GitHub. They emit JSON to stdout. `probe_native_ceiling.py` also observes Linux process resource usage, which is not a limit guarantee.

From the repository root after placing this directory at `research/arcs/core_audit`:

```sh
export PYTHONPATH="$PWD/src"
export PYTHONDONTWRITEBYTECODE=1
PYTHON="$PWD/.venv/bin/python"
AUDIT="$PWD/research/arcs/core_audit"
timeout 60 "$PYTHON" "$AUDIT/probes/probe_native_ceiling.py" intrinsic256
timeout 60 "$PYTHON" "$AUDIT/probes/probe_native_ceiling.py" rows1024
"$PYTHON" "$AUDIT/probes/probe_arc_domains.py"
"$PYTHON" "$AUDIT/probes/probe_arc_branches.py"
"$PYTHON" "$AUDIT/probes/probe_false_success.py"
"$PYTHON" "$AUDIT/probes/probe_legacy_compat.py" "$PWD/examples" > /tmp/arc-legacy-evidence.json
sha256sum /tmp/arc-legacy-evidence.json
```

For a differential check, run the compatibility script against separate baseline and candidate source roots, keeping the same examples directory, and compare stdout bytes using `cmp`. The retained receipt records the exact matched output hash and byte count. Do not compare timings/RSS as golden values. All probes are Ruff-clean; the numeric probes contain independent atomicity/domain assertions.

This is core evidence only. It does not qualify result-v3 service consumers, mixed profiles, B-rep construction, topology lineage, assembly/UI/journal support or installed Blender behavior.
