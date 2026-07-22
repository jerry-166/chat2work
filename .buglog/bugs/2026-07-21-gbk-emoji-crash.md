---
id: BUG-002
title: mcp_fetcher.py 在 Windows GBK 终端下因 emoji 崩溃
status: open
severity: major
source: ai-observed
reported_at: 2026-07-21T22:12:00
---

## mcp_fetcher.py 在 Windows GBK 终端下因 emoji 崩溃

### 现象
运行 `python scripts/mcp_fetcher.py --save-config --token "..."` 时报错：
```
UnicodeEncodeError: 'gbk' codec can't encode character '✅' in position 0: illegal multibyte sequence
```
脚本在第 567 行 `print(f"✅ 配置已保存到: {path}")` 处崩溃退出。

### 根因分析
Windows 终端默认使用 GBK 编码（代码页 936），而脚本中使用了 ✅、❌、⚠️、🎉 等 emoji 字符。Python 的 `print()` 函数在向 GBK 终端输出时无法编码这些字符，抛出 `UnicodeEncodeError`。

### 修复过程
临时绕过：通过 PowerShell 设置 `PYTHONIOENCODING=utf-8` 后运行。

正确修复方案（待实施）：
1. 在脚本入口处添加 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` 和 `sys.stderr.reconfigure(encoding='utf-8', errors='replace')`
2. 或者将所有 emoji 替换为 ASCII 等价符号（[OK]、[FAIL]、[WARN] 等）

### 经验教训
1. 面向 Windows 用户的 CLI 工具不应在 print 中直接使用 emoji，或必须强制设置 UTF-8 输出编码
2. 脚本入口处统一设置 stdout/stderr 编码是最可靠的做法
