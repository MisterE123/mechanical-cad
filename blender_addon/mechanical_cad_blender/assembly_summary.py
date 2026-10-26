"""Presentation-only assembly verdicts. Currency is supplied by guarded state reads."""

import json


def verification_summary(report_json, *, current):
    """Never promote persisted verdicts to current authority or contact to clearance."""
    if not current:
        return ("Check again" if report_json else "Not checked", "INFO")
    try:
        response = json.loads(report_json)
        report = response["report"]
        action = response["action"]
        if not isinstance(report, dict):
            return "Check unavailable", "ERROR"
    except (ValueError, KeyError, TypeError):
        return "Check unavailable", "ERROR"
    if action not in {"assembly_check", "assembly_sample"}:
        return "Not checked", "INFO"
    prefix = "Samples: " if action == "assembly_sample" else ""
    if report.get("known_interference"):
        return prefix + "Interference found", "ERROR"
    if report.get("known_clearance_violation"):
        return prefix + "Clearance violation", "ERROR"
    if report.get("complete") is not True:
        return prefix + "Check incomplete", "ERROR"
    if report.get("policy_accepted") is True:
        return prefix + "Contact policy accepted", "INFO"
    if report.get("has_threshold_contacts"):
        return prefix + "Contact uncertain", "ERROR"
    if not (report.get("verification_basis") or {}).get("configured"):
        return prefix + "Measured · no pass policy", "INFO"
    if report.get("passed") is True:
        return prefix + "Measured pass", "CHECKMARK"
    return prefix + "Check did not pass", "ERROR"
