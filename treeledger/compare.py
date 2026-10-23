"""Content-based change classification and conservative move detection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .models import FileEntry, Snapshot


@dataclass(frozen=True)
class Comparison:
    added: tuple[FileEntry, ...]
    removed: tuple[FileEntry, ...]
    modified: tuple[tuple[FileEntry, FileEntry], ...]
    moved: tuple[tuple[FileEntry, FileEntry], ...]
    unchanged: int
    rules_changed: bool

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.modified or self.moved or self.rules_changed)

    @property
    def counts(self) -> dict:
        return {
            "added": len(self.added), "removed": len(self.removed),
            "modified": len(self.modified), "moved": len(self.moved),
            "unchanged": self.unchanged,
        }

    def as_dict(self) -> dict:
        return {
            "format": "treeledger.diff", "version": 1,
            "changed": self.changed, "rules_changed": self.rules_changed,
            "summary": self.counts,
            "added": [f.as_dict() for f in self.added],
            "removed": [f.as_dict() for f in self.removed],
            "modified": [{"before": a.as_dict(), "after": b.as_dict()} for a, b in self.modified],
            "moved": [{"before": a.as_dict(), "after": b.as_dict()} for a, b in self.moved],
        }


def compare(before: Snapshot, after: Snapshot) -> Comparison:
    old = {f.path: f for f in before.files}
    new = {f.path: f for f in after.files}
    removed = {p: old[p] for p in old.keys() - new.keys()}
    added = {p: new[p] for p in new.keys() - old.keys()}
    modified = []
    unchanged = 0
    for path in sorted(old.keys() & new.keys()):
        if (old[path].sha256, old[path].size) == (new[path].sha256, new[path].size):
            unchanged += 1
        else:
            modified.append((old[path], new[path]))
    old_groups: dict[tuple, list[FileEntry]] = defaultdict(list)
    new_groups: dict[tuple, list[FileEntry]] = defaultdict(list)
    for entry in removed.values():
        old_groups[(entry.sha256, entry.size)].append(entry)
    for entry in added.values():
        new_groups[(entry.sha256, entry.size)].append(entry)
    moves = []
    for identity in sorted(old_groups.keys() & new_groups.keys()):
        left, right = old_groups[identity], new_groups[identity]
        if len(left) == len(right) == 1:
            moves.append((left[0], right[0]))
            del removed[left[0].path]
            del added[right[0].path]
    return Comparison(
        tuple(added[p] for p in sorted(added)), tuple(removed[p] for p in sorted(removed)),
        tuple(modified), tuple(sorted(moves, key=lambda pair: pair[0].path)),
        unchanged, set(before.excludes) != set(after.excludes),
    )
