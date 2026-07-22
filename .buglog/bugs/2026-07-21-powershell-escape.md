---
id: BUG-003
title: PowerShell 环境变量语法在 Bash 中转义失败
status: open
severity: minor
source: ai-observed
reported_at: 2026-07-21T22:14:00
---

## PowerShell 环境变量语法在 Bash 中转义失败

### 现象
第一次尝试用 PowerShell 运行 Python 并设置 UTF-8 编码：
```bash
powershell.exe -Command "$env:PYTHONIOENCODING='utf-8'; ..."
```
报错：`无法将"$env:PYTHONIOENCODING=utf-8"识别为 cmdlet`。原因是 Bash 中 `$` 会被 Bash 解析为变量引用，需要用 `\$` 转义。

### 根因分析
Claude Code 的 Shell 是 Git Bash，调用 PowerShell 时命令字符串先经过 Bash 解析，`$env:` 中的 `$` 被 Bash 吞掉，导致 PowerShell 收到的是无意义的字符串。

### 修复过程
改用 `\$env:PYTHONIOENCODING='utf-8'` 后成功。

### 经验教训
1. 从 Git Bash 调用 PowerShell 时，所有 PowerShell 变量语法 `$xxx` 必须转义为 `\$xxx`
2. 更好的做法是用 `-File` 参数传递 .ps1 脚本，避免复杂的内联转义
