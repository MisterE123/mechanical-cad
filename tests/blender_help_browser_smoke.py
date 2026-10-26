"""Background RNA/draw smoke only; does not claim manual popup usability."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(os.environ["MCAD_ROOT"]) / "blender_addon"))
from mechanical_cad_blender import help_browser  # noqa: E402


class Layout:
    def __init__(self):
        self.labels = []

    def label(self, *, text, **kwargs):
        self.labels.append(text)

    def prop(self, *args, **kwargs):
        pass

    def row(self, **kwargs):
        return self


cls = help_browser.MCAD_OT_help_browser
bpy.utils.register_class(cls)
try:
    before = bpy.context.scene.as_pointer(), list(bpy.data.objects)
    props = bpy.context.window_manager.operator_properties_last(cls.bl_idname)
    props.query = "facing normals"
    assert props.selected == "assembly.faces"
    props.reading = True
    props.next = True
    assert props.page == 2 and not props.next
    props.previous = True
    assert props.page == 1 and not props.previous
    props.previous = True
    assert props.page == 1
    props.category = "Sketch"
    assert props.selected == "NONE" and not props.reading and props.page == 1
    props.query = "solid edge"
    assert props.selected == "sketch.projection"
    props.category = "Assembly"
    props.query = ""
    assert props.selected.startswith("assembly.")
    props.reading = True
    for _ in range(100):
        props.next = True
    assert props.page == len(help_browser.topic_pages(props.selected))
    # Draw all branches using actual RNA values, without opening an active GUI.
    for query, reading in [("missing_word", False), ("", False), ("facing", True)]:
        props.query = query
        props.reading = reading
        layout = Layout()
        proxy = SimpleNamespace(
            layout=layout,
            **{
                name: getattr(props, name)
                for name in ("query", "category", "selected", "reading", "page", "previous", "next")
            },
        )
        cls.draw(proxy, bpy.context)
        assert layout.labels[-1].startswith("Esc or click outside")
    props.reading = False  # Back keeps query/category/selection.
    assert props.query == "facing" and props.selected == "assembly.faces"
    assert before == (bpy.context.scene.as_pointer(), list(bpy.data.objects))
    assert bpy.ops.mcad.help_browser() == {"FINISHED"}
finally:
    bpy.utils.unregister_class(cls)
print("MCAD_HELP_BROWSER_SMOKE_OK")
