"""Native RNA history filtering; no geometry or interactive GUI claim."""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from bl_ui import UI_UL_list

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import document_state, panels, register, unregister  # noqa: E402

register()
state = bpy.context.scene.mechanical_cad
document = json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
document["features"][0]["label"] = "Mounting plate outline"
document["features"][1]["label"] = "Mounting plate solid"
document_state._populate_document(bpy.context.scene, document)
state.feature_index = 1
before = (state.document_json, state.active_feature, state.feature_index, tuple(state.features))
# Reproduce the old gap with Blender's shipped equivalent of default C filtering:
assert all(not item.name for item in state.features)
assert UI_UL_list.filter_items_by_name("Mounting", 1 << 30, state.features) == [0, 0]


class Filter:
    bitflag_filter_item = 1 << 30
    filter_name = ""
    use_filter_show = False
    use_filter_sort_lock = False
    use_filter_sort_reverse = True
    use_filter_invert = True
    _matching_flags = panels.MCAD_UL_features._matching_flags
    filter_items = panels.MCAD_UL_features.filter_items
    draw_filter = panels.MCAD_UL_features.draw_filter


class Layout:
    def __init__(self):
        self.labels = []
        self.buttons = []
        self.props = []

    def row(self, **kwargs):
        return self

    def label(self, **kwargs):
        self.labels.append(kwargs.get("text", ""))

    def prop(self, data, name, **kwargs):
        self.props.append(name)

    def operator(self, name, **kwargs):
        op = SimpleNamespace()
        self.buttons.append((name, op))
        return op


filter_ui = Filter()
bit = filter_ui.bitflag_filter_item
for query, expected in [
    ("", []), ("mountING", [bit, bit]), ("outline", [bit, 0]),
    (state.features[1].feature_id, [0, bit]), ("not present", [0, 0]),
    ("Mount*solid", [0, bit]), ("[", [0, 0]),
]:
    filter_ui.filter_name = query
    flags, order = filter_ui.filter_items(bpy.context, state, "features")
    assert flags == expected, (query, flags)
    assert order == []
    assert filter_ui.use_filter_sort_lock and not filter_ui.use_filter_sort_reverse
    assert not filter_ui.use_filter_invert
    if query:
        assert filter_ui.use_filter_show
    for index, flag in enumerate(flags):
        if flag & bit:
            layout = Layout()
            with patch.object(panels, "row_presentation", return_value=("DOT", False)) as row:
                panels.MCAD_UL_features.draw_item(
                    filter_ui, bpy.context, layout, state, state.features[index],
                    0, state, "feature_index", index,
                )
            assert row.call_args.args[-1] == index
            assert layout.buttons[0][1].feature_id == state.features[index].feature_id
    assert (state.document_json, state.active_feature, state.feature_index, tuple(state.features)) == before

filter_ui.filter_name = "outline"
layout = Layout()
filter_ui.draw_filter(bpy.context, layout)
assert layout.props == ["filter_name"]  # No sorting or inversion controls.
assert "1 of 2 features shown" in layout.labels
assert "Selection hidden by search" in layout.labels
filter_ui.filter_name = "not present"
layout = Layout()
filter_ui.draw_filter(bpy.context, layout)
assert "No matches · clear search" in layout.labels
filter_ui.filter_name = ""
filter_ui.use_filter_show = False
assert filter_ui.filter_items(bpy.context, state, "features") == ([], [])
assert not filter_ui.use_filter_show  # Clearing permits the existing collapsed drawer.
layout = Layout()
filter_ui.draw_filter(bpy.context, layout)
assert not layout.labels
# Empty and maximum-sized bounded histories, with duplicate visible labels.
filter_ui.filter_name = "duplicate"
assert filter_ui._matching_flags([]) == []
items = [SimpleNamespace(label="Duplicate", feature_id=f"stable_{index}") for index in range(256)]
assert filter_ui._matching_flags(items) == [bit] * 256
filter_ui.filter_name = "stable_255"
assert filter_ui._matching_flags(items) == [0] * 255 + [bit]
assert (state.document_json, state.active_feature, state.feature_index, tuple(state.features)) == before
unregister()
print("HISTORY_FILTER_SMOKE_OK", flush=True)
