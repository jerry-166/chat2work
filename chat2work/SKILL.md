---
name: chat2work
description: 群聊记录转任务驱动工作空间的助手。输入微信/QQ群聊记录（支持MCP自动采集或手动导出txt/json），自动构建树形工作目录或人物画像。当用户说"整理群聊/课程设计资料/蒸馏某人/聊天记录转工作目录"时激活。
license: MIT
---

# Chat2Work — 群聊记录转工作空间

把散落在微信群/QQ群里的课程设计资料，自动整理成任务驱动的树形工作目录，或把某个发言者蒸馏成可安装的人物画像。

## 何时使用

触发词（任一命中即激活）：
- "整理这个群聊记录" / "把聊天记录转成工作目录"
- "课程设计资料太乱了" / "老师发的资料扒不出来"
- "蒸馏张老师" / "把 XX 老师的知识提炼出来"
- `/chat2work` 命令

## 两种数据获取方式

### 🚀 方式一：MCP 自动采集（推荐）

如果本机安装了 **WeChatDataAnalysis** 并开启了 MCP 服务，chat2work 可以**直接从微信读取数据**，不需要手动导出任何文件。

**首次使用请先配置**：详细步骤见 [MCP_SETUP.md](MCP_SETUP.md)

**激活时自动检测 MCP**：
1. 运行 `python scripts/mcp_fetcher.py --check` 检测 MCP 状态
2. 如果可用 → 走 MCP 自动采集流程（见下方工作流 A）
3. 如果不可用 → 提示用户配置 MCP，或走手动导出流程（见下方工作流 B）

**MCP 可用时的功能**：
- 列出最近会话
- 模糊搜索联系人/群聊
- 拉取指定会话消息（自动分页）
- 消息类型完整识别（text/link/image/file/voice/quote/emoji/system）
- 朋友圈数据读取
- 统计分析

### 📄 方式二：手动导出文件

如果没有配置 MCP，使用传统方式：先用 WechatDataAnalysis / qq-chat-exporter 导出聊天记录文件，再喂给 chat2work。

支持的导出格式：
- **WechatDataAnalysis**（微信）：`.json`（推荐，字段最完整） / `.txt` / `.html`
- **qq-chat-exporter**（QQ）：`.json`

## 两种模式

### 1. course-maker（默认）
输入：课程群聊记录
输出：树形工作目录，可直接给 Claude Code/WorkBuddy 进去工作
```
课程设计-XXX/
├── 00_README.md
├── 00_文件信息整理.md        自动生成的文件导航
├── 00_进度看板.md            todo + deadline 倒计时
├── 01_任务说明/
│   ├── 实验任务书.md        带 [src:msg#123] 溯源标签
│   └── 评分标准.md
├── 02_参考资料/
│   ├── 链接库.md            每条链接带 url+sender+time+why
│   ├── 设计参考资料大全.md
│   └── 原始资料包/          老师发的压缩包解压后原样保留
├── 03_我的实现/             你的工作区
├── 04_提交/
└── _provenance/             隐藏目录，消息→文件映射
```

### 2. person-distiller
输入：群聊记录 + 目标人物名（`--target "张老师"`）
输出：SOUL.md 人物画像文件，可安装为 Claude Code expert/skill
提取：说话风格、知识领域、决策模式、常用参考


## 完整工作流

### 工作流 A：MCP 自动采集（推荐）

用户说"整理 XX 群聊"或"蒸馏 XX 群里的张老师"时：

1. **检测 MCP 可用性**：
   ```bash
   python scripts/mcp_fetcher.py --check
   ```
   - ✅ 可用 → 继续步骤 2
   - ❌ 不可用 → 跳转到工作流 B（手动导出），并提示用户可以配置 MCP

2. **搜索/确认目标会话**：
   - 如果用户说了群名/人名 → 用 `--search` 搜索并确认
   - 如果不确定 → 用 `--list` 列出最近会话让用户选

3. **拉取消息**：
   ```bash
   # 用名字自动匹配
   python scripts/mcp_fetcher.py --name "课程设计群" --limit 500 -o messages.json

   # 或用会话 ID 精确拉取
   python scripts/mcp_fetcher.py --session "123456789@chatroom" --limit 1000 -o messages.json
   ```

4. **后续步骤与工作流 B 相同**（场景路由 → 规则提取 → LLM 处理 → 实体化输出）

### 工作流 B：手动导出文件

用户提供了导出的聊天记录文件时：

1. **解析输入**：调用 `python scripts/parser.py <chat_file>` 得到 `messages.json`
   - parser 自动嗅探格式（txt/json/html），归一化为统一 Message 结构
   - WechatDataAnalysis 的 JSON 取 senderDisplayName 作真名，wxid 保留到 sender_id

2. **场景路由**：调用 `python scripts/router.py messages.json [--mode course|distill] [--target name]`
   - --mode 由用户意图决定，不猜测聊天内容
   - 未指定时默认 course-maker；distill 必须显式 --mode distill
   - 输出 scene.json

3. **加载 prompt 模板**：读取 `prompts/<scene>.md`，按模板四段式（Role/Extraction Rules/Output Format/Edge Cases）

4. **规则提取客观字段**：调用 `python scripts/extractor.py messages.json -o extracted.json`
   - 纯规则全量抽取链接/文件/提取码/日期/会议号，100% 不丢（LLM 自由扫描会漏抽，规则保证不丢）
   - 产出的 extracted.json 喂给 LLM 作输入，LLM 不再自己扫链接，只做语义标注（why/title）

5. **LLM 处理**：把 messages.json + extracted.json + prompt 模板 一起作为输入，由宿主 AI（你）执行提取
   - course-maker：refs 字段的 url/extract_code/src_msg 直接从 extracted.links 取，LLM 只补 why/title；输出目录树 JSON（含 tasks/refs/deadline/dir_tree）
   - person-distiller：输出 SOUL.md 内容

6. **实体化输出**：调用 `python scripts/builder.py <llm_output.json> --extracted-file extracted.json [--target-dir .]`
   - builder 用 jinja2 渲染 templates/ 下的模板
   - 链接库以 extracted.links 为主表（规则保证不丢），llm_output.refs 只贡献语义字段
   - 创建目录、写文件、生成 _provenance/msg-to-file.json
   - 产物落到用户当前工作目录（不是 skill 目录）

7. **收尾提示**：打印一句
   > 搞定啦~ 原聊天记录文件你自己看着删哦，我怕删错~

## MCP 配置引导话术

当检测到 MCP 不可用时，友好地告诉用户：

> 检测到本机没有启用 WeChatDataAnalysis MCP 服务。
>
> **两种选择：**
> 1. **配置 MCP（推荐）** — 以后直接从微信读数据，不用手动导出
>    - 下载 WeChatDataAnalysis：https://wechat-data-analysis.com/
>    - 安装后打开 → 设置 → MCP → 开启服务 → 复制 Token
>    - 然后运行：`python scripts/mcp_fetcher.py --save-config --token "你的Token"`
>    - 详细指南见 MCP_SETUP.md
>
> 2. **手动导出** — 先用 WechatDataAnalysis 导出聊天记录为 JSON/TXT 文件
>    - 把导出的文件路径告诉我，我直接处理

## 边界与错误处理

- 输入文件格式无法识别 → 报错并提示支持的格式
- 聊天记录 < 5 条 → 报错"消息太少，无法蒸馏"
- LLM 输出非合法 JSON → 重试一次，仍失败则保留原始输出到 `_debug/`
- 目标目录已存在 → 询问：覆盖 / 合并 / 重命名
- `--target` 指定的人不存在 → 列出所有 sender 让用户重选
- 解压资料包失败 → 跳过，记录到 `_debug/unzip_errors.log`
- MCP 连接失败 → 降级到手动导出模式，并提示配置方法

## 不做的事

- 不碰微信/QQ 数据库解密（通过 WeChatDataAnalysis MCP 或导出文件获取数据）
- 不写 llm_client（宿主即模型）
- 不自动清理聊天记录（只提示用户自行处理）
- 不弹窗（只用终端文本反馈）

## 扩展新场景

在 `prompts/` 加一个 `<scene-name>.md`，遵循四段式结构即可。无需改代码。router.py 的关键词表可按需补充。

## 相关文件

- [MCP_SETUP.md](MCP_SETUP.md) — MCP 详细配置指南（下载、安装、Token 获取、验证）
- [README.md](README.md) — 项目说明和安装指南
- `scripts/mcp_fetcher.py` — MCP 连接器（拉取消息 → 转 chat2work 格式）
- `scripts/parser.py` — 传统文件解析器（txt/json/html → messages.json）
