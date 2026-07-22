# Chat2Work

> 群聊记录 → 任务驱动工作空间 的 Claude Code / WorkBuddy Skill

把散落在微信群/QQ群里的课程设计资料，自动整理成任务驱动的树形工作目录，或把某个发言者蒸馏成可安装的人物画像。

## 快速开始

```bash
# MCP 自动采集（推荐）
python chat2work/scripts/mcp_fetcher.py --name "课程设计群" --limit 500 -o messages.json

# 或手动导出文件
python chat2work/scripts/parser.py chat.txt -o messages.json
```

安装和使用详见 **[chat2work/README.md](chat2work/README.md)**

## 两种模式

| 模式 | 输入 | 输出 |
|------|------|------|
| **course-maker** | 课程群聊记录 | 树形工作目录 |
| **person-distiller** | 群聊 + 目标人名 | SOUL.md 人物画像（6层递进人格结构） |

## 核心能力

- **MCP 自动采集** — 直接从本机微信读取数据，无需手动导出
- **6 层人物蒸馏** — 从价值观底色到红线避坑的递进人格结构，输出可直接安装为 Claude Code expert
- **规则+AI 混合提取** — 链接/文件/日期规则保证不丢，LLM 负责语义理解
- **provenance 溯源** — 所有内容可追溯到原始聊天消息

---

详细文档、使用流程、配置指南见 [chat2work/README.md](chat2work/README.md)
