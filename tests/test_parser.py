import unittest

from flagquery.parser import FlagFileError, parse

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
        self.assertEqual(checkout.rules[0].key, "env")
        self.assertEqual(checkout.rules[0].op, "==")
        self.assertEqual(checkout.rules[0].value, "staging")
        self.assertTrue(checkout.rules[0].result)

        dashboard = flags["new_dashboard"]
        self.assertTrue(dashboard.default)

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


if __name__ == "__main__":
    unittest.main()
