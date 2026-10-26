"""Idempotent compound CAD suffixes, independent of Blender's single-suffix helper."""

from pathlib import Path


def normalized_document_path(path, suffix):
    path = Path(path)
    if path.name.lower().endswith(suffix.lower()):
        return path
    stem_suffix = suffix.removesuffix(".json")
    if path.name.lower().endswith(stem_suffix.lower()):
        return path.with_name(path.name + ".json")
    if path.suffix.lower() == ".json":
        return path.with_name(path.name[:-5] + suffix)
    return path.with_name(path.name + suffix)


def normalized_export_check(self, context):
    """File-selector check must not strip .json repeatedly from a compound suffix."""
    if not self.filepath:
        return False
    normalized = str(normalized_document_path(self.filepath, self.filename_ext))
    changed = normalized != self.filepath
    if changed:
        self.filepath = normalized
    return changed
