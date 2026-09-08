"""Command-line entry point for flagquery."""

from __future__ import annotations

import argparse
import difflib
import sys

from .parser import Flag, FlagFileError, Rule, parse_file


def _parse_context(pairs) -> dict:
    context = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"invalid --context value {pair!r}, expected key=value")
        key, _, value = pair.partition("=")
        context[key.strip()] = value.strip()
    return context


def _matches(rule: Rule, context: dict) -> bool:
    actual = context.get(rule.key)
    if actual is None:
        return False
    if rule.op == "==":
        return actual == rule.value
    return actual != rule.value


def cmd_why(args) -> int:
    try:
        flags = parse_file(args.file)
    except FlagFileError as exc:
        print(exc, file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: could not read {args.file}: {exc.strerror}", file=sys.stderr)
        return 1

    flag: Flag = flags.get(args.flag)
    if flag is None:
        message = f"error: no flag named {args.flag!r} in {args.file}"
        close = difflib.get_close_matches(args.flag, flags.keys(), n=1)
        if close:
            message += f" (did you mean {close[0]!r}?)"
        print(message, file=sys.stderr)
        return 1

    context = _parse_context(args.context)

    for rule in flag.rules:
        if _matches(rule, context):
            state = "on" if rule.result else "off"
            print(f"{args.flag} is {state}")
            print(f"  matched rule at {args.file}:{rule.line}: {rule.text}")
            return 0

    state = "on" if flag.default else "off"
    print(f"{args.flag} is {state}")
    print(f"  no rule matched, used the default from {args.file}:{flag.line}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flagquery",
        description="Answer whether a feature flag is on or off, and why.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    why = sub.add_parser(
        "why", help="explain whether a flag is on or off for a given context"
    )
    why.add_argument("flag", help="name of the flag to evaluate")
    why.add_argument("file", help="path to a flags file")
    why.add_argument(
        "--context",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="a context value used to evaluate rules, e.g. --context env=staging",
    )
    why.set_defaults(func=cmd_why)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
