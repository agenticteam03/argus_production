"""Safe precondition expression interpreter for action cards (ACR-0019 §3.4).

Evaluates candidate action preconditions against observation state without invoking
dynamic execution primitives (eval, exec, compile).
"""
from __future__ import annotations

import ast
from typing import Any


class PreconditionSyntaxError(ValueError):
    """Raised when an expression contains invalid syntax or disallowed AST nodes."""


class _MissingSentinel:
    """Represents a missing key or attribute in the observation context."""
    def __repr__(self) -> str:
        return "<MISSING>"


_MISSING = _MissingSentinel()


class _SafeEvaluator:
    """Recursive AST evaluator restricted to safe boolean logic and comparisons."""

    ALLOWED_NODES = (
        ast.Expression,
        ast.Compare,
        ast.BoolOp,
        ast.UnaryOp,
        ast.Constant,
        ast.List,
        ast.Tuple,
        ast.Name,
        ast.Attribute,
        ast.Load,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.In,
        ast.NotIn,
        ast.And,
        ast.Or,
        ast.Not,
    )

    def __init__(self, context: dict[str, Any]) -> None:
        self.context = context

    def evaluate(self, node: ast.AST) -> Any:
        if not isinstance(node, self.ALLOWED_NODES):
            raise PreconditionSyntaxError(f"Disallowed AST node: {type(node).__name__}")

        method = getattr(self, f"_eval_{type(node).__name__}", None)
        if method is None:
            raise PreconditionSyntaxError(f"Unhandled safe AST node: {type(node).__name__}")
        return method(node)

    def _eval_Expression(self, node: ast.Expression) -> Any:
        return self.evaluate(node.body)

    def _eval_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def _eval_Name(self, node: ast.Name) -> Any:
        name = node.id
        if name.startswith("_"):
            raise PreconditionSyntaxError(f"Access to private identifier '{name}' is forbidden")
        return self.context.get(name, _MISSING)

    def _eval_Attribute(self, node: ast.Attribute) -> Any:
        attr = node.attr
        if attr.startswith("_"):
            raise PreconditionSyntaxError(f"Access to private attribute '{attr}' is forbidden")
        base = self.evaluate(node.value)
        if isinstance(base, _MissingSentinel):
            return _MISSING
        if isinstance(base, dict):
            return base.get(attr, _MISSING)
        return getattr(base, attr, _MISSING)

    def _eval_List(self, node: ast.List) -> list[Any]:
        return [self.evaluate(elem) for elem in node.elts]

    def _eval_Tuple(self, node: ast.Tuple) -> tuple[Any, ...]:
        return tuple(self.evaluate(elem) for elem in node.elts)

    def _eval_UnaryOp(self, node: ast.UnaryOp) -> Any:
        val = self.evaluate(node.operand)
        if isinstance(node.op, ast.Not):
            if isinstance(val, _MissingSentinel):
                return True
            return not bool(val)
        raise PreconditionSyntaxError(f"Disallowed unary operator: {type(node.op).__name__}")

    def _eval_BoolOp(self, node: ast.BoolOp) -> bool:
        if isinstance(node.op, ast.And):
            for val_node in node.values:
                val = self.evaluate(val_node)
                if isinstance(val, _MissingSentinel) or not val:
                    return False
            return True
        if isinstance(node.op, ast.Or):
            for val_node in node.values:
                val = self.evaluate(val_node)
                if not isinstance(val, _MissingSentinel) and bool(val):
                    return True
            return False
        raise PreconditionSyntaxError(f"Disallowed boolean operator: {type(node.op).__name__}")

    def _eval_Compare(self, node: ast.Compare) -> bool:
        left = self.evaluate(node.left)
        current = left

        for op, comp_node in zip(node.ops, node.comparators):
            right = self.evaluate(comp_node)
            if not self._apply_comparison(current, op, right):
                return False
            current = right
        return True

    def _apply_comparison(self, left: Any, op: ast.cmpop, right: Any) -> bool:
        # If either operand is missing, any equality or relational comparison is False
        if isinstance(left, _MissingSentinel) or isinstance(right, _MissingSentinel):
            return False

        try:
            if isinstance(op, ast.Eq):
                return bool(left == right)
            if isinstance(op, ast.NotEq):
                return bool(left != right)
            if isinstance(op, ast.Lt):
                return bool(left < right)
            if isinstance(op, ast.LtE):
                return bool(left <= right)
            if isinstance(op, ast.Gt):
                return bool(left > right)
            if isinstance(op, ast.GtE):
                return bool(left >= right)
            if isinstance(op, ast.In):
                return bool(left in right)
            if isinstance(op, ast.NotIn):
                return bool(left not in right)
        except TypeError:
            return False

        raise PreconditionSyntaxError(f"Unsupported comparison operator: {type(op).__name__}")


def evaluate_precondition(expr: str, context: dict[str, Any]) -> bool:
    """Safely evaluates a single precondition string against observation context.

    Returns True if the expression is satisfied, False if not or if required fields
    are missing. Raises PreconditionSyntaxError on syntax errors or disallowed AST nodes.
    """
    expr_clean = expr.strip()
    if not expr_clean:
        return True

    try:
        parsed = ast.parse(expr_clean, mode="eval")
    except SyntaxError as e:
        raise PreconditionSyntaxError(f"Invalid expression syntax: {e}") from e

    evaluator = _SafeEvaluator(context)
    result = evaluator.evaluate(parsed)
    if isinstance(result, _MissingSentinel):
        return False
    return bool(result)
