from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from treeledger.cli import main, write_output
from treeledger.compare import compare
from treeledger.models import FileEntry, LedgerError, Snapshot, load_snapshot, parse_snapshot
from treeledger.render import render
from treeledger.scan import collect_excludes, excluded, hash_file, scan


def entry(path: str, content: bytes = b"hello") -> FileEntry:
    return FileEntry(path, len(content), hashlib.sha256(content).hexdigest())


def snapshot(*entries: FileEntry, excludes: tuple[str, ...] = ()) -> Snapshot:
    return Snapshot(tuple(entries), excludes)


class TemporaryFolder(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "input"
        self.root.mkdir()

    def put(self, path: str, data: bytes = b"hello") -> Path:
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return destination

    def invoke(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()


class SnapshotTests(TemporaryFolder):
    def test_content_hash_size_unicode_and_empty_file(self):
        self.put("资料/说明.txt", "文件内容".encode())
        self.put("empty", b"")
        result, skipped = scan(self.root, ())
        self.assertEqual(result.files, tuple(sorted((entry("资料/说明.txt", "文件内容".encode()), entry("empty", b"")), key=lambda f: f.path)))
        self.assertEqual(skipped, ())

    def test_snapshot_is_deterministic_and_has_no_root_or_timestamp(self):
        self.put("z.txt")
        self.put("a.txt", b"a")
        first, _ = scan(self.root, ())
        os.utime(self.root / "a.txt", (1000000000, 1000000000))
        second, _ = scan(self.root, ())
        self.assertEqual(first.to_json(), second.to_json())
        self.assertNotIn(str(self.root), first.to_json())
        self.assertEqual([f.path for f in first.files], ["a.txt", "z.txt"])

    def test_streams_multiple_chunks(self):
        data = bytes(range(256)) * 100
        file = self.put("binary", data)
        with patch("treeledger.scan.CHUNK_SIZE", 127):
            self.assertEqual(hash_file(file, "binary"), entry("binary", data))

    def test_default_exclusions_and_nested_directories(self):
        self.put("src/main.py")
        self.put("nested/node_modules/library.js")
        self.put(".git/config")
        self.put(".venv/bin/python")
        result, _ = scan(self.root, collect_excludes(self.root, [], None))
        self.assertEqual([f.path for f in result.files], ["src/main.py"])

    def test_ignore_file_comments_and_extra_exclusions(self):
        self.put(".treeledgerignore", b"# temporary\n*.tmp\ncache/\n\n")
        self.put("nested/a.tmp")
        self.put("cache/data")
        self.put("private.key")
        self.put("keep.txt")
        result, _ = scan(self.root, collect_excludes(self.root, ["*.key"], None))
        self.assertEqual([f.path for f in result.files], [".treeledgerignore", "keep.txt"])

    def test_output_in_root_is_excluded_exactly_and_escaped(self):
        output = self.root / "state[1].json"
        self.put("state[1].json", b"old output")
        self.put("state1.json")
        self.put("nested/state[1].json")
        rules = collect_excludes(self.root, [], output)
        result, _ = scan(self.root, rules)
        self.assertEqual([f.path for f in result.files], ["nested/state[1].json", "state1.json"])

    def test_directory_only_pattern_does_not_exclude_regular_file(self):
        self.put("cache")
        result, _ = scan(self.root, ("cache/",))
        self.assertEqual(len(result.files), 1)

    def test_anchored_pattern_and_case_sensitive_matching(self):
        self.assertTrue(excluded("build/a.txt", False, ("/build/",)))
        self.assertFalse(excluded("sub/build/a.txt", False, ("/build/",)))
        self.assertFalse(excluded("A.TMP", False, ("*.tmp",)))
        self.assertTrue(excluded("docs/sub/a.tmp", False, ("docs/*.tmp",)))

    def test_missing_root_and_file_root_fail(self):
        for root in (self.root / "absent", self.put("file")):
            with self.subTest(root=root), self.assertRaises(LedgerError):
                scan(root, ())

    def test_read_error_fails_scan(self):
        self.put("unreadable")
        with patch("treeledger.scan.hash_file", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(LedgerError, "no partial snapshot"):
                scan(self.root, ())

    def test_file_mutation_while_hashing_fails(self):
        file = self.put("changing", b"original")
        actual_fdopen = os.fdopen

        class MutatingReader:
            def __init__(self, *args):
                self.stream = actual_fdopen(*args)
                self.mutated = False

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def fileno(self):
                return self.stream.fileno()

            def read(self, size):
                data = self.stream.read(size)
                if not self.mutated:
                    file.write_bytes(b"changed and longer")
                    self.mutated = True
                return data

        with patch("treeledger.scan.os.fdopen", MutatingReader):
            with self.assertRaisesRegex(LedgerError, "changed while hashing"):
                hash_file(file, "changing")

    def test_symlink_file_and_directory_are_not_followed(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secret").write_text("outside")
        try:
            (self.root / "link").symlink_to(outside / "secret")
            (self.root / "directory-link").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")
        result, skipped = scan(self.root, ())
        self.assertEqual(result.files, ())
        self.assertEqual(skipped, ("directory-link", "link"))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO support requires POSIX")
    def test_fifo_is_skipped_without_blocking(self):
        os.mkfifo(self.root / "pipe")
        result, skipped = scan(self.root, ())
        self.assertEqual(result.files, ())
        self.assertEqual(skipped, ("pipe",))

    @unittest.skipUnless(os.name == "nt", "Junctions require Windows")
    def test_windows_junction_is_not_followed(self):
        outside = self.base / "junction-target"
        outside.mkdir()
        (outside / "secret").write_text("outside")
        junction = self.root / "junction"
        created = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True)
        if created.returncode:
            self.skipTest("Junction creation unavailable")
        self.addCleanup(lambda: junction.rmdir() if junction.exists() else None)
        result, skipped = scan(self.root, ())
        self.assertEqual(result.files, ())
        self.assertEqual(skipped, ("junction",))


class ValidationTests(TemporaryFolder):
    def valid(self):
        return snapshot(entry("a")).as_dict()

    def test_round_trip_and_utf8_bom(self):
        file = self.base / "snapshot.json"
        source = snapshot(entry("中文"), excludes=("*.tmp",))
        file.write_text(source.to_json(), encoding="utf-8-sig")
        self.assertEqual(load_snapshot(file), source)

    def test_rejects_non_snapshot_and_unknown_schema(self):
        for data in (None, [], {}, {**self.valid(), "extra": 1}, {**self.valid(), "version": True}, {**self.valid(), "version": 99}, {**self.valid(), "algorithm": "md5"}):
            with self.subTest(data=data), self.assertRaises(LedgerError):
                parse_snapshot(data)

    def test_rejects_unsafe_or_noncanonical_paths(self):
        for path in ("../a", "/a", "a//b", "a/./b", "a/../b", "a\\b", "C:/file", "", "a\x00b", 42):
            data = self.valid()
            data["files"][0]["path"] = path
            with self.subTest(path=path), self.assertRaises(LedgerError):
                parse_snapshot(data)

    def test_rejects_bad_sizes_and_hashes(self):
        for field, value in (("size", -1), ("size", True), ("size", 1.2), ("sha256", "a" * 63), ("sha256", "G" * 64), ("sha256", None)):
            data = self.valid()
            data["files"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(LedgerError):
                parse_snapshot(data)

    def test_rejects_duplicate_paths(self):
        data = self.valid()
        data["files"] *= 2
        with self.assertRaisesRegex(LedgerError, "Duplicate file path"):
            parse_snapshot(data)

    def test_rejects_duplicate_json_keys(self):
        file = self.base / "duplicate.json"
        file.write_text('{"version": 1, "version": 2}')
        with self.assertRaisesRegex(LedgerError, "Duplicate JSON key"):
            load_snapshot(file)

    def test_rejects_invalid_json_and_encoding(self):
        file = self.base / "invalid.json"
        for content in (b"{", b"\xff"):
            file.write_bytes(content)
            with self.assertRaises(LedgerError):
                load_snapshot(file)

    def test_rejects_invalid_ignore_patterns(self):
        for pattern in ("!keep", "../x", "C:\\temp", "", " spaced", 7, "/"):
            with self.subTest(pattern=pattern), self.assertRaises(LedgerError):
                collect_excludes(self.root, [pattern], None)


class ComparisonTests(unittest.TestCase):
    def test_all_change_kinds(self):
        before = snapshot(entry("keep"), entry("edit", b"old"), entry("old-name", b"move"), entry("gone", b"gone"))
        after = snapshot(entry("keep"), entry("edit", b"new"), entry("new-name", b"move"), entry("new", b"new file"))
        result = compare(before, after)
        self.assertEqual(result.counts, {"added": 1, "removed": 1, "modified": 1, "moved": 1, "unchanged": 1})
        self.assertTrue(result.changed)
        self.assertEqual(result.moved[0][0].path, "old-name")

    def test_same_size_modification_is_detected(self):
        result = compare(snapshot(entry("file", b"abc")), snapshot(entry("file", b"xyz")))
        self.assertEqual(len(result.modified), 1)

    def test_ambiguous_moves_are_not_guessed(self):
        result = compare(snapshot(entry("a"), entry("b")), snapshot(entry("c"), entry("d")))
        self.assertEqual(result.counts["moved"], 0)
        self.assertEqual(result.counts["added"], 2)
        self.assertEqual(result.counts["removed"], 2)

    def test_one_to_many_is_ambiguous(self):
        result = compare(snapshot(entry("a")), snapshot(entry("b"), entry("c")))
        self.assertEqual(len(result.moved), 0)

    def test_copies_are_added(self):
        result = compare(snapshot(entry("a")), snapshot(entry("a"), entry("b")))
        self.assertEqual(result.counts["added"], 1)
        self.assertEqual(result.counts["moved"], 0)

    def test_rule_change_is_visible_even_when_content_is_equal(self):
        result = compare(snapshot(entry("a")), snapshot(entry("a"), excludes=("*.tmp",)))
        self.assertTrue(result.changed)
        self.assertTrue(result.rules_changed)
        self.assertIn("Exclusion rules differ", render(result, "text"))

    def test_rule_order_does_not_matter(self):
        result = compare(snapshot(excludes=("a", "b")), snapshot(excludes=("b", "a")))
        self.assertFalse(result.changed)

    def test_empty_and_identical_snapshots(self):
        for source in (snapshot(), snapshot(entry("a"))):
            self.assertFalse(compare(source, source).changed)

    def test_report_order_is_stable(self):
        left = compare(snapshot(), snapshot(entry("z"), entry("a")))
        right = compare(snapshot(), snapshot(entry("a"), entry("z")))
        self.assertEqual(render(left, "json"), render(right, "json"))

    def test_json_report_schema(self):
        result = json.loads(render(compare(snapshot(), snapshot(entry("a"))), "json"))
        self.assertEqual(result["format"], "treeledger.diff")
        self.assertEqual(result["summary"]["added"], 1)
        self.assertEqual(result["added"][0]["path"], "a")

    def test_text_escapes_terminal_controls(self):
        result = compare(snapshot(), snapshot(entry("file\nforged\x1b[31m")))
        output = render(result, "text")
        self.assertEqual(len(output.splitlines()), 3)
        self.assertNotIn("\x1b", output)

    def test_markdown_escapes_markup_and_table_characters(self):
        result = compare(snapshot(), snapshot(entry("<script>|`[link](url)\n.txt")))
        output = render(result, "markdown")
        self.assertNotIn("<script>", output)
        self.assertIn("&#124;", output)
        self.assertIn("&#96;", output)
        self.assertIn("&lt;script&gt;", output)


class CLITests(TemporaryFolder):
    def test_checked_in_examples_match_real_scans_and_reports(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        before = load_snapshot(examples / "before.snapshot.json")
        after = load_snapshot(examples / "after.snapshot.json")
        self.assertEqual(scan(examples / "before", before.excludes)[0], before)
        self.assertEqual(scan(examples / "after", after.excludes)[0], after)
        result = compare(before, after)
        self.assertEqual(render(result, "markdown"), (examples / "changes.md").read_text(encoding="utf-8"))
        self.assertEqual(render(result, "json"), (examples / "changes.json").read_text(encoding="utf-8"))

    def test_snapshot_and_check_exit_codes(self):
        self.put("file", b"one")
        baseline = self.base / "baseline.json"
        code, out, err = self.invoke("snapshot", str(self.root), "-o", str(baseline))
        self.assertEqual((code, out), (0, ""))
        self.assertIn("Saved 1 files", err)
        self.assertEqual(self.invoke("check", str(baseline), str(self.root))[0], 0)
        self.put("file", b"two")
        code, out, _ = self.invoke("check", str(baseline), str(self.root), "--format", "json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["summary"]["modified"], 1)

    def test_snapshot_stdout_is_json_only(self):
        self.put("file")
        code, out, err = self.invoke("snapshot", str(self.root))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(json.loads(out)["files"]), 1)

    def test_check_uses_saved_rules(self):
        self.put("file")
        baseline = self.base / "baseline.json"
        self.assertEqual(self.invoke("snapshot", str(self.root), "--exclude", "*.tmp", "-o", str(baseline))[0], 0)
        self.put("later.tmp", b"ignored")
        self.assertEqual(self.invoke("check", str(baseline), str(self.root))[0], 0)

    def test_repeated_snapshot_inside_root_is_stable(self):
        self.put("file")
        baseline = self.root / "baseline.json"
        args = ("snapshot", str(self.root), "-o", str(baseline))
        self.assertEqual(self.invoke(*args)[0], 0)
        first = baseline.read_bytes()
        self.assertEqual(self.invoke(*args)[0], 0)
        self.assertEqual(first, baseline.read_bytes())
        self.assertEqual(self.invoke("check", str(baseline), str(self.root))[0], 0)

    def test_diff_markdown_file_and_exit_code(self):
        before, after, report = (self.base / name for name in ("before.json", "after.json", "report.md"))
        before.write_text(snapshot().to_json())
        after.write_text(snapshot(entry("new")).to_json())
        code, out, err = self.invoke("diff", str(before), str(after), "--format", "markdown", "-o", str(report))
        self.assertEqual((code, out, err), (1, "", ""))
        self.assertIn("| Added |", report.read_text(encoding="utf-8"))

    def test_diff_cannot_overwrite_its_input(self):
        file = self.base / "baseline.json"
        original = snapshot().to_json()
        file.write_text(original)
        code, _, err = self.invoke("diff", str(file), str(file), "-o", str(file))
        self.assertEqual(code, 2)
        self.assertIn("must not overwrite", err)
        self.assertEqual(file.read_text(), original)

    def test_check_cannot_overwrite_baseline(self):
        file = self.base / "baseline.json"
        file.write_text(snapshot().to_json())
        self.assertEqual(self.invoke("check", str(file), str(self.root), "-o", str(file))[0], 2)

    def test_error_is_concise_and_no_report_is_written(self):
        output = self.base / "report.md"
        code, out, err = self.invoke("diff", "missing.json", "missing2.json", "-o", str(output))
        self.assertEqual((code, out), (2, ""))
        self.assertIn("treeledger:", err)
        self.assertNotIn("Traceback", err)
        self.assertFalse(output.exists())

    def test_failed_scan_preserves_existing_output(self):
        output = self.base / "baseline.json"
        output.write_text("keep me")
        with patch("treeledger.cli.scan", side_effect=LedgerError("file changed")):
            code, _, _ = self.invoke("snapshot", str(self.root), "-o", str(output))
        self.assertEqual(code, 2)
        self.assertEqual(output.read_text(), "keep me")

    def test_failed_atomic_replace_preserves_output_and_cleans_temp(self):
        output = self.base / "report.txt"
        output.write_text("old")
        with patch("treeledger.cli.os.replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                write_output("new", output)
        self.assertEqual(output.read_text(), "old")
        self.assertEqual(list(self.base.glob(".treeledger-*.tmp")), [])

    def test_actual_module_entrypoint(self):
        process = subprocess.run([sys.executable, "-m", "treeledger", "snapshot", str(self.root)], text=True, capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["files"], [])


if __name__ == "__main__":
    unittest.main()
