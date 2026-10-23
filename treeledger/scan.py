"""Streaming content hashing with explicit exclusions and no link traversal."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import stat
from pathlib import Path

from .models import FileEntry, LedgerError, Snapshot, validate_path, validate_pattern

DEFAULT_EXCLUDES = (".git/", ".venv/", "venv/", "node_modules/", "__pycache__/", ".pytest_cache/")
CHUNK_SIZE = 1024 * 1024


def excluded(path: str, is_dir: bool, patterns: tuple[str, ...]) -> bool:
    parts = path.split("/")
    for pattern in patterns:
        directory_only = pattern.endswith("/")
        anchored = pattern.startswith("/")
        pattern = pattern.removeprefix("/").removesuffix("/")
        for length in range(1, len(parts) + 1):
            if directory_only and length == len(parts) and not is_dir:
                continue
            candidate = "/".join(parts[:length]) if anchored or "/" in pattern else parts[length - 1]
            if fnmatch.fnmatchcase(candidate, pattern):
                return True
    return False


def literal_exclude(path: str) -> str:
    # Escape glob metacharacters without escaping the brackets we introduce.
    return "/" + "".join({"[": "[[]", "*": "[*]", "?": "[?]"}.get(c, c) for c in path)


def collect_excludes(root: Path, extra: list[str], output: Path | None) -> tuple[str, ...]:
    patterns = list(DEFAULT_EXCLUDES)
    ignore_file = root / ".treeledgerignore"
    if ignore_file.is_symlink():
        raise LedgerError(".treeledgerignore must be a regular file, not a symbolic link.")
    if ignore_file.exists():
        try:
            for line in ignore_file.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
        except (OSError, UnicodeError) as exc:
            raise LedgerError(f"Cannot read .treeledgerignore: {exc}") from exc
    patterns.extend(extra)
    if output is not None:
        try:
            relative = output.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
        else:
            validate_path(relative)
            patterns.append(literal_exclude(relative))
    return tuple(sorted(set(validate_pattern(p) for p in patterns)))


def _identity(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _signature(info: os.stat_result) -> tuple:
    return (*_identity(info), info.st_ctime_ns)


def hash_file(path: Path, relative: str) -> FileEntry:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise LedgerError(f"File changed type during scan: {relative!r}; retry with a quiet folder.")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        # Windows stat/fstat can give ctime different meanings. Compare ctime
        # only within the same API: https://github.com/python/cpython/issues/157671
        if not stat.S_ISREG(opened.st_mode) or _identity(before) != _identity(opened):
            raise LedgerError(f"File changed before hashing: {relative!r}; retry with a quiet folder.")
        digest = hashlib.sha256()
        size = 0
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(stream.fileno())
    current = path.lstat()
    if size != opened.st_size or _signature(opened) != _signature(after) or _signature(before) != _signature(current):
        raise LedgerError(f"File changed while hashing: {relative!r}; retry with a quiet folder.")
    return FileEntry(relative, size, digest.hexdigest())


def scan(root: Path, excludes: tuple[str, ...]) -> tuple[Snapshot, tuple[str, ...]]:
    root = root.resolve()
    if not root.is_dir():
        raise LedgerError(f"Folder does not exist or is not a directory: {str(root)!r}")
    files: list[FileEntry] = []
    skipped: list[str] = []
    pending = [root]
    try:
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as children:
                entries = sorted(children, key=lambda entry: entry.name)
            for entry in entries:
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                # Windows junctions are reparse points even on Python versions without is_junction().
                info = entry.stat(follow_symlinks=False)
                reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                if entry.is_symlink() or reparse:
                    skipped.append(relative)
                    continue
                is_dir = stat.S_ISDIR(info.st_mode)
                if excluded(relative, is_dir, excludes):
                    continue
                validate_path(relative)
                if is_dir:
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    files.append(hash_file(path, relative))
                else:
                    skipped.append(relative)
    except OSError as exc:
        raise LedgerError(f"Scan failed; no partial snapshot was written: {exc}") from exc
    return Snapshot(tuple(sorted(files, key=lambda f: f.path)), excludes), tuple(sorted(skipped))
