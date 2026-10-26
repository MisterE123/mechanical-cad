"""Linux native quit with a real owned sketch sidecar and publication owner.

Run with repository Python, MCAD_ROOT=/repo and BLENDER=/path/to/blender.
The launcher only signals a child whose PID is still rooted in its exact unique
fixture directory. An independent control child must survive Blender's exit.
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
    raise SystemExit("Set BLENDER to the native Blender 5.2.2 LTS executable.")
if not sys.platform.startswith("linux"):
    raise SystemExit("This exact owned-process exit gate currently requires Linux /proc.")
PYTHON = os.environ.get("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))


def owned_process(pid, folder):
    try:
        return Path(f"/proc/{pid}/cwd").resolve(strict=True) == folder
    except (FileNotFoundError, PermissionError):
        return False


with tempfile.TemporaryDirectory(prefix="mcad-sketch-exit-child-") as directory:
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
    script = folder / "quit_with_owned_sketch_job.py"
    script.write_text(
        textwrap.dedent(f"""\
        import os
        from pathlib import Path
        import sys
        import time
        import bpy
        ROOT = Path({str(ROOT)!r})
        FOLDER = Path({str(folder)!r})
        os.environ['MCAD_ROOT'] = str(FOLDER)
        os.environ['MCAD_PYTHON'] = {PYTHON!r}
        sys.path.insert(0, str(ROOT / 'blender_addon'))
        from mechanical_cad_blender import register, registration
        from mechanical_cad_blender import assembly_job_ui as ui
        from mechanical_cad_blender import document_state, draft_dispatch, execution_lease
        from mechanical_cad_blender import general_sketch_draft as drafts
        from mechanical_cad_blender import general_authoring, part_publication
        from mechanical_cad_blender import sketch_pending as pending
        from mechanical_cad_blender import guarded_transport, sketch_session, sidecar_job
        register()
        assert bpy.app.version == (5, 2, 2)
        assert registration._before_blender_exit in bpy.app.handlers.exit_pre
        BASE = '{{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{{}},"features":[],"active_feature":null}}'
        RAW = ' \\tinvalid_radius + ( 🛠\\n'
        scene = bpy.context.scene
        scene.mechanical_cad.document_json = BASE
        scene['unrelated_exit_value'] = 'keep exact'
        other = bpy.data.scenes.new('Unrelated exit scene')
        other['unrelated_exit_value'] = 'also exact'
        other.mechanical_cad.sketch_notice = 'keep unrelated notice'
        commands = drafts.GeneralSketchDraft(BASE)
        _, circle = commands.execute(drafts.AddCircle(drafts.PointSeed(1, 2), 4)).entity_ids
        driver = commands.execute(drafts.AddRelation('radius', (circle,), value=4)).constraint_id
        commands.begin_edit(driver)
        commands.update_edit(RAW)
        wrapper = general_authoring.GeneralSketchAuthoringState.from_v1_draft(commands)

        class TestSession(sketch_session.SketchSession):
            intent = None
            pending = None
            detach_count = 0

            def _detach_input(self):
                self.detach_count += 1
                assert not self.alive and sketch_session.active_session() is None
                self.intent.retire()
                assert self.intent._binding is None
                pending.cancel(self.pending, 'Exit input retirement')
                ui.ensure_supervisor()

            def checkpoint(self):
                raise AssertionError('Exit must not checkpoint or save scene data')

        window = bpy.context.window
        area = next(item for item in window.screen.areas if item.type == 'VIEW_3D')
        region = next(item for item in area.regions if item.type == 'WINDOW')
        with bpy.context.temp_override(window=window, area=area, region=region):
            owner = TestSession(bpy.context, wrapper)
            owner.start_resources((), 'Exit lifecycle fixture')
            owner.intent = part_publication.prepare(bpy.context, wrapper.candidate())
            owner.pending = pending.prepare_guarded(
                owner.intent.prepared,
                {{'session': owner.session_id, 'draft': draft_dispatch.dumps(wrapper)}},
                selection=owner.intent.selection, owner_token=owner.intent.owner_token,
            )
        ui.ensure_supervisor()
        handle = owner.pending
        assert type(handle._job) is guarded_transport.GuardedJob
        assert type(handle._job._job) is sidecar_job.SidecarJob
        assert handle.selection is owner.intent.selection
        assert handle.selection.project_root == str(FOLDER)
        deadline = time.monotonic() + 10
        while not (FOLDER / 'owned-pid').exists():
            assert time.monotonic() < deadline, 'owned sketch sidecar did not start'
            assert not handle.done, handle.status()
            time.sleep(.01)
        assert handle._job.state == 'running'
        assert execution_lease.is_busy()
        before = document_state._snapshot_fields(scene.mechanical_cad)
        unrelated_before = document_state._snapshot_fields(other.mechanical_cad)
        saved_wrapper = draft_dispatch.dumps(wrapper)
        scene_ids = {{item.as_pointer() for item in bpy.data.scenes}}

        def no_result(*args, **kwargs):
            raise AssertionError('Exit consumed a native response')

        handle._job.result = no_result

        def verify_exit(_dummy):
            assert not owner.alive and owner.detach_count == 1
            assert not owner.cleanup_errors and owner.timer is None and not owner.handles
            assert sketch_session.active_session() is None
            assert owner.intent.retired and owner.intent._binding is None
            assert owner.intent._workspace is None and owner.intent._owner_snapshot is None
            assert handle.done and handle._job.done and not pending._ACTIVE
            assert handle.status()['phase'] == 'cancelled'
            assert not execution_lease.is_busy()
            assert not bpy.app.timers.is_registered(ui._supervise)
            assert document_state._snapshot_fields(scene.mechanical_cad) == before
            assert document_state._snapshot_fields(other.mechanical_cad) == unrelated_before
            assert scene['unrelated_exit_value'] == 'keep exact'
            assert other['unrelated_exit_value'] == 'also exact'
            assert {{item.as_pointer() for item in bpy.data.scenes}} == scene_ids
            assert draft_dispatch.dumps(wrapper) == saved_wrapper
            assert wrapper.command_draft.pending_edit.raw_text == RAW
            print('SKETCH_EXIT_OWNER_AND_PUBLICATION_RETIRED', flush=True)

        bpy.app.handlers.exit_pre.append(verify_exit)
        print('EXIT_WITH_ACTIVE_OWNED_SKETCH_SIDECAR',
              (FOLDER / 'owned-pid').read_text(), flush=True)
        bpy.ops.wm.quit_blender()
    """),
        encoding="utf-8",
    )
    control_folder = folder / "unrelated-control"
    control_folder.mkdir()
    control = subprocess.Popen([PYTHON, "-c", "import time; time.sleep(60)"], cwd=control_folder)
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
        assert "EXIT_WITH_ACTIVE_OWNED_SKETCH_SIDECAR" in result.stdout
        assert "SKETCH_EXIT_OWNER_AND_PUBLICATION_RETIRED" in result.stdout
        pid = int((folder / "owned-pid").read_text())
        assert not Path(f"/proc/{pid}").exists(), (
            f"Owned sketch sidecar {pid} survived normal Blender exit"
        )
        assert control.poll() is None and owned_process(control.pid, control_folder), (
            "Independent control process must survive addon exit cleanup"
        )
        print("SKETCH_JOB_EXIT_SMOKE_OK", "owned child reaped; unrelated child survives")
    finally:
        pidfile = folder / "owned-pid"
        if pid is None and pidfile.exists():
            pid = int(pidfile.read_text())
        if pid is not None and owned_process(pid, folder):
            os.kill(pid, signal.SIGKILL)
        if control.poll() is None and owned_process(control.pid, control_folder):
            control.terminate()
            control.wait(timeout=5)
