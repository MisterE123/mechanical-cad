# Temporary isolated sketch viewport

The bounded Line/Circle editor hides mesh context using only the captured native
`SpaceView3D.show_object_viewport_mesh` filter. The overlay calls this an isolated
sketch view. It is not face-attached or in-context reference editing, and it is
not the intended final contextual sketch design.

`MeshVisibilityLease` captures the original boolean before acquisition. Cleanup
first drops its captured reference, then conditionally restores that exact space.
If a user changed the filter back to true, cleanup preserves that change. A second
write of false cannot be distinguished from the value owned by the editor; this
is an explicit value-based ownership limitation. No fallback searches for a new
viewport are performed after an area changes or is removed.

GeneralSession acquires the resource only during start. Its shared owner cleanup
restores it on Finish, Discard, suspension, partial startup and retirement, even
if native cancellation or text-controller teardown raises. Cleanup errors remain
diagnostic; they cannot authorize a stale solve or publish a Part. The resource
does not touch object hide flags, collections, scene units, rendering visibility,
other viewports or canonical design data.

## Reproduce native headless coverage

Set `MCAD_ROOT` to this source checkout, `MCAD_PYTHON` to its prepared sidecar and
`BLENDER` to native Blender 5.2.2:

```sh
export MCAD_ROOT="$PWD" MCAD_PYTHON="$PWD/.venv/bin/python"
"$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python tests/blender_sketch_view_presentation_smoke.py
"$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python tests/blender_general_view_isolation_smoke.py
```

The resource suite checks two actual native viewports, exact unrelated-data
snapshots, area changes, invalid references and read/write failures. The owner
suite additionally checks real circle Check/Finish, Discard/Suspend, combined
teardown failures, partial acquisition and external filter changes. These tests
are headless lifecycle evidence; actual viewport readability is a separate GUI
gate.
