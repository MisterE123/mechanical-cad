import math

import pytest

from mechanical_cad.errors import CADException
from mechanical_cad.expressions import dependencies, evaluate, resolve_parameters


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (5, 5),
        ("2 + 3 * 4", 14),
        ("(2+3)*4", 20),
        ("-5 / 2", -2.5),
        ("sqrt(9) + abs(-2)", 5),
        ("min(4,2,3) + max(1,5)", 7),
        ("pi * 2", math.tau),
        ("2**3", 8),
        ("width / 2", 10),
        ("max(3)", 3),
    ],
)
def test_bounded_arithmetic(value, expected):
    assert evaluate(value, {"width": 20}) == pytest.approx(expected)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo bad')",
        "(1).__class__",
        "[x for x in [1]]",
        "[1][0]",
        "lambda: 1",
        "open('/etc/passwd')",
        "True",
        "1 < 2",
        "1 if 1 else 0",
        "2**100",
        "1/0",
        "sqrt(-1)",
        "sqrt(1,2)",
        "min()",
        "max(value=2)",
        "1e309",
        "1e13",
        "",
        " " * 300,
        "1+" * 70 + "1",
        "(-1)**0.5",
        "'hello'",
        "unknown+1",
    ],
)
def test_rejects_unsafe_or_invalid_expressions(expression):
    with pytest.raises(CADException):
        evaluate(expression, {})


@pytest.mark.parametrize("number", [True, False, float("nan"), float("inf"), 10**400, None, []])
def test_rejects_invalid_numeric_inputs(number):
    with pytest.raises(CADException):
        evaluate(number, {})


def test_named_parameters_resolve_in_dependency_order():
    assert resolve_parameters({"width": "half * 2", "half": "base + 1", "base": 4}) == {
        "base": 4,
        "half": 5,
        "width": 10,
    }


def test_parameter_cycle_is_explicit():
    with pytest.raises(CADException, match="a → b → a") as error:
        resolve_parameters({"a": "b + 1", "b": "a - 1"})
    assert error.value.code == "parameter_cycle"


def test_dependencies_exclude_functions_and_constants():
    assert dependencies("sqrt(width) + pi + min(depth, 3)") == {"width", "depth"}
