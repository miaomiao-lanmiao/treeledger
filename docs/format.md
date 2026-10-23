# Snapshot format, version 1

A UTF-8 JSON document has exactly these fields:

```json
{
  "format": "treeledger.snapshot",
  "version": 1,
  "algorithm": "sha256",
  "excludes": [],
  "files": [
    {
      "path": "empty.txt",
      "size": 0,
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
  ]
}
```

The writer sorts paths and exclusion rules, uses two-space indentation and a final newline, and escapes non-ASCII characters. Paths always use `/`, independent of the host OS. Root paths, file timestamps and snapshot timestamps are intentionally omitted.

The loader accepts UTF-8 with or without a byte order mark. It rejects unsupported versions/algorithms, duplicate JSON keys, duplicate paths, extra fields, malformed hashes, negative/non-integer sizes (including booleans), absolute paths, empty/dot/parent segments, backslashes, colons and NULs. Digests must be 64 lowercase hexadecimal characters. Exclusion rules are deduplicated and validated. The loader validates structure, not authenticity or correspondence to original file bytes.

## Diff format

JSON reports use `format: "treeledger.diff"` and `version: 1` with:

- `changed`: true when file changes or rule differences exist.
- `rules_changed`: true when the sets of exclusion rules differ.
- `summary`: counts for `added`, `removed`, `modified`, `moved`, and `unchanged`.
- `added` / `removed`: arrays of file records.
- `modified` / `moved`: arrays of objects containing `before` and `after` file records.

An unchanged path is identified by equal size and hash. A modified path is counted once. Move candidates are removed from addition/removal lists, so the summary categories do not overlap. Matching uses exact case-sensitive paths; content matching is SHA-256 plus byte size. Reports do not include the full unchanged file list.

Files are hashed in streaming chunks, but manifests and comparisons are kept in memory. Runtime is dominated by total bytes read; memory grows with file count. This release is intended for ordinary project and backup folders, not unbounded manifests from untrusted sources.
