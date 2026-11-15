"""Reference Implementation 2: Propositional Logic Reducer (pure Python stdlib).

Plugs boolean formulas into ``symbolics.interfaces.SymbolicBackend`` and
``symbolics.interfaces.RuleEngine``, using exhaustive truth tables as an
independent ground-truth semantic verifier across every reduction step.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import itertools
import re
from typing import Any

from symbolics.interfaces import RuleEngine


@dataclass(frozen=True)
class BoolConst:
    value: bool


@dataclass(frozen=True)
class Atom:
    name: str


@dataclass(frozen=True)
class Not:
    operand: Any


@dataclass(frozen=True)
class And:
    left: Any
    right: Any


@dataclass(frozen=True)
class Or:
    left: Any
    right: Any


@dataclass(frozen=True)
class Implies:
    left: Any
    right: Any


_TOKEN_RE = re.compile(r"\s*(->|<->|[~!&|()]|[A-Za-z_][A-Za-z0-9_]*)\s*")


class _LogicParser:
    def __init__(self, text: str) -> None:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Formula text must be a non-empty string.")
        self.tokens: list[str] = []
        pos = 0
        while pos < len(text):
            if text[pos].isspace():
                pos += 1
                continue
            m = _TOKEN_RE.match(text, pos)
            if not m:
                raise ValueError(f"Unexpected token starting at {text[pos:]!r}")
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
        node = self.parse_implies()
        if self.peek() is not None:
            raise ValueError(f"Unexpected trailing token {self.peek()!r}")
        return node

    def parse_implies(self) -> Any:
        left = self.parse_or()
        if self.peek() == "->":
            self.take()
            return Implies(left, self.parse_implies())
        return left

    def parse_or(self) -> Any:
        node = self.parse_and()
        while self.peek() == "|":
            self.take()
            node = Or(node, self.parse_and())
        return node

    def parse_and(self) -> Any:
        node = self.parse_not()
        while self.peek() == "&":
            self.take()
            node = And(node, self.parse_not())
        return node

    def parse_not(self) -> Any:
        if self.peek() in ("~", "!"):
            self.take()
            return Not(self.parse_not())
        return self.parse_atom()

    def parse_atom(self) -> Any:
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected end of formula.")
        if tok == "(":
            self.take()
            inner = self.parse_implies()
            if self.peek() != ")":
                raise ValueError("Expected closing ')' in formula.")
            self.take()
            return inner
        self.take()
        if tok in ("True", "T", "1"):
            return BoolConst(True)
        if tok in ("False", "F", "0"):
            return BoolConst(False)
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tok):
            return Atom(tok)
        raise ValueError(f"Unexpected token {tok!r}")


class LogicBackend:
    """Implements ``SymbolicBackend`` for propositional boolean logic formulas."""

    def parse(self, text: str) -> Any:
        return _LogicParser(text).parse()

    def format(self, node: Any) -> str:
        if isinstance(node, BoolConst):
            return "True" if node.value else "False"
        if isinstance(node, Atom):
            return node.name
        if isinstance(node, Not):
            inner = self.format(node.operand)
            if isinstance(node.operand, (And, Or, Implies)):
                return f"~({inner})"
            return f"~{inner}"
        if isinstance(node, And):
            l = f"({self.format(node.left)})" if isinstance(node.left, (Or, Implies)) else self.format(node.left)
            r = f"({self.format(node.right)})" if isinstance(node.right, (Or, Implies)) else self.format(node.right)
            return f"{l} & {r}"
        if isinstance(node, Or):
            l = f"({self.format(node.left)})" if isinstance(node.left, Implies) else self.format(node.left)
            r = f"({self.format(node.right)})" if isinstance(node.right, Implies) else self.format(node.right)
            return f"{l} | {r}"
        if isinstance(node, Implies):
            l = f"({self.format(node.left)})" if isinstance(node.left, Implies) else self.format(node.left)
            return f"{l} -> {self.format(node.right)}"
        raise TypeError(f"Unsupported logic node: {type(node).__name__}")

    def complexity(self, node: Any) -> int:
        if isinstance(node, (BoolConst, Atom)):
            return 1
        if isinstance(node, Not):
            return 1 + self.complexity(node.operand)
        if isinstance(node, (And, Or, Implies)):
            return 1 + self.complexity(node.left) + self.complexity(node.right)
        raise TypeError(f"Unsupported logic node: {type(node).__name__}")

    def evaluate(self, node: Any, env: Mapping[str, bool]) -> bool:
        if isinstance(node, BoolConst):
            return bool(node.value)
        if isinstance(node, Atom):
            if node.name not in env:
                raise KeyError(f"Missing proposition variable {node.name!r}")
            return bool(env[node.name])
        if isinstance(node, Not):
            return not self.evaluate(node.operand, env)
        if isinstance(node, And):
            return self.evaluate(node.left, env) and self.evaluate(node.right, env)
        if isinstance(node, Or):
            return self.evaluate(node.left, env) or self.evaluate(node.right, env)
        if isinstance(node, Implies):
            return (not self.evaluate(node.left, env)) or self.evaluate(node.right, env)
        raise TypeError(f"Unsupported logic node: {type(node).__name__}")

    def variables(self, node: Any) -> tuple[str, ...]:
        found: set[str] = set()

        def walk(n: Any) -> None:
            if isinstance(n, Atom):
                found.add(n.name)
            elif isinstance(n, Not):
                walk(n.operand)
            elif isinstance(n, (And, Or, Implies)):
                walk(n.left)
                walk(n.right)

        walk(node)
        return tuple(sorted(found))

    def truth_table(self, node: Any, var_names: tuple[str, ...] | None = None) -> list[bool]:
        names = var_names if var_names is not None else self.variables(node)
        return [
            self.evaluate(node, dict(zip(names, assignment)))
            for assignment in itertools.product((False, True), repeat=len(names))
        ]


class PropositionalReducer(RuleEngine):
    """Terminating propositional-logic normal-form reducer."""

    def __init__(self, backend: LogicBackend | None = None, enforce_constitutional: bool = True) -> None:
        super().__init__(backend or LogicBackend(), enforce_constitutional=enforce_constitutional)

    def rewrite_once(self, node: Any) -> tuple[Any, str | None]:
        if isinstance(node, (BoolConst, Atom)):
            return node, None

        if isinstance(node, Not):
            inner, rule = self.rewrite_once(node.operand)
            if rule is not None:
                return Not(inner), rule
            if isinstance(inner, BoolConst):
                return BoolConst(not inner.value), "not_const"
            if isinstance(inner, Not):
                return inner.operand, "double_negation_elim"
            if isinstance(inner, And):
                return Or(Not(inner.left), Not(inner.right)), "de_morgan_and"
            if isinstance(inner, Or):
                return And(Not(inner.left), Not(inner.right)), "de_morgan_or"
            return node, None

        if isinstance(node, Implies):
            new_l, l_rule = self.rewrite_once(node.left)
            if l_rule is not None:
                return Implies(new_l, node.right), l_rule
            new_r, r_rule = self.rewrite_once(node.right)
            if r_rule is not None:
                return Implies(node.left, new_r), r_rule
            if isinstance(node.left, BoolConst) and node.left.value is False:
                return BoolConst(True), "vacuous_implication"
            if isinstance(node.left, BoolConst) and node.left.value is True:
                return node.right, "modus_ponens_const"
            if isinstance(node.right, BoolConst) and node.right.value is True:
                return BoolConst(True), "tautological_consequent"
            if node.left == node.right:
                return BoolConst(True), "self_implication_tautology"
            return Or(Not(node.left), node.right), "implies_elim"

        if isinstance(node, And):
            new_l, l_rule = self.rewrite_once(node.left)
            if l_rule is not None:
                return And(new_l, node.right), l_rule
            new_r, r_rule = self.rewrite_once(node.right)
            if r_rule is not None:
                return And(node.left, new_r), r_rule
            l, r = node.left, node.right
            if (isinstance(l, BoolConst) and not l.value) or (isinstance(r, BoolConst) and not r.value):
                return BoolConst(False), "and_annihilation"
            if isinstance(l, BoolConst) and l.value:
                return r, "and_identity_left"
            if isinstance(r, BoolConst) and r.value:
                return l, "and_identity_right"
            if l == r:
                return l, "and_idempotence"
            if l == Not(r) or r == Not(l):
                return BoolConst(False), "non_contradiction"
            return node, None

        if isinstance(node, Or):
            new_l, l_rule = self.rewrite_once(node.left)
            if l_rule is not None:
                return Or(new_l, node.right), l_rule
            new_r, r_rule = self.rewrite_once(node.right)
            if r_rule is not None:
                return Or(node.left, new_r), r_rule
            l, r = node.left, node.right
            if (isinstance(l, BoolConst) and l.value) or (isinstance(r, BoolConst) and r.value):
                return BoolConst(True), "or_annihilation"
            if isinstance(l, BoolConst) and not l.value:
                return r, "or_identity_left"
            if isinstance(r, BoolConst) and not r.value:
                return l, "or_identity_right"
            if l == r:
                return l, "or_idempotence"
            if l == Not(r) or r == Not(l):
                return BoolConst(True), "excluded_middle"
            return node, None

        raise TypeError(f"Unsupported logic node: {type(node).__name__}")
