"""Non-mutating searchable Help popup; no nested authoring dialogs."""

from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator

from .help_catalog import CATEGORIES, category_for, search_topics, topic_pages
from .help_topics import HELP_TOPICS

# Blender requires callback enum strings to outlive draw calls. Keep all item
# strings and stable numeric identities module-owned, including the empty result.
_ITEMS = {
    topic: (topic, title, f"{category_for(topic)}: {title}", index)
    for index, (topic, (title, _)) in enumerate(HELP_TOPICS.items(), start=1)
}
_EMPTY = ("NONE", "No matching topics", "Clear search or choose All categories", 0)


def _items(self, context):
    return [_ITEMS[topic] for topic in search_topics(self.query, self.category)] or [_EMPTY]


def _filter_changed(self, context):
    matches = search_topics(self.query, self.category)
    self.selected = matches[0] if matches else "NONE"
    self.reading = False
    self.page = 1


def _selection_changed(self, context):
    self.page = 1


def _previous(self, context):
    if self.previous:
        self.page = max(1, self.page - 1)
        self.previous = False


def _next(self, context):
    if self.next:
        if self.selected in HELP_TOPICS:
            self.page = min(len(topic_pages(self.selected)), self.page + 1)
        self.next = False


class MCAD_OT_help_browser(Operator):
    bl_idname = "mcad.help_browser"
    bl_label = "Search CAD Help"
    bl_description = "Browse Sketch, Part, Assembly and Troubleshooting; search tools and errors"

    query: StringProperty(name="Search", options={"SKIP_SAVE"}, update=_filter_changed)
    category: EnumProperty(
        name="Category",
        items=[("ALL", "All categories", "Search every topic")]
        + [(name, name, f"Browse {name} help") for name in CATEGORIES],
        default="ALL",
        options={"SKIP_SAVE"},
        update=_filter_changed,
    )
    selected: EnumProperty(
        name="Topic",
        items=_items,
        options={"SKIP_SAVE"},
        update=_selection_changed,
    )
    reading: BoolProperty(name="Read topic", options={"SKIP_SAVE"})
    page: IntProperty(default=1, min=1, options={"HIDDEN", "SKIP_SAVE"})
    previous: BoolProperty(update=_previous, options={"SKIP_SAVE"})
    next: BoolProperty(update=_next, options={"SKIP_SAVE"})

    def invoke(self, context, event):
        _filter_changed(self, context)
        return context.window_manager.invoke_popup(self, width=600)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "query", text="Search", icon="VIEWZOOM")
        layout.prop(self, "category")
        matches = search_topics(self.query, self.category)
        if not matches:
            layout.label(text="No matching topics. Clear search or choose All categories.")
        elif not self.reading:
            layout.label(text=f"{len(matches)} topics: choose one, then Read topic.")
            layout.prop(self, "selected")
            layout.prop(self, "reading", text="Read topic", toggle=True, icon="BOOKMARKS")
        elif self.selected in matches:
            topic = self.selected
            layout.prop(self, "reading", text="Back to results", toggle=True, icon="BACK")
            layout.label(text=category_for(topic))
            layout.label(text=HELP_TOPICS[topic][0])
            pages = topic_pages(topic)
            page = min(self.page, len(pages))
            for index in range(6):
                lines = pages[page - 1]
                layout.label(text=lines[index] if index < len(lines) else " ")
            row = layout.row(align=True)
            previous = row.row(align=True)
            previous.enabled = page > 1
            previous.prop(self, "previous", text="Previous", toggle=True)
            row.label(text=f"{page} / {len(pages)}")
            following = row.row(align=True)
            following.enabled = page < len(pages)
            following.prop(self, "next", text="Next", toggle=True)
        layout.label(text="Esc or click outside to close. Help never changes your model.")

    def execute(self, context):
        return {"FINISHED"}
