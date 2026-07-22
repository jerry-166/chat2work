---
id: BUG-001
title: Git Bash 下 Python 命令返回 exit code 49 且无任何输出
status: open
severity: major
source: ai-observed
reported_at: 2026-07-21T22:10:00
---

## Git Bash 下 Python 命令返回 exit code 49 且无任何输出

### 现象
在 Git Bash 环境中运行 `python` 命令（无论是直接运行还是带参数），总是返回 exit code 49，没有任何 stdout 也没有 stderr 输出。反复尝试 `python --version`、`python -c "print('hello')"` 等均无输出。

### 根因分析
Git Bash 中的 `python` 指向 Windows Store 的 stub（`C:\Users\ASUS\AppData\Local\Microsoft\WindowsApps\python.exe`），实际未安装真正的 Python。但更关键的是，Claude Code 的 PostUseFailure hook 可能拦截了 exit code 49 的命令，导致即使有错误输出也被吞掉。最终通过 `powershell.exe -Command "python --version"` 确认 Python 3.13.5 是存在的。

### 修复过程
未修复。临时绕过方案：使用 `powershell.exe -Command "$env:PYTHONIOENCODING='utf-8'; python ..."` 来运行 Python 脚本。

### 经验教训
1. Claude Code 在 Git Bash 中执行 Python 命令时，如果 exit code 不为 0 且无输出，应立即尝试通过 PowerShell/cmd.exe 替代执行，而不是反复重试相同命令
2. `where python` 找到的 WindowsApps stub 不代表 Python 已安装，需要用 `powershell.exe -Command "python --version"` 验证
