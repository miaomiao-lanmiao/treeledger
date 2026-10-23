# TreeLedger

[![CI](https://github.com/miaomiao-lanmiao/treeledger/actions/workflows/ci.yml/badge.svg)](https://github.com/miaomiao-lanmiao/treeledger/actions/workflows/ci.yml)
[中文说明](README.md) · [Examples](examples/README.md) · [Snapshot format](docs/format.md) · [Releases](https://github.com/miaomiao-lanmiao/treeledger/releases)

**A content ledger for your folders.** Create deterministic SHA-256 snapshots and compare backups, migrations, or deliverables without relying on modification times.

TreeLedger uses only the Python standard library and makes no network requests at runtime. It reports additions, removals, modifications and unambiguous content-based move candidates as text, JSON or Markdown.

## Install

Python 3.10+ is required. The project is distributed on GitHub, not PyPI.

```sh
git clone https://github.com/miaomiao-lanmiao/treeledger.git
cd treeledger
python -m pip install .
treeledger --version
```

For offline installation, download the wheel from [Releases](https://github.com/miaomiao-lanmiao/treeledger/releases), then run:

```sh
python -m pip install --no-index treeledger-0.1.0-py3-none-any.whl
```

From the source checkout, `python -m treeledger` works without installation. Source installation and wheel builds require setuptools; fetching build tools may require network access.

## Use

```sh
treeledger snapshot ./project -o baseline.json
treeledger check baseline.json ./backup
treeledger snapshot ./project -o current.json
treeledger diff baseline.json current.json --format markdown -o changes.md
```

Keep snapshots and reports outside the scanned folders where possible. An explicitly selected snapshot output inside its own source folder is automatically excluded. Other snapshot/report files are not automatically excluded.

`snapshot` writes JSON to stdout when `-o` is omitted. `diff` and `check` default to text on stdout; `--format json` and `--format markdown` are also available. Status messages go to stderr. Reports are written via a temporary file and replacement, so a failed scan never leaves a partial report.

| Exit code | Meaning |
| --- | --- |
| 0 | Snapshot written, or comparison found no changes |
| 1 | File changes or exclusion-rule differences found |
| 2 | Invalid input, invalid arguments, or filesystem error |

Exit code 1 is an expected comparison result. Scripts should distinguish it from errors.

## Exclusions

Defaults exclude directories named `.git`, `.venv`, `venv`, `node_modules`, `__pycache__` and `.pytest_cache` at every depth. Add a `.treeledgerignore` file at the scanned root or repeat `--exclude GLOB`:

```gitignore
# Blank lines and comments are ignored
*.tmp
cache/
/build/
private/*.key
```

- Matching is case-sensitive on every operating system.
- A pattern without `/` matches names at any depth. A leading `/` anchors it to the root. Other patterns containing `/` are also relative to the root.
- A trailing `/` matches directories and their descendants only.
- Patterns use Python `fnmatch`: `*`, `?`, and `[abc]` work; `*` can span `/`. `**` has no special meaning.
- Negated rules (`!`) are rejected. This is not full gitignore syntax.
- The ignore file itself is included as an ordinary file unless excluded.

`check` reuses the baseline's saved rules, without reloading the current ignore file. If `diff` compares snapshots with different rules, it reports the coverage difference and exits 1, even when their file lists are identical.

## Guarantees and limits

- Snapshots contain relative paths, sizes, hashes and exclusion rules. They omit file contents, absolute roots and generation timestamps. Identical content and rules produce identical snapshots.
- File names and hashes can still be sensitive. Nothing is uploaded by the program.
- Regular files are read in 1 MiB chunks. Detected changes during hashing and read failures abort the operation, preserving any existing output.
- Symbolic links, Windows reparse points (including junctions), and special files are skipped with a stderr count. Their changes are not tracked.
- Empty directories, permissions, timestamps, extended attributes and filesystem-specific data are not tracked. Paths are case-sensitive and must be canonical relative paths without `:` or backslashes.
- This is not an atomic filesystem snapshot or a security boundary against hostile concurrent filesystem changes. Use a quiet folder or a filesystem snapshot for consistent results.
- A move is inferred only when exactly one removed file and one added file share a size and hash. Ambiguous matches remain additions/removals. This does not prove actual move history.
- TreeLedger does not copy, restore or delete source files, and snapshots are not digitally signed.

## Development

```sh
python -m unittest discover -s tests -v
python -m pip wheel --no-deps . --wheel-dir dist
```

CI runs on Windows, macOS and Linux with Python 3.10 and 3.13, and checks the installed command outside the checkout. Platform-specific tests skip when unavailable. See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under MIT.
