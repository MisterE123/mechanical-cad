"""Linux native Blender exit gate for an owned, actually running sidecar.

Run with the repository Python, MCAD_ROOT=/repo and BLENDER=/path/to/blender.
The launcher creates its own temporary module; no repo/model source is modified.
Only the PID emitted by that module, still rooted in that unique temp directory,
may be signalled for test teardown. Missing/reused PIDs are never signalled.
"""

import os
import signal
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
BLENDER = os.environ.get("BLENDER")
if not BLENDER:
    raise SystemExit("Set BLENDER to the native Blender 5.2 LTS executable.")
if not sys.platform.startswith("linux"):
    raise SystemExit("This exact owned-process exit gate currently requires Linux /proc.")
PYTHON = os.environ.get("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))


def owned_process(pid, folder):
    try:
        return Path(f"/proc/{pid}/cwd").resolve(strict=True) == folder
    except (FileNotFoundError, PermissionError):
        return False


with tempfile.TemporaryDirectory(prefix="mcad-exit-child-") as directory:
    folder = Path(directory).resolve()
    package = folder / "src/mechanical_cad"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "sidecar.py").write_text(
        textwrap.dedent("""\
        import json
        import os
        from pathlib import Path
        import sys
        import time
        json.load(sys.stdin)
        Path('owned-pid').write_text(str(os.getpid()), encoding='ascii')
        time.sleep(60)
        print('{"protocol_version":1,"ok":true}')
    """),
        encoding="utf-8",
    )
    script = folder / "quit_with_owned_job.py"
    script.write_text(
        textwrap.dedent(f"""\
        import json
        import os
        from pathlib import Path
        import sys
        import time
        from unittest.mock import patch
        import bpy
        ROOT = Path({str(ROOT)!r})
        FOLDER = Path({str(folder)!r})
        os.environ['MCAD_ROOT'] = str(ROOT)
        os.environ['MCAD_PYTHON'] = {PYTHON!r}
        sys.path.insert(0, str(ROOT / 'blender_addon'))
        from mechanical_cad_blender import register
        from mechanical_cad_blender import assembly_pending as pending
        from mechanical_cad_blender import assembly_state as state
        from mechanical_cad_blender import document_state
        from mechanical_cad_blender.backend_selection import BackendSelection
        register()
        assembly = json.loads((ROOT / 'examples/reused_blocks.mcad-assembly.json').read_text())
        document_state._populate_document(bpy.context.scene, assembly['part_sources'][0]['document'])
        state.commit_candidate(bpy.context, assembly)
        selection = BackendSelection.capture(
            str(FOLDER), {PYTHON!r}, 60, generation=0, lifetime_id='exit-test'
        )
        with (
            patch.object(state, '_configuration', return_value=(selection, 0.1)),
            patch.object(state, '_current_selection', return_value=selection),
        ):
            handle = pending.prepare(bpy.context, 'assembly_check')
        deadline = time.monotonic() + 10
        while not (FOLDER / 'owned-pid').exists():
            assert time.monotonic() < deadline, 'owned sidecar did not start'
            assert not handle.done, handle.status()
            time.sleep(.01)
        assert handle._job.state == 'running'
        print('EXIT_WITH_ACTIVE_OWNED_SIDECAR', (FOLDER / 'owned-pid').read_text(), flush=True)
        bpy.ops.wm.quit_blender()
    """),
        encoding="utf-8",
    )
    pid = None
    try:
        result = subprocess.run(
            [
                BLENDER,
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python-expr",
                "import sys; sys.dont_write_bytecode = True",
                "--python",
                str(script),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=25,
        )
        print(result.stdout)
        assert result.returncode == 0, f"Blender exited with status {result.returncode}"
        assert "EXIT_WITH_ACTIVE_OWNED_SIDECAR" in result.stdout
        pid = int((folder / "owned-pid").read_text())
        assert not Path(f"/proc/{pid}").exists(), (
            f"Owned sidecar {pid} survived normal Blender exit"
        )
        print("ASSEMBLY_JOB_EXIT_SMOKE_OK", "owned child was reaped before Blender exited")
    except subprocess.TimeoutExpired as exc:
        print(exc.stdout.decode() if isinstance(exc.stdout, bytes) else exc.stdout, flush=True)
        raise
    finally:
        pidfile = folder / "owned-pid"
        if pid is None and pidfile.exists():
            pid = int(pidfile.read_text())
        if pid is not None and owned_process(pid, folder):
            os.kill(pid, signal.SIGKILL)
