"""Explain current parameter dependencies without changing model intent."""

import ast


def _references(value, name):
    if not isinstance(value, str):
        return False
    try:
        expression = ast.parse(value, mode="eval")
    except (SyntaxError, ValueError):
        return False
    return any(isinstance(node, ast.Name) and node.id == name for node in ast.walk(expression))


def parameter_usage(document, name):
    usages = []
    for key, value in document.get("parameters", {}).items():
        if key != name and _references(value, name):
            usages.append("Parameter: " + key)
    for feature in document.get("features", []):
        label = feature.get("label") or feature.get("id", "Feature")
        for field, value in feature.get("params", {}).items():
            if _references(value, name):
                usages.append(f"{label}: {field.replace('_', ' ')}")
        for constraint in feature.get("sketch", {}).get("constraints", []):
            if _references(constraint.get("value"), name):
                relation = constraint.get("id") or constraint.get("kind", "dimension")
                usages.append(f"{label}: {relation}")
    return tuple(dict.fromkeys(usages))
