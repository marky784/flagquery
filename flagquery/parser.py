"""Parser for the flagquery flags file format.

The format is deliberately line oriented: each directive lives on its own
line, which makes it possible to point at an exact line and column for
every error without needing a real grammar. The one place that isn't
trivially line-shaped is a "rule" line's expression, so that gets its own
small tokenizer below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union


class FlagFileError(Exception):
    """A problem with a flags file, reported with a line and column."""

    def __init__(self, message: str, source_name: str, line: int, column: int, raw_line: str):
        self.message = message
        self.source_name = source_name
        self.line = line
        self.column = column
        self.raw_line = raw_line
        super().__init__(self._format())

    def _format(self) -> str:
        pointer = " " * max(self.column - 1, 0) + "^"
        location = f"{self.source_name}:{self.line}:{self.column}"
        return f"{location}: error: {self.message}\n    {self.raw_line}\n    {pointer}"

    def __str__(self) -> str:
        return self._format()


@dataclass
class Comparison:
    key: str
    op: str
    value: str

    def evaluate(self, context: dict) -> bool:
        actual = context.get(self.key)
        if actual is None:
            return False
        if self.op == "==":
            return actual == self.value
        return actual != self.value


@dataclass
class BoolExpr:
    op: str  # "and" or "or"
    operands: "List[Condition]"

    def evaluate(self, context: dict) -> bool:
        if self.op == "and":
            return all(operand.evaluate(context) for operand in self.operands)
        return any(operand.evaluate(context) for operand in self.operands)


Condition = Union[Comparison, BoolExpr]


@dataclass
class Rule:
    condition: Condition
    result: bool
    line: int
    text: str


@dataclass
class Flag:
    name: str
    line: int
    default: Optional[bool] = None
    rules: List[Rule] = field(default_factory=list)


# A rule expression looks like:
#   user.plan == "enterprise" and (env == staging or env == canary) -> on
# 'and' and 'or' are ordinary WORD tokens; the parser treats those two
# spellings as keywords wherever a field name or value is not expected.
_TOKEN_RE = re.compile(
    r"""
      (?P<WS>\s+)
    | (?P<ARROW>->)
    | (?P<EQ>==)
    | (?P<NE>!=)
    | (?P<SINGLE_EQ>=)
    | (?P<LPAREN>\()
    | (?P<RPAREN>\))
    | (?P<STRING>"[^"]*")
    | (?P<WORD>[A-Za-z_][A-Za-z0-9_.-]*)
    | (?P<INVALID>.)
    """,
    re.VERBOSE,
)

_KEYWORDS = ("and", "or")


def _tokenize_rule(expr: str, line_no: int, base_col: int, raw_line: str, source_name: str):
    tokens = []
    for match in _TOKEN_RE.finditer(expr):
        kind = match.lastgroup
        text = match.group()
        col = base_col + match.start()
        if kind == "WS":
            continue
        if kind == "SINGLE_EQ":
            raise FlagFileError(
                "'=' is not a valid comparison here, use '==' or '!='",
                source_name, line_no, col, raw_line,
            )
        if kind == "INVALID":
            raise FlagFileError(
                f"unexpected character {text!r} in rule",
                source_name, line_no, col, raw_line,
            )
        tokens.append((kind, text, col))
    return tokens


def _parse_rule_expr(expr: str, line_no: int, base_col: int, raw_line: str, source_name: str) -> Rule:
    tokens = _tokenize_rule(expr, line_no, base_col, raw_line, source_name)

    def fail(message: str, col: int):
        raise FlagFileError(message, source_name, line_no, col, raw_line)

    if not tokens:
        fail("expected a rule of the form 'field == value -> on', found nothing", base_col)

    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def col_after_last():
        # Column just past the previous token, used when a token is missing.
        prev_col, prev_text = tokens[pos - 1][2], tokens[pos - 1][1]
        return prev_col + len(prev_text)

    def parse_comparison() -> Comparison:
        nonlocal pos
        tok = peek()
        if tok is None:
            fail("expected a condition", col_after_last())
        kind, text, col = tok
        if kind != "WORD" or text in _KEYWORDS:
            fail(f"expected a field name (like env or user.plan), found {text!r}", col)
        key = text
        pos += 1

        tok = peek()
        if tok is None:
            fail("expected '==' or '!=' after the field name", col_after_last())
        kind, text, col = tok
        if kind not in ("EQ", "NE"):
            fail(f"expected '==' or '!=' after the field name, found {text!r}", col)
        op = text
        pos += 1

        tok = peek()
        if tok is None:
            fail("expected a value after the comparison", col_after_last())
        kind, text, col = tok
        if kind not in ("WORD", "STRING") or (kind == "WORD" and text in _KEYWORDS):
            fail(f"expected a value after the comparison, found {text!r}", col)
        value = text[1:-1] if kind == "STRING" else text
        pos += 1

        return Comparison(key=key, op=op, value=value)

    def parse_atom() -> Condition:
        nonlocal pos
        tok = peek()
        if tok is None:
            fail("expected a condition", col_after_last())
        kind, text, col = tok
        if kind == "LPAREN":
            pos += 1
            inner = parse_or()
            tok = peek()
            if tok is None or tok[0] != "RPAREN":
                fail("expected ')' to close '('", col)
            pos += 1
            return inner
        return parse_comparison()

    def parse_and() -> Condition:
        nonlocal pos
        operands = [parse_atom()]
        while True:
            tok = peek()
            if tok and tok[0] == "WORD" and tok[1] == "and":
                pos += 1
                operands.append(parse_atom())
            else:
                break
        return operands[0] if len(operands) == 1 else BoolExpr(op="and", operands=operands)

    def parse_or() -> Condition:
        nonlocal pos
        operands = [parse_and()]
        while True:
            tok = peek()
            if tok and tok[0] == "WORD" and tok[1] == "or":
                pos += 1
                operands.append(parse_and())
            else:
                break
        return operands[0] if len(operands) == 1 else BoolExpr(op="or", operands=operands)

    condition = parse_or()

    tok = peek()
    if tok is None:
        fail("expected '->' after the condition", col_after_last())
    kind, text, col = tok
    if kind != "ARROW":
        fail(f"expected '->' after the condition, found {text!r}", col)
    pos += 1

    tok = peek()
    if tok is None:
        fail("expected 'on' or 'off' after '->'", col_after_last())
    kind, text, col = tok
    if text not in ("on", "off"):
        fail(f"expected 'on' or 'off' after '->', found {text!r}", col)
    result = text == "on"
    pos += 1

    tok = peek()
    if tok is not None:
        _, extra_text, extra_col = tok
        fail(f"unexpected text after rule: {extra_text!r}", extra_col)

    return Rule(condition=condition, result=result, line=line_no, text=raw_line.strip())


def parse(text: str, source_name: str = "<string>") -> Dict[str, Flag]:
    flags: Dict[str, Flag] = {}
    current: Optional[Flag] = None
    lines = text.splitlines()

    for line_no, raw_line in enumerate(lines, start=1):
        stripped = raw_line.lstrip()
        leading_ws = len(raw_line) - len(stripped)
        content = stripped.rstrip()

        if not content or content.startswith("#"):
            continue

        if ":" not in content:
            raise FlagFileError(
                "expected 'flag:', 'default:', or 'rule:'",
                source_name, line_no, leading_ws + 1, raw_line,
            )

        directive, _, rest = content.partition(":")
        directive = directive.strip()
        directive_col = leading_ws + 1

        rest_lstripped = rest.lstrip()
        rest_ws = len(rest) - len(rest_lstripped)
        rest_col = leading_ws + len(directive) + 2 + rest_ws
        value = rest_lstripped.rstrip()

        if directive == "flag":
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", value or ""):
                raise FlagFileError(
                    f"{value!r} is not a valid flag name; use letters, numbers, '_' and '-'",
                    source_name, line_no, rest_col, raw_line,
                )
            if value in flags:
                raise FlagFileError(
                    f"flag {value!r} is already defined at line {flags[value].line}",
                    source_name, line_no, directive_col, raw_line,
                )
            current = Flag(name=value, line=line_no)
            flags[value] = current

        elif directive == "default":
            if current is None:
                raise FlagFileError(
                    "'default' must come after a 'flag:' line",
                    source_name, line_no, directive_col, raw_line,
                )
            if value not in ("on", "off"):
                raise FlagFileError(
                    f"expected 'on' or 'off', found {value!r}",
                    source_name, line_no, rest_col, raw_line,
                )
            if current.default is not None:
                raise FlagFileError(
                    f"default is already set for flag {current.name!r} at line {current.line}",
                    source_name, line_no, directive_col, raw_line,
                )
            current.default = value == "on"

        elif directive == "rule":
            if current is None:
                raise FlagFileError(
                    "'rule' must come after a 'flag:' line",
                    source_name, line_no, directive_col, raw_line,
                )
            rule = _parse_rule_expr(rest_lstripped, line_no, rest_col, raw_line, source_name)
            current.rules.append(rule)

        else:
            raise FlagFileError(
                f"unknown directive {directive!r}; expected 'flag', 'default', or 'rule'",
                source_name, line_no, directive_col, raw_line,
            )

    for flag in flags.values():
        if flag.default is None:
            raise FlagFileError(
                f"flag {flag.name!r} has no 'default:' line",
                source_name, flag.line, 1, lines[flag.line - 1],
            )

    return flags


def parse_file(path) -> Dict[str, Flag]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return parse(text, source_name=str(path))
