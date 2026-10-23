# TreeLedger

[![CI](https://github.com/miaomiao-lanmiao/treeledger/actions/workflows/ci.yml/badge.svg)](https://github.com/miaomiao-lanmiao/treeledger/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**给文件夹记一本内容账本。** 离线生成 SHA-256 快照，核对备份、迁移和交付前后的文件变化。

[English](README.en.md) · [可运行示例](examples/README.md) · [快照格式](docs/format.md) · [下载](https://github.com/miaomiao-lanmiao/treeledger/releases)

```text
Changes detected
1 added, 1 removed, 1 modified, 1 moved, 1 unchanged
+ "todo.txt" (29 bytes)
- "old-note.txt" (26 bytes)
~ "config.json" (20 -> 20 bytes)
> "docs/intro.txt" -> "docs/guide.txt" (35 bytes)
```

## 适合做什么

- **备份验收**：保存原目录快照，再检查备份目录的内容是否一致。
- **迁移核对**：不依赖修改时间，也能发现同样大小但内容不同的文件。
- **交付清单**：输出 JSON 供脚本处理，或生成 Markdown 差异报告。
- **移动线索**：仅在消失与新增文件之间，内容和大小各有唯一匹配时推断移动；存在歧义则保留为新增、删除。

Python 标准库实现，**零运行依赖**。运行时不访问网络。Windows、macOS、Linux 均有自动化测试配置。

## 安装

需要 Python 3.10 或更新版本。当前发布在 GitHub，尚未发布到 PyPI。

```sh
git clone https://github.com/miaomiao-lanmiao/treeledger.git
cd treeledger
python -m pip install .
treeledger --version
```

也可以从 [Releases](https://github.com/miaomiao-lanmiao/treeledger/releases) 下载 wheel，随后离线安装：

```sh
python -m pip install --no-index treeledger-0.1.0-py3-none-any.whl
```

源码无需安装即可通过 `python -m treeledger` 运行；构建和源码安装需要 setuptools，下载构建工具时可能访问网络。

## 三条命令

```sh
# 1. 给目录生成快照，建议保存在被扫描目录之外
treeledger snapshot ./project -o baseline.json

# 2. 用保存的忽略规则检查当前目录，也可以换成备份目录
treeledger check baseline.json ./project

# 3. 比较两份快照，无需保留原始目录
treeledger snapshot ./project -o current.json
treeledger diff baseline.json current.json --format markdown -o changes.md
```

`snapshot` 不指定 `-o` 时向标准输出写 JSON。`check` 和 `diff` 支持 `--format text`（默认）、`json`、`markdown`。

| 退出码 | 含义 |
| --- | --- |
| `0` | 快照创建成功，或比较没有差异 |
| `1` | 检测到文件差异或排除规则变化 |
| `2` | 参数、输入格式或文件读取/写入错误 |

因此，`diff` 返回 `1` 表示成功发现差异，并不表示程序崩溃。

## 排除不需要的文件

默认跳过 `.git/`、`.venv/`、`venv/`、`node_modules/`、`__pycache__/`、`.pytest_cache/`，这些目录名在任意层级生效。

在被扫描目录的根部创建 `.treeledgerignore`：

```gitignore
# 注释和空行被忽略
*.tmp
*.log
cache/
/build/
private/*.key
```

也可以重复传入 `--exclude`：

```sh
treeledger snapshot ./project --exclude '*.zip' --exclude 'cache/' -o baseline.json
```

这些是简单、区分大小写的 glob 规则，**不是完整的 gitignore 语法**：

- 无 `/` 的规则匹配任意层级的名称；以 `/` 开头的规则从根目录匹配。
- 其他包含 `/` 的规则也相对根目录匹配；末尾 `/` 表示只匹配目录及其内容。
- 支持 `*`、`?`、`[abc]`；使用 Python `fnmatch` 语义，`*` 可以跨越 `/`，`**` 没有特殊含义。
- 不支持 `!` 反向包含，遇到它会报错。空白边缘和注释行在忽略文件中会被去掉。
- `.treeledgerignore` 本身作为普通文件进入快照。`check` 使用快照保存的规则，不重新加载当前忽略文件。

如果快照输出文件位于扫描目录内，该文件会自动排除；保存的规则包含这条排除项。其他快照与报告不会自动排除，建议统一保存在目录之外。两份快照排除规则不同会明确提示，并返回 `1`。

## 数据与边界

- 快照只记录相对路径、文件字节数、SHA-256 和排除规则；不记录文件正文、根目录绝对路径或生成时间。相同内容与规则产生相同快照。
- 文件名和哈希仍可能透露信息，请按你对目录的保密要求保管快照。工具不上传它们。
- 跳过符号链接、Windows reparse point（含目录联接）及特殊文件，并在标准错误输出汇总提示；这些对象的变化不计入比较。
- 不记录空目录、权限、修改时间、扩展属性或文件系统专有数据。文件路径比较区分大小写；不接受 `:`、反斜杠及非规范的相对路径。
- 采用 1 MiB 分块读取。普通读取错误或检测到文件在哈希过程中变化时，操作失败，保留已有输出文件。
- 每个文件读取前后会核对状态，但扫描不是文件系统级原子快照，也不是对恶意并发修改的安全隔离。扫描前请暂停写入或使用文件系统快照。
- 移动是根据内容推断的线索；工具不复制、恢复或删除源文件。快照也没有数字签名。

## 开发

```sh
python -m unittest discover -s tests -v
python -m pip wheel --no-deps . --wheel-dir dist
```

测试覆盖内容变化、移动歧义、忽略规则、非法快照、流式读取、并发写入、原子报告替换以及 CLI 退出码。平台不支持的符号链接/FIFO/目录联接测试会说明原因并跳过；CI 在三个操作系统、Python 3.10 与 3.13 上运行。

MIT License。欢迎通过 [Issues](https://github.com/miaomiao-lanmiao/treeledger/issues) 提交问题；贡献方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。
