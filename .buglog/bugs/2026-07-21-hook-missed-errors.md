---
id: BUG-005
title: buglog hook 无法识别 AI 自身操作产生的错误，仅触发于 Bash exit code
status: open
severity: major
source: user-review
reported_at: 2026-07-21T22:20:00
---

## buglog hook 无法识别 AI 自身操作产生的错误，仅触发于 Bash exit code

### 现象
本次会话中出现了 5 个明显的问题（Python exit code 49 静默失败、GBK emoji 崩溃、PowerShell 转义错误、搜索名不匹配等），但 buglog hook 始终报告"当前项目无未修复 bug"。hook 仅在以下两种情况触发：
1. Bash 工具返回非零 exit code 时（PostUseFailure）
2. Write 工具写入文件时（检测到编辑了多个文件）

hook 从不检测 AI 逻辑层面的错误——比如反复重试相同的失败命令、用了错误的转义语法、没有主动建议备选方案等。

### 根因分析
hook 的触发机制过于简单，仅依赖工具返回值（exit code）来判断是否有 bug，无法感知：
1. **重复失败模式**：相同命令连续失败多次应被视为异常
2. **AI 决策错误**：选错了方案、遗漏了明显的信息
3. **用户反馈的隐含 bug**：用户说"还是有问题"时没有主动回溯查找

此外，`bug-state.json` 文件不存在说明 hook 的初始化流程也不完整。

### 修复过程
未修复。当前由用户手动触发 `/buglog add` 来记录。

改进方向：
1. Hook 应检测重复失败模式（同一命令连续失败 >= 2 次）
2. 当用户表达不满（"还是有问题"、"你没有发现"等）时，应触发 AI 回溯本次会话的错误
3. hook 应检查 `bug-state.json` 是否存在，不存在则自动创建

### 经验教训
1. 不能完全依赖自动 hook 来捕获所有 bug，AI 应在每次长对话结束时主动反思是否有遗漏的问题
2. hook 的触发条件需要从"工具失败"扩展到"模式检测"——重复失败、用户负面反馈等
3. `bug-state.json` 等状态文件应该在 hook 初始化时自动创建
