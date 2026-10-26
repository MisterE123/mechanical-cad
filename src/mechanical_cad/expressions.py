"""Small arithmetic language for model parameters. Never executes Python code.

All values use the document's millimetres convention. Dimensional analysis and
unit-bearing formulas are deliberately outside this initial implementation.
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Mapping

from .errors import CADException

Scalar = int | float | str
MAX_MAGNITUDE = 1e12
MAX_EXPRESSION_LENGTH = 256
MAX_EXPRESSION_NODES = 80
CONSTANTS = {"pi": math.pi, "tau": math.tau}
FUNCTIONS = {"abs": abs, "sqrt": math.sqrt, "min": min, "max": max}
BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CADException("invalid_number", "Expected a finite real number.")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise CADException("invalid_number", "Number is outside the supported range.") from exc
    if not math.isfinite(result) or abs(result) > MAX_MAGNITUDE:
        raise CADException(
            "invalid_number", f"Number must be finite and within ±{MAX_MAGNITUDE:g}."
        )
    return result


def _parse(value: str) -> ast.Expression:
    if not value.strip() or len(value) > MAX_EXPRESSION_LENGTH:
        raise CADException("invalid_expression", "Expression must contain 1–256 characters.")
    try:
        tree = ast.parse(value, mode="eval")
    except (SyntaxError, RecursionError) as exc:
        raise CADException("invalid_expression", "Invalid arithmetic expression.") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_EXPRESSION_NODES:
        raise CADException("invalid_expression", "Expression is too complex.")
    return tree


def evaluate(value: Scalar, names: Mapping[str, float]) -> float:
    """Evaluate only bounded numeric arithmetic and explicitly allowed functions."""
    if not isinstance(value, str):
        return _number(value)

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Constant):
            return _number(node.value)
        if isinstance(node, ast.Name):
            if node.id in names:
                return _number(names[node.id])
            if node.id in CONSTANTS:
                return CONSTANTS[node.id]
            raise CADException("unknown_parameter", f"Unknown parameter '{node.id}'.")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return _number(visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1))
        if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise CADException("invalid_expression", "Exponents must be within ±12.")
            return _number(BINARY[type(node.op)](left, right))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in FUNCTIONS
            and not node.keywords
            and 1 <= len(node.args) <= 8
        ):
            values = [visit(arg) for arg in node.args]
            if node.func.id in {"abs", "sqrt"} and len(values) != 1:
                raise CADException("invalid_expression", f"{node.func.id} expects one argument.")
            if node.func.id in {"min", "max"}:
                return _number(FUNCTIONS[node.func.id](values))
            return _number(FUNCTIONS[node.func.id](*values))
        raise CADException(
            "invalid_expression", "Only arithmetic, names, abs/sqrt/min/max are allowed."
        )

    try:
        return visit(_parse(value).body)
    except CADException:
        raise
    except (ArithmeticError, ValueError, TypeError, RecursionError) as exc:
        raise CADException("invalid_expression", f"Expression cannot be evaluated: {exc}") from exc


def dependencies(value: Scalar) -> set[str]:
    """Find parameter names without evaluating or accepting additional syntax."""
    if not isinstance(value, str):
        _number(value)
        return set()
    tree = _parse(value)
    function_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id not in CONSTANTS and node.id not in function_names
    }


def resolve_parameters(parameters: Mapping[str, Scalar]) -> dict[str, float]:
    """Resolve formulas in any declaration order; reject cycles explicitly."""
    resolved: dict[str, float] = {}
    visiting: list[str] = []

    def resolve(name: str) -> None:
        if name in resolved:
            return
        if name not in parameters:
            raise CADException("unknown_parameter", f"Unknown parameter '{name}'.")
        if name in visiting:
            cycle = " → ".join(visiting[visiting.index(name) :] + [name])
            raise CADException("parameter_cycle", f"Parameter cycle: {cycle}")
        visiting.append(name)
        for dependency in sorted(dependencies(parameters[name])):
            resolve(dependency)
        resolved[name] = evaluate(parameters[name], resolved)
        visiting.pop()

    for name in parameters:
        resolve(name)
    return resolved
