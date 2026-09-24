import unittest

from flagquery.parser import BoolExpr, Comparison, FlagFileError, parse

VALID = """\
flag: checkout_v2
default: off
rule: env == staging -> on
rule: user.plan == enterprise -> on

flag: new_dashboard
default: on
rule: user.beta == false -> off
"""


class ParseTests(unittest.TestCase):
    def test_parses_flags_and_rules(self):
        flags = parse(VALID, source_name="test.flags")

        checkout = flags["checkout_v2"]
        self.assertFalse(checkout.default)
        self.assertEqual(len(checkout.rules), 2)
        self.assertEqual(checkout.rules[0].condition, Comparison("env", "==", "staging"))
        self.assertTrue(checkout.rules[0].result)

        dashboard = flags["new_dashboard"]
        self.assertTrue(dashboard.default)

    def test_and_combines_comparisons(self):
        text = (
            "flag: x\ndefault: off\n"
            "rule: env == staging and user.plan == enterprise -> on\n"
        )
        flags = parse(text, source_name="test.flags")
        condition = flags["x"].rules[0].condition
        self.assertEqual(
            condition,
            BoolExpr(
                "and",
                [Comparison("env", "==", "staging"), Comparison("user.plan", "==", "enterprise")],
            ),
        )
        self.assertTrue(condition.evaluate({"env": "staging", "user.plan": "enterprise"}))
        self.assertFalse(condition.evaluate({"env": "staging", "user.plan": "free"}))

    def test_or_and_parentheses_grouping(self):
        text = (
            "flag: x\ndefault: off\n"
            "rule: user.plan == enterprise and (env == staging or env == canary) -> on\n"
        )
        flags = parse(text, source_name="test.flags")
        condition = flags["x"].rules[0].condition
        self.assertTrue(condition.evaluate({"user.plan": "enterprise", "env": "canary"}))
        self.assertFalse(condition.evaluate({"user.plan": "free", "env": "canary"}))
        self.assertFalse(condition.evaluate({"user.plan": "enterprise", "env": "production"}))

    def test_unclosed_paren_reports_column(self):
        text = "flag: x\ndefault: off\nrule: (env == staging -> on\n"
        with self.assertRaises(FlagFileError) as ctx:
            parse(text, source_name="test.flags")
        self.assertEqual(ctx.exception.line, 3)
        self.assertIn("expected ')'", ctx.exception.message)

    def test_bad_operator_reports_line_and_column(self):
        text = "flag: x\ndefault: off\nrule: env = staging -> on\n"
        with self.assertRaises(FlagFileError) as ctx:
            parse(text, source_name="test.flags")
        self.assertEqual(ctx.exception.line, 3)
        self.assertEqual(ctx.exception.column, 11)

    def test_missing_default_reports_flag_line(self):
        text = "flag: x\nrule: env == staging -> on\n"
        with self.assertRaises(FlagFileError) as ctx:
            parse(text, source_name="test.flags")
        self.assertEqual(ctx.exception.line, 1)

    def test_duplicate_flag_references_first_definition(self):
        text = "flag: x\ndefault: off\nflag: x\ndefault: on\n"
        with self.assertRaises(FlagFileError) as ctx:
            parse(text, source_name="test.flags")
        self.assertIn("line 1", ctx.exception.message)

    def test_numeric_comparison(self):
        text = "flag: x\ndefault: off\nrule: user.signup_days >= 30 -> on\n"
        flags = parse(text, source_name="test.flags")
        condition = flags["x"].rules[0].condition
        self.assertEqual(condition, Comparison("user.signup_days", ">=", 30))
        self.assertTrue(condition.evaluate({"user.signup_days": "45"}))
        self.assertTrue(condition.evaluate({"user.signup_days": "30"}))
        self.assertFalse(condition.evaluate({"user.signup_days": "29"}))
        self.assertFalse(condition.evaluate({"user.signup_days": "not-a-number"}))

    def test_float_comparison(self):
        text = "flag: x\ndefault: off\nrule: error_rate < 0.5 -> on\n"
        flags = parse(text, source_name="test.flags")
        condition = flags["x"].rules[0].condition
        self.assertTrue(condition.evaluate({"error_rate": "0.2"}))
        self.assertFalse(condition.evaluate({"error_rate": "0.9"}))

    def test_boolean_comparison(self):
        text = "flag: x\ndefault: off\nrule: user.beta == true -> on\n"
        flags = parse(text, source_name="test.flags")
        condition = flags["x"].rules[0].condition
        self.assertEqual(condition, Comparison("user.beta", "==", True))
        self.assertTrue(condition.evaluate({"user.beta": "true"}))
        self.assertFalse(condition.evaluate({"user.beta": "false"}))
        self.assertFalse(condition.evaluate({"user.beta": "yes"}))

    def test_relational_operator_requires_numeric_value(self):
        text = "flag: x\ndefault: off\nrule: env >= staging -> on\n"
        with self.assertRaises(FlagFileError) as ctx:
            parse(text, source_name="test.flags")
        self.assertEqual(ctx.exception.line, 3)
        self.assertIn("only works with numeric values", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
