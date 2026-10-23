"""Stable reports for people and scripts."""

from __future__ import annotations

import html
import json

from .compare import Comparison


def quote(path: str) -> str:
    # Escape control characters in filenames so they cannot forge terminal lines.
    return json.dumps(path, ensure_ascii=True)


def render(result: Comparison, format: str) -> str:
    if format == "json":
        return json.dumps(result.as_dict(), ensure_ascii=True, indent=2) + "\n"
    headline = "Changes detected" if result.changed else "No changes"
    counts = ", ".join(f"{value} {key}" for key, value in result.counts.items())
    if format == "text":
        lines = [headline, counts]
        if result.rules_changed:
            lines.append("WARNING: Exclusion rules differ; file coverage may differ.")
        lines.extend(f"+ {quote(f.path)} ({f.size} bytes)" for f in result.added)
        lines.extend(f"- {quote(f.path)} ({f.size} bytes)" for f in result.removed)
        lines.extend(f"~ {quote(a.path)} ({a.size} -> {b.size} bytes)" for a, b in result.modified)
        lines.extend(f"> {quote(a.path)} -> {quote(b.path)} ({b.size} bytes)" for a, b in result.moved)
        return "\n".join(lines) + "\n"
    if format != "markdown":
        raise ValueError(f"Unknown report format: {format}")

    def cell(path: str) -> str:
        return "<code>" + html.escape(quote(path)).replace("|", "&#124;").replace("`", "&#96;") + "</code>"

    lines = [f"# TreeLedger: {headline}", "", counts, ""]
    if result.rules_changed:
        lines.extend(["> Exclusion rules differ; file coverage may differ.", ""])
    if any((result.added, result.removed, result.modified, result.moved)):
        lines.extend(["| Change | Path | Bytes |", "| --- | --- | ---: |"])
        lines.extend(f"| Added | {cell(f.path)} | {f.size} |" for f in result.added)
        lines.extend(f"| Removed | {cell(f.path)} | {f.size} |" for f in result.removed)
        lines.extend(f"| Modified | {cell(a.path)} | {a.size} → {b.size} |" for a, b in result.modified)
        lines.extend(f"| Moved | {cell(a.path)} → {cell(b.path)} | {b.size} |" for a, b in result.moved)
    return "\n".join(lines) + "\n"
