# flagquery

A command-line tool that answers one question: **is this feature flag on,
and why?**

Most feature flag systems end up as a pile of JSON or YAML that only the
app itself can evaluate. When someone asks "why is checkout_v2 off for
this staging user," the honest answer is usually "let me go add a log
line and redeploy." flagquery reads a plain-text flags file and evaluates
a flag against a context you give it on the command line, so you can
answer that question without touching the app.

It does one thing. It is not a flag management platform, it does not
talk to a server, and it does not have a UI. It reads a file and tells
you the result of one rule.

## The flags file format

```
flag: checkout_v2
default: off
rule: env == staging -> on
rule: user.plan == enterprise -> on

flag: new_dashboard
default: on
rule: user.beta == false -> off
```

Each flag has a default and an ordered list of rules. Rules are checked
top to bottom; the first one whose condition matches the given context
wins. If nothing matches, the default applies.

A rule's condition can combine comparisons with `and` and `or`, and use
parentheses to group them:

```
rule: user.plan == enterprise and (env == staging or env == canary) -> on
```

`and` binds tighter than `or`, the same as most languages, so
`a == 1 or b == 2 and c == 3` reads as `a == 1 or (b == 2 and c == 3)`.
Use parentheses when you mean something else.

A comparison value can be a bare word, a quoted string, a number, or
`true`/`false`. Numbers and booleans are compared as their own type, not
as text, and the context value on the command line is coerced to match:

```
rule: user.signup_days >= 30 -> on
rule: error_rate < 0.5 -> on
rule: user.beta == true -> off
```

`==` and `!=` work with any value type. `>`, `<`, `>=`, and `<=` only
make sense for numbers, so using one with a non-numeric value is a parse
error rather than a rule that silently never matches.

## Usage

```
$ python -m flagquery why checkout_v2 flags.txt --context env=staging
checkout_v2 is on
  matched rule at flags.txt:3: rule: env == staging -> on

$ python -m flagquery why checkout_v2 flags.txt --context env=production
checkout_v2 is off
  no rule matched, used the default from flags.txt:2
```

## Why the errors matter

The whole point of this tool is to be trustworthy about a config file
nobody wants to hand-parse. A typo shouldn't produce a silent wrong
answer, it should point at exactly where it went wrong:

```
$ python -m flagquery why checkout_v2 flags.txt --context env=staging
flags.txt:3:12: error: '=' is not a valid comparison here, use '==' or '!='
    rule: env = staging -> on
               ^
```

Every parse error reports the file, line, and column, along with the
offending line and a caret pointing at the exact character.

## Status

This is a first pass: the parser and the `why` command work end to end.
The rule language supports `and`/`or` grouping, parentheses, and
comparisons over strings, numbers, and booleans (`==`, `!=`, `>`, `<`,
`>=`, `<=`). There's no negation yet. See the roadmap for what's next.

## Development

No dependencies to install. Run the tests with:

```
python -m unittest discover
```
