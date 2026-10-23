# Contributing

Please open an issue with the TreeLedger version, Python version, operating system, a minimal synthetic folder layout, the command you ran, and expected/actual behavior. Avoid attaching private snapshots or file contents.

For changes, keep runtime dependencies at zero and preserve deterministic output and documented exit codes. Add a focused regression test when fixing behavior, and run:

```sh
python -m unittest discover -s tests -v
```

Update both READMEs when changing command-line behavior. Snapshot format changes require an explicit version decision. Do not silently reinterpret version 1 snapshots.
