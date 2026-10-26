"""Immutable support disclosure strings; never geometry or action authority."""

from .support_intent_edit import support_decision


def support_status(decision):
    if decision and decision.get("status") == "assumed":
        return "ASSUMPTION ACTIVE", "INFO"
    if decision and decision.get("status") == "exact":
        return "Support: exact face", "ORIENTATION_NORMAL"
    return "Support unverified", "INFO"



def support_text(feature, result):
    policy = "Preserve logical plane" if "support_intent" in feature else "Strict exact face"
    detail = "Sketch support policy: " + policy + "."
    if "support_intent" in feature:
        detail += " Orientation: " + (
            "Minimal twist" if "orientation" in feature["support_intent"] else "World axes"
        ) + "."
    error = ""
    if result is not None:
        try:
            decision = support_decision(feature, result)
            text, icon = support_status(decision)
            detail += "\n" + text + ". " + decision.get("reason", "")
        except ValueError as exc:
            text, icon = "Support needs review", "ERROR"
            error = str(exc)
            detail += "\nNeeds review: " + error
    else:
        text, icon = support_status(None)
        detail += "\nSupport unverified. Review Support checks its current ancestry."
    return text, icon, detail, error
