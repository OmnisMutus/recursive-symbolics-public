"""Reference Implementation 1: Recursive Symbolic Algebra Simplifier (pure Python stdlib).

Plugs an immutable arithmetic AST into ``symbolics.interfaces.SymbolicBackend`` and
``symbolics.interfaces.RuleEngine`` to demonstrate:
- Deterministic leftmost-innermost rule rewriting
- Strict structural complexity descent Phi(S_{t+1}) < Phi(S_t)
- Depth tracking & bounded convergence (max_depth / CycleDetectedError)
- Independent ground truth via direct numeric evaluation across arbitrary variable assignments
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

from symbolics.interfaces import RuleEngine


@dataclass(frozen=True)
class Const:
    value: int


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Neg:
    operand: Any


@dataclass(frozen=True)
class BinOp:
    op: str  # '+', '-', '*'
    left: Any
    right: Any


_TOKEN_RE = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*|\d+|[+\-*()])\s*")


class _AlgebraParser:
    def __init__(self, text: str) -> None:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Expression text must be a non-empty string.")
        self.tokens: list[str] = []
        pos = 0
        while pos < len(text):
            if text[pos].isspace():
                pos += 1
                continue
            m = _TOKEN_RE.match(text, pos)
            if not m:
                raise ValueError(f"Unexpected character {text[pos]!r} at index {pos} in {text!r}")
            self.tokens.append(m.group(1))
            pos = m.end()
        self.idx = 0

    def peek(self) -> str | None:
        return self.tokens[self.idx] if self.idx < len(self.tokens) else None

    def take(self) -> str:
        tok = self.tokens[self.idx]
        self.idx += 1
        return tok

    def parse(self) -> Any:
        node = self.parse_expr()
        if self.peek() is not None:
            raise ValueError(f"Unexpected trailing token {self.peek()!r}")
        return node

    def parse_expr(self) -> Any:
        node = self.parse_term()
        while self.peek() in ("+", "-"):
            op = self.take()
            node = BinOp(op, node, self.parse_term())
        return node

    def parse_term(self) -> Any:
        node = self.parse_unary()
        while self.peek() == "*":
            self.take()
            node = BinOp("*", node, self.parse_unary())
        return node

    def parse_unary(self) -> Any:
        if self.peek() == "-":
            self.take()
            return Neg(self.parse_unary())
        if self.peek() == "+":
            self.take()
            return self.parse_unary()
        return self.parse_atom()

    def parse_atom(self) -> Any:
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected end of expression.")
        if tok == "(":
            self.take()
            inner = self.parse_expr()
            if self.peek() != ")":
                raise ValueError("Expected closing ')' in expression.")
            self.take()
            return inner
        self.take()
        if tok.isdigit():
            return Const(int(tok))
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tok):
            return Var(tok)
        raise ValueError(f"Unexpected token {tok!r}")


class AlgebraBackend:
    """Implements ``SymbolicBackend`` for integer-coefficient polynomial expressions."""

    def parse(self, text: str) -> Any:
        return _AlgebraParser(text).parse()

    def format(self, node: Any) -> str:
        if isinstance(node, Const):
            return str(node.value)
        if isinstance(node, Var):
            return node.name
        if isinstance(node, Neg):
            inner = self.format(node.operand)
            if isinstance(node.operand, BinOp):
                return f"-({inner})"
            return f"-{inner}"
        if isinstance(node, BinOp):
            left = self._wrap_child(node.op, node.left, is_right=False)
            right = self._wrap_child(node.op, node.right, is_right=True)
            return f"{left} {node.op} {right}"
        raise TypeError(f"Unsupported AST node: {type(node).__name__}")

    def _wrap_child(self, parent_op: str, child: Any, *, is_right: bool) -> str:
        rendered = self.format(child)
        if not isinstance(child, BinOp):
            return rendered
        if parent_op == "*" and child.op in ("+", "-"):
            return f"({rendered})"
        if parent_op == "-" and is_right and child.op in ("+", "-"):
            return f"({rendered})"
        return rendered

    def complexity(self, node: Any) -> int:
        if isinstance(node, (Const, Var)):
            return 1
        if isinstance(node, Neg):
            return 1 + self.complexity(node.operand)
        if isinstance(node, BinOp):
            return 1 + self.complexity(node.left) + self.complexity(node.right)
        raise TypeError(f"Unsupported AST node: {type(node).__name__}")

    def evaluate(self, node: Any, env: Mapping[str, int | float]) -> int | float:
        if isinstance(node, Const):
            return node.value
        if isinstance(node, Var):
            if node.name not in env:
                raise KeyError(f"Missing variable {node.name!r} in evaluation environment.")
            return env[node.name]
        if isinstance(node, Neg):
            return -self.evaluate(node.operand, env)
        if isinstance(node, BinOp):
            lv = self.evaluate(node.left, env)
            rv = self.evaluate(node.right, env)
            if node.op == "+":
                return lv + rv
            if node.op == "-":
                return lv - rv
            if node.op == "*":
                return lv * rv
        raise TypeError(f"Unsupported AST node: {type(node).__name__}")


class AlgebraSimplifier(RuleEngine):
    """Terminating algebraic normal-form reducer plugging into ``RuleEngine``."""

    def __init__(self, backend: AlgebraBackend | None = None, enforce_constitutional: bool = True) -> None:
        super().__init__(backend or AlgebraBackend(), enforce_constitutional=enforce_constitutional)

    def rewrite_once(self, node: Any) -> tuple[Any, str | None]:
        if isinstance(node, (Const, Var)):
            return node, None

        if isinstance(node, Neg):
            inner, rule = self.rewrite_once(node.operand)
            if rule is not None:
                return Neg(inner), rule
            if isinstance(inner, Neg):
                return inner.operand, "double_negation"
            if isinstance(inner, Const):
                return Const(-inner.value), "negate_constant"
            return node, None

        if isinstance(node, BinOp):
            new_left, l_rule = self.rewrite_once(node.left)
            if l_rule is not None:
                return BinOp(node.op, new_left, node.right), l_rule

            new_right, r_rule = self.rewrite_once(node.right)
            if r_rule is not None:
                return BinOp(node.op, node.left, new_right), r_rule

            return self._rewrite_binop_local(node)

        raise TypeError(f"Unsupported AST node: {type(node).__name__}")

    def _rewrite_binop_local(self, node: BinOp) -> tuple[Any, str | None]:
        op, left, right = node.op, node.left, node.right

        # Constant folding
        if isinstance(left, Const) and isinstance(right, Const):
            if op == "+":
                return Const(left.value + right.value), "constant_fold_add"
            if op == "-":
                return Const(left.value - right.value), "constant_fold_sub"
            if op == "*":
                return Const(left.value * right.value), "constant_fold_mul"

        if op == "+":
            if isinstance(left, Const) and left.value == 0:
                return right, "additive_identity_left"
            if isinstance(right, Const) and right.value == 0:
                return left, "additive_identity_right"
            if left == right:
                return BinOp("*", Const(2), left), "collect_like_terms"
            if isinstance(left, Neg) and left.operand == right:
                return Const(0), "additive_inverse_cancel"
            if isinstance(right, Neg) and right.operand == left:
                return Const(0), "additive_inverse_cancel"
            # Canonical constant-on-right normalization if nested? Keep monotone descending only!

        if op == "-":
            if isinstance(right, Const) and right.value == 0:
                return left, "subtractive_identity_right"
            if isinstance(left, Const) and left.value == 0:
                return Neg(right), "subtractive_zero_left"
            if left == right:
                return Const(0), "self_subtraction_zero"
            if isinstance(right, Neg):
                return BinOp("+", left, right.operand), "subtract_negation"

        if op == "*":
            if (isinstance(left, Const) and left.value == 0) or (
                isinstance(right, Const) and right.value == 0
            ):
                return Const(0), "multiplicative_annihilation"
            if isinstance(left, Const) and left.value == 1:
                return right, "multiplicative_identity_left"
            if isinstance(right, Const) and right.value == 1:
                return left, "multiplicative_identity_right"

        return node, None
