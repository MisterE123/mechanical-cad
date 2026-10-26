"""Shared ownership tags, unit conversion and Scene state access.

This module does not import Blender or any other add-on module."""

OWNER_KEY = "mechanical_cad_owner"

MIN_BLENDER_VERSION = (5, 2, 0)


FEATURE_KEY = "mechanical_cad_feature_id"


DOCUMENT_KEY = "mechanical_cad_document_id"


MM_TO_METERS = 0.001


def _state(context):
    return context.scene.mechanical_cad
