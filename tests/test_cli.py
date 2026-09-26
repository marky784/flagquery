import contextlib
import io
import os
import tempfile
import unittest

from flagquery.cli import main

VALID = """\
flag: checkout_v2
default: off
rule: env == staging -> on
rule: user.plan == enterprise -> on

flag: new_dashboard
default: on
"""

INVALID = "flag: x\nrule: env == staging -> on\n"


def _write(text: str) -> str:
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".flags", delete=False)
    handle.write(text)
    handle.close()
    return handle.name


class ValidateCommandTests(unittest.TestCase):
    def setUp(self):
        self.paths = []

    def tearDown(self):
        for path in self.paths:
            os.unlink(path)

    def _flags_file(self, text: str) -> str:
        path = _write(text)
        self.paths.append(path)
        return path

    def test_valid_file_reports_counts_and_exits_zero(self):
        path = self._flags_file(VALID)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["validate", path])
        self.assertEqual(code, 0)
        self.assertIn("ok, 2 flags, 2 rules", out.getvalue())

    def test_invalid_file_reports_error_and_exits_nonzero(self):
        path = self._flags_file(INVALID)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["validate", path])
        self.assertEqual(code, 1)
        self.assertIn("no 'default:' line", err.getvalue())

    def test_missing_file_exits_nonzero(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["validate", "/no/such/flags.txt"])
        self.assertEqual(code, 1)
        self.assertIn("could not read", err.getvalue())


if __name__ == "__main__":
    unittest.main()
