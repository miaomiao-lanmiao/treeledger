"""Versioned, strictly validated snapshot format."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


class LedgerError(Exception):
    """An actionable input or filesystem error."""


def validate_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise LedgerError("File paths must be non-empty strings.")
    if "\\" in value or ":" in value or "\x00" in value:
        raise LedgerError(f"Unsupported path: {value!r}; use portable relative paths.")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise LedgerError(f"Unsafe or non-canonical relative path: {value!r}")
    return value


def validate_pattern(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise LedgerError("Exclude patterns must be non-empty strings without outer whitespace.")
    if value.startswith("!"):
        raise LedgerError("Negated ignore patterns (!) are not supported.")
    core = value.removeprefix("/").removesuffix("/")
    validate_path(core)
    return value


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    sha256: str

    def as_dict(self) -> dict:
        return {"path": self.path, "size": self.size, "sha256": self.sha256}


@dataclass(frozen=True)
class Snapshot:
    files: tuple[FileEntry, ...]
    excludes: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "format": "treeledger.snapshot",
            "version": 1,
            "algorithm": "sha256",
            "excludes": sorted(self.excludes),
            "files": [entry.as_dict() for entry in sorted(self.files, key=lambda f: f.path)],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=True, indent=2) + "\n"


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise LedgerError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def parse_snapshot(data: object) -> Snapshot:
    keys = {"format", "version", "algorithm", "excludes", "files"}
    if not isinstance(data, dict) or set(data) != keys:
        raise LedgerError("Not a TreeLedger snapshot: expected format, version, algorithm, excludes, files.")
    if data["format"] != "treeledger.snapshot" or type(data["version"]) is not int or data["version"] != 1:
        raise LedgerError("Unsupported snapshot format or version (expected version 1).")
    if data["algorithm"] != "sha256":
        raise LedgerError("Unsupported hash algorithm (expected sha256).")
    if not isinstance(data["excludes"], list) or not isinstance(data["files"], list):
        raise LedgerError("Snapshot excludes and files must be arrays.")
    excludes = tuple(sorted(set(validate_pattern(p) for p in data["excludes"])))
    entries = []
    paths = set()
    for record in data["files"]:
        if not isinstance(record, dict) or set(record) != {"path", "size", "sha256"}:
            raise LedgerError("Each file must contain exactly path, size and sha256.")
        path = validate_path(record["path"])
        size, digest = record["size"], record["sha256"]
        if type(size) is not int or size < 0:
            raise LedgerError(f"Invalid file size for {path!r}.")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise LedgerError(f"Invalid SHA-256 digest for {path!r}.")
        if path in paths:
            raise LedgerError(f"Duplicate file path: {path!r}")
        paths.add(path)
        entries.append(FileEntry(path, size, digest))
    return Snapshot(tuple(sorted(entries, key=lambda f: f.path)), excludes)


def load_snapshot(path: Path) -> Snapshot:
    try:
        return parse_snapshot(json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise LedgerError(f"Cannot read snapshot {str(path)!r}: {exc}") from exc
