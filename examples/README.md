# 可复现示例 / Reproducible example

从仓库根目录运行。`before/` 与 `after/` 仅包含手工创建的示例数据。
Run from the repository root. Both folders contain synthetic example data only.

```sh
python -m treeledger snapshot examples/before -o examples/before.snapshot.json
python -m treeledger snapshot examples/after -o examples/after.snapshot.json
python -m treeledger diff examples/before.snapshot.json examples/after.snapshot.json
python -m treeledger diff examples/before.snapshot.json examples/after.snapshot.json --format markdown -o examples/changes.md
python -m treeledger diff examples/before.snapshot.json examples/after.snapshot.json --format json -o examples/changes.json
```

每条 `diff` 命令预期返回 `1`，表示检测到差异。结果为新增、删除、修改、移动、保持不变各一个文件。
Each `diff` exits 1 as expected: one addition, removal, modification, move candidate and unchanged file.

在 Windows 上重建示例时，`.gitattributes` 会让示例正文保留 LF 换行，以便哈希与报告跨平台一致。
`.gitattributes` keeps fixture text at LF so hashes and reports are reproducible on Windows too.
