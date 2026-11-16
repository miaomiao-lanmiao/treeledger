import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from treeledger.cli import main


class IgnoreOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "source"
        self.root.mkdir()
        self.nested = self.root / "nested"
        self.nested.mkdir()
        (self.root / "keep.txt").write_text("synthetic", encoding="utf-8")

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(arg) for arg in args])
        return code, out.getvalue(), err.getvalue()

    def assert_ignore_output_rejected(self, *args):
        code, out, err = self.invoke(*args)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("must not be the root .treeledgerignore", err)

    def test_snapshot_preserves_existing_ignore_rules_through_parent_alias(self):
        rules = self.root / ".treeledgerignore"
        original = b"# synthetic rules\n*.bak\n"
        rules.write_bytes(original)
        self.assert_ignore_output_rejected(
            "snapshot", self.root, "-o", self.nested / ".." / rules.name
        )
        self.assertEqual(rules.read_bytes(), original)

    def test_check_does_not_create_ignore_file_with_case_variant(self):
        baseline = self.base / "baseline.json"
        self.assertEqual(self.invoke("snapshot", self.root, "-o", baseline)[0], 0)
        target = self.root / ".TreeLedgerIgnore"
        self.assert_ignore_output_rejected("check", baseline, self.root, "-o", target)
        self.assertFalse(target.exists())
        self.assertFalse((self.root / ".treeledgerignore").exists())

    @unittest.skipUnless(os.name == "nt", "Win32 normalizes trailing dots and spaces")
    def test_snapshot_rejects_windows_trailing_dot_alias(self):
        target = self.root / ".treeledgerignore."
        self.assert_ignore_output_rejected("snapshot", self.root, "-o", target)
        self.assertFalse((self.root / ".treeledgerignore").exists())

    def test_snapshot_allows_a_nested_output_named_like_the_ignore_file(self):
        target = self.nested / ".treeledgerignore"
        self.assertEqual(self.invoke("snapshot", self.root, "-o", target)[0], 0)
        self.assertTrue(target.is_file())
        self.assertFalse((self.root / ".treeledgerignore").exists())
