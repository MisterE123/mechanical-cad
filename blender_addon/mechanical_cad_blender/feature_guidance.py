"""Short actionable explanations for feature dialogs; keep exact diagnostic detail."""

from .linked_extrusion_edit import SharedToolConsentRequired

_HINTS = {
    "fillet": "Try a smaller radius or a different stable edge selection.",
    "chamfer": "Try a smaller chamfer distance or a different stable edge selection.",
    "shell": "Try a thinner wall. An inward offset may fail on tight corners or thin regions.",
    "union": "The selected solids must overlap or touch so the result is one connected solid.",
    "intersection": "The selected solids need a nonempty shared solid volume.",
    "cut": "Check the base and tool selection and that the cut leaves one valid solid.",
    "revolve": "Choose a closed profile that does not cross the axis; check the axis position and angle.",
    "loft": "Choose 2–16 distinct compatible closed profiles without holes; check the authored traversal order and positions.",
    "sweep": "Use one closed section and a solved open planar line/arc path. Review Center at path start, roll and reversed traversal, or explicitly Keep authored placement.",
    "linear_pattern": "Copies must overlap or touch to form one connected solid; reduce spacing if needed.",
    "circular_pattern": "Copies must join into one connected solid; check axis, spacing and count.",
    "sketch_face_rectangle": "Choose a current stable planar face. Missing or split references need an explicit replacement.",
    "sketch_face_circle": "Choose a current stable planar face. Missing or split references need an explicit replacement.",
}


def feature_error(kind, error):
    detail = str(error)
    if isinstance(error, SharedToolConsentRequired):
        return (
            detail + "\nModel unchanged. Enable "
            "'Also update the shared tool and listed features' in Edit Feature, or Cancel."
        )
    hint = _HINTS.get(kind)
    if kind == "shell" and any(word in detail.lower() for word in ("opening", "planar", "pick")):
        hint = "Review the checked opening faces; choose unique stable planar faces on the base."
    return detail if hint is None else f"{detail}\n{hint}"
