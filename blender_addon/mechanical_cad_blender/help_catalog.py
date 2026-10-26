"""Searchable hierarchy over the same topic text used by contextual help."""

import re
import textwrap

from .help_topics import HELP_TOPICS

CATEGORIES = ("Sketch", "Part", "Assembly", "Troubleshooting")
# Short common-language aliases supplement (rather than duplicate) the help text.
ALIASES = {
    "sketch.support_intent": "topological naming tnp split face plane support assumption preserve strict repair undo slot centroid lineage",
    "sketch.projection": "offset reference project use solid edge linked associative",
    "sketch.constraints": "overconstrained conflict underconstrained freedom dof fix snap",
    "sketch.general": "draw dimension trim extend tangent diameter radius arc line circle",
    "feature.cut": "pocket subtract remove hole",
    "feature.union": "boss join fuse add",
    "feature.shell": "hollow thickness enclosure lid",
    "assembly.faces": "mate facing flip roll centroid guess assumption unchecked contact",
    "geometry.actions": "check export step stl watertight mesh invalid precision",
    "error.rebuild": "failed blocked stale dirty timeout error regenerate rebuild",
    "intent.suggestion": "guess assumptions default wrong selected change override",
}


def category_for(topic):
    if topic.startswith("sketch.") or topic.startswith("feature.sketch_"):
        return "Sketch"
    if topic.startswith("assembly."):
        return "Assembly"
    if topic.startswith(("error.", "setup.", "verification.")) or topic in {
        "intent.suggestion",
        "units",
        "roadmap",
        "geometry.actions",
    }:
        return "Troubleshooting"
    return "Part"


def search_topics(query="", category="ALL"):
    """All query words must match, ignoring case and punctuation; stable ordering."""
    words = re.findall(r"\w+", query.casefold())
    matches = []
    for topic, (title, paragraphs) in HELP_TOPICS.items():
        if topic == "error.details":  # Empty dynamic diagnostic, not a guide chapter.
            continue
        group = category_for(topic)
        if category != "ALL" and category != group:
            continue
        haystack = " ".join((topic, group, title, *paragraphs, ALIASES.get(topic, "")))
        haystack = " ".join(re.findall(r"\w+", haystack.casefold()))
        if all(word in haystack for word in words):
            matches.append(topic)
    return sorted(
        matches,
        key=lambda key: (
            -sum(word in HELP_TOPICS[key][0].casefold() for word in words),
            CATEGORIES.index(category_for(key)),
            HELP_TOPICS[key][0].casefold(),
            key,
        ),
    )


def topic_pages(topic):
    """Six bounded lines per page; no clipped paragraphs or native dependencies."""
    paragraphs = HELP_TOPICS[topic][1]
    lines = []
    for paragraph in paragraphs:
        lines.extend(textwrap.wrap(paragraph, width=68, break_on_hyphens=False))
        lines.append("")
    return [lines[i : i + 6] for i in range(0, len(lines), 6)] or [["No explanation available."]]
