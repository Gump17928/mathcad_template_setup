"""Plain-arithmetic formulas: parse, inspect, evaluate and print.

Supports numbers, variables, `+ - * / ^`, unary minus and parentheses - the subset that can be turned into a live
Mathcad formula. Anything else (function calls, `if`, table look-ups) raises ValueError when parsed.
Units use the same grammar (`kN/m`, `m^2`), with the identifiers meaning unit names.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Num:
    text: str  # kept as written so the generated worksheet shows exactly what the user typed


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Parens:
    inner: Node


@dataclass(frozen=True)
class Neg:
    operand: Node


@dataclass(frozen=True)
class BinOp:
    op: str  # one of BINARY_OPERATORS
    left: Node
    right: Node


Node = Num | Var | Parens | Neg | BinOp

BINARY_OPERATORS = "+-*/^"

# number | identifier | any single other character
_TOKEN = re.compile(r"\s*(?:(\d+\.?\d*(?:[eE][+-]?\d+)?)|([A-Za-z_][A-Za-z_0-9]*)|(.))")


class _Parser:
    """Recursive descent, lowest precedence first: add > mul > power > atom. `^` is right-associative."""

    def __init__(self, source: str):
        self.source = source
        # each token is (number, identifier, other); exactly one of the three is non-empty
        self.tokens = [t for t in _TOKEN.findall(source) if t[0] or t[1] or t[2].strip()]
        self.pos = 0

    def parse(self) -> Node:
        tree = self._add()
        if self.pos != len(self.tokens):
            raise ValueError(f"trailing input in {self.source!r}")
        return tree

    def _peek_is(self, operators: str) -> bool:
        if self.pos >= len(self.tokens):
            return False
        number, identifier, other = self.tokens[self.pos]
        return not number and not identifier and other in operators

    def _next(self) -> tuple[str, str, str]:
        if self.pos >= len(self.tokens):
            raise ValueError(f"unexpected end of {self.source!r}")
        self.pos += 1
        return self.tokens[self.pos - 1]

    def _atom(self) -> Node:
        number, identifier, other = self._next()
        if number:
            return Num(number)
        if identifier:
            return Var(identifier)
        if other == "(":
            inner = self._add()
            if not self._peek_is(")"):
                raise ValueError(f"missing ) in {self.source!r}")
            self._next()
            return Parens(inner)
        if other == "-":
            return Neg(self._power())
        raise ValueError(f"unexpected {other!r} in {self.source!r}")

    def _power(self) -> Node:
        base = self._atom()
        if self._peek_is("^"):
            self._next()
            return BinOp("^", base, self._power())
        return base

    def _mul(self) -> Node:
        left = self._power()
        while self._peek_is("*/"):
            left = BinOp(self._next()[2], left, self._power())
        return left

    def _add(self) -> Node:
        left = self._mul()
        while self._peek_is("+-"):
            left = BinOp(self._next()[2], left, self._mul())
        return left


def parse(source: str) -> Node:
    """Parse `source` into a formula tree. Raises ValueError (with the offending text) if it is not plain arithmetic."""
    return _Parser(source).parse()


def variables(node: Node) -> set[str]:
    """Names of all variables used in the formula."""
    if isinstance(node, Var):
        return {node.name}
    if isinstance(node, Parens):
        return variables(node.inner)
    if isinstance(node, Neg):
        return variables(node.operand)
    if isinstance(node, BinOp):
        return variables(node.left) | variables(node.right)
    return set()


def rename_variables(node: Node, mapping: dict[str, str]) -> Node:
    """Copy of the formula with every variable replaced by mapping[name]."""
    if isinstance(node, Var):
        return Var(mapping[node.name])
    if isinstance(node, Parens):
        return Parens(rename_variables(node.inner, mapping))
    if isinstance(node, Neg):
        return Neg(rename_variables(node.operand, mapping))
    if isinstance(node, BinOp):
        return BinOp(node.op, rename_variables(node.left, mapping), rename_variables(node.right, mapping))
    return node


def evaluate(node: Node, values: dict[str, float]) -> float:
    """Numeric value of the formula. Raises KeyError (unknown variable), ZeroDivisionError, OverflowError or
    ValueError (result is not a real number)."""
    if isinstance(node, Num):
        return float(node.text)
    if isinstance(node, Var):
        return values[node.name]
    if isinstance(node, Parens):
        return evaluate(node.inner, values)
    if isinstance(node, Neg):
        return -evaluate(node.operand, values)
    left, right = evaluate(node.left, values), evaluate(node.right, values)
    result = {
        "+": lambda: left + right,
        "-": lambda: left - right,
        "*": lambda: left * right,
        "/": lambda: left / right,
        "^": lambda: left**right,
    }[node.op]()
    if isinstance(result, complex):
        raise ValueError("result is not a real number")
    return result


def to_text(node: Node) -> str:
    """The formula as text, normalised (no spaces)."""
    if isinstance(node, Num):
        return node.text
    if isinstance(node, Var):
        return node.name
    if isinstance(node, Parens):
        return f"({to_text(node.inner)})"
    if isinstance(node, Neg):
        return f"-{to_text(node.operand)}"
    return f"{to_text(node.left)}{node.op}{to_text(node.right)}"
