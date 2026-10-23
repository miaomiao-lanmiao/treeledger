"""Command-line entry point. Exit status: 0 same/success, 1 changed, 2 error."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from . import __version__
from .compare import compare
from .models import LedgerError, load_snapshot
from .render import render
from .scan import collect_excludes, scan


def write_output(content: str, destination: Path | None) -> None:
    if destination is None:
        sys.stdout.write(content)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=destination.parent, prefix=".treeledger-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _report_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    parser.add_argument("-o", "--output", type=Path, help="Write the report to a UTF-8 file (default: stdout).")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline folder snapshots and content diffs.")
    parser.add_argument("--version", action="version", version=f"treeledger {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot", help="Hash regular files into a deterministic JSON snapshot.")
    snapshot.add_argument("folder", type=Path)
    snapshot.add_argument("-o", "--output", type=Path, help="Save JSON here (default: stdout).")
    snapshot.add_argument("--exclude", action="append", default=[], metavar="GLOB", help="Additional exclusion; repeatable.")
    diff = commands.add_parser("diff", help="Compare two snapshots without reading the original files.")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    _report_options(diff)
    check = commands.add_parser("check", help="Compare a folder to a baseline using its saved exclusions.")
    check.add_argument("baseline", type=Path)
    check.add_argument("folder", type=Path)
    _report_options(check)
    return parser


def _warn_skipped(skipped: tuple[str, ...]) -> None:
    if skipped:
        print(f"Warning: skipped {len(skipped)} symbolic link(s), reparse point(s) or special file(s).", file=sys.stderr)


def _protect_inputs(output: Path | None, inputs: list[Path]) -> None:
    if output is not None and any(output.resolve() == path.resolve() for path in inputs):
        raise LedgerError("Report output must not overwrite an input snapshot.")


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            root = args.folder.resolve()
            if not root.is_dir():
                raise LedgerError(f"Folder does not exist or is not a directory: {str(root)!r}")
            excludes = collect_excludes(root, args.exclude, args.output)
            snapshot, skipped = scan(root, excludes)
            write_output(snapshot.to_json(), args.output)
            _warn_skipped(skipped)
            if args.output is not None:
                print(f"Saved {len(snapshot.files)} files ({sum(f.size for f in snapshot.files)} bytes).", file=sys.stderr)
            return 0
        if args.command == "diff":
            _protect_inputs(args.output, [args.before, args.after])
            before, after = load_snapshot(args.before), load_snapshot(args.after)
        else:
            _protect_inputs(args.output, [args.baseline])
            before = load_snapshot(args.baseline)
            after, skipped = scan(args.folder, before.excludes)
            _warn_skipped(skipped)
        result = compare(before, after)
        write_output(render(result, args.format), args.output)
        return int(result.changed)
    except (LedgerError, OSError, UnicodeError) as exc:
        print(f"treeledger: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
