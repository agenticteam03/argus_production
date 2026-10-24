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


def _validate_observation(value: Any, *, depth: int = 0, seen: set[int] | None = None,
                         budget: list[int] | None = None) -> None:
    """Reject custom objects so comparisons cannot dispatch user-defined Python methods."""
    if value is None or type(value) in (bool, int, float, str):
        return
    if depth >= 64:
        raise PreconditionSyntaxError("Observation values are nested too deeply")
    if type(value) not in (dict, list, tuple):
        raise PreconditionSyntaxError("Observation values must use built-in JSON types")
    if seen is None:
        seen = set()
    if budget is None:
        budget = [10_000]
    ident = id(value)
    if ident in seen:
        raise PreconditionSyntaxError("Observation values must not contain cycles")
    seen.add(ident)
    try:
        items = value.items() if type(value) is dict else enumerate(value)
        for key, child in items:
            budget[0] -= 1
            if budget[0] < 0:
                raise PreconditionSyntaxError("Observation values contain too many entries")
            if type(value) is dict and type(key) is not str:
                raise PreconditionSyntaxError("Observation mappings must have string keys")
            _validate_observation(child, depth=depth + 1, seen=seen, budget=budget)
    finally:
        seen.remove(ident)


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
        if type(context) is not dict:
            raise PreconditionSyntaxError("Observation context must be a dictionary")
        _validate_observation(context)
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
        raise PreconditionSyntaxError("Observation paths must contain dictionaries only")

    def _eval_List(self, node: ast.List) -> list[Any]:
        return [self.evaluate(elem) for elem in node.elts]

    def _eval_Tuple(self, node: ast.Tuple) -> tuple[Any, ...]:
        return tuple(self.evaluate(elem) for elem in node.elts)

    def _eval_UnaryOp(self, node: ast.UnaryOp) -> Any:
        val = self.evaluate(node.operand)
        if isinstance(node.op, ast.Not):
            if isinstance(val, _MissingSentinel):
                return _MISSING
            return not bool(val)
        raise PreconditionSyntaxError(f"Disallowed unary operator: {type(node.op).__name__}")

    def _eval_BoolOp(self, node: ast.BoolOp) -> Any:
        if isinstance(node.op, ast.And):
            missing = False
            for val_node in node.values:
                val = self.evaluate(val_node)
                if isinstance(val, _MissingSentinel):
                    missing = True
                elif not val:
                    return False
            return _MISSING if missing else True
        if isinstance(node.op, ast.Or):
            missing = False
            for val_node in node.values:
                val = self.evaluate(val_node)
                if isinstance(val, _MissingSentinel):
                    missing = True
                elif bool(val):
                    return True
            return _MISSING if missing else False
        raise PreconditionSyntaxError(f"Disallowed boolean operator: {type(node.op).__name__}")

    def _eval_Compare(self, node: ast.Compare) -> Any:
        left = self.evaluate(node.left)
        current = left

        for op, comp_node in zip(node.ops, node.comparators):
            right = self.evaluate(comp_node)
            compared = self._apply_comparison(current, op, right)
            if isinstance(compared, _MissingSentinel):
                return _MISSING
            if not compared:
                return False
            current = right
        return True

    def _apply_comparison(self, left: Any, op: ast.cmpop, right: Any) -> Any:
        # Preserve unknown through negation so missing evidence cannot satisfy a guard.
        if isinstance(left, _MissingSentinel) or isinstance(right, _MissingSentinel):
            return _MISSING

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
