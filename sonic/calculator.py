from __future__ import annotations

import ast
import operator
import re
from typing import Any

_PERCENT = re.compile(
    r"(?i)^\s*(?:what(?:'s| is)\s+)?(\d+(?:\.\d+)?)\s*%\s*(?:of\s+)?(\d+(?:\.\d+)?)\s*\??\s*$"
)
_SIMPLE_MATH = re.compile(
    r"(?i)^\s*(?:what(?:'s| is)\s+)?(-?\d+(?:\.\d+)?)\s*([+\-*/x×])\s*(-?\d+(?:\.\d+)?)\s*\??\s*$"
)

_OPS = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "x": operator.mul,
    "×": operator.mul,
    "/": operator.truediv,
}


def try_calculator(utterance: str) -> dict[str, Any] | None:
    """Intercept arithmetic before Laya. Returns a result dict or None."""
    text = utterance.strip()
    m = _PERCENT.match(text)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        value = (a / 100.0) * b
        return {
            "matched": True,
            "expression": f"{a}% of {b}",
            "value": value,
            "text": _format_number(value),
        }
    m = _SIMPLE_MATH.match(text)
    if m:
        a, op, b = float(m.group(1)), m.group(2), float(m.group(3))
        value = _OPS[op](a, b)
        return {
            "matched": True,
            "expression": f"{a} {op} {b}",
            "value": value,
            "text": _format_number(value),
        }
    # Safe fallback: pure numeric expression with + - * /
    if re.fullmatch(r"[\d\.\+\-\*/\(\)\s]+", text) and any(c in text for c in "+-*/"):
        try:
            value = _safe_eval(text)
            return {
                "matched": True,
                "expression": text,
                "value": value,
                "text": _format_number(value),
            }
        except Exception:
            return None
    return None


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4g}"


def _safe_eval(expr: str) -> float:
    node = ast.parse(expr, mode="eval")

    def _eval(n: ast.AST) -> float:
        if isinstance(n, ast.Expression):
            return _eval(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            v = _eval(n.operand)
            return v if isinstance(n.op, ast.UAdd) else -v
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = _eval(n.left), _eval(n.right)
            if isinstance(n.op, ast.Add):
                return left + right
            if isinstance(n.op, ast.Sub):
                return left - right
            if isinstance(n.op, ast.Mult):
                return left * right
            if right == 0:
                raise ZeroDivisionError("division by zero")
            return left / right
        raise ValueError("unsupported expression")

    return _eval(node)
