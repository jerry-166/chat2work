# Chat2Work

> 群聊记录 → 任务驱动工作空间 的 Claude Code / WorkBuddy Skill

把散落在微信群/QQ群里的课程设计资料，自动整理成任务驱动的树形工作目录，或把某个发言者蒸馏成可安装的人物画像。

## ✨ 新功能：MCP 自动采集

**不需要手动导出聊天记录了！** 配置 WeChatDataAnalysis MCP 后，chat2work 可以直接从本机微信读取数据。

- 🚀 一键拉取群聊消息，秒级响应
- 🔍 模糊搜索联系人/群聊
- 📸 朋友圈数据读取
- 📊 统计分析和年度报告

**快速开始：**
```bash
# 1. 检测 MCP 是否可用
python scripts/mcp_fetcher.py --check

# 2. 如果不可用，按 MCP_SETUP.md 配置
# 3. 保存配置（一次配置永久生效）
python scripts/mcp_fetcher.py --save-config --token "你的Token"

# 4. 列出最近会话
python scripts/mcp_fetcher.py --list

# 5. 拉取某个群的消息
python scripts/mcp_fetcher.py --name "课程设计群" --limit 500 -o messages.json
```

详细配置指南 → [MCP_SETUP.md](MCP_SETUP.md)

---

## 为什么需要这个

计算机专业学生在课程设计等开放性实践课中，老师在微信群/QQ群散落发布资料：
- 语言指示（"下周三交实验报告"）
- 网页链接（公众号文章、GitHub 仓库、Wiki）
- 资料包（压缩包、PDF、docx）
- 代码包（参考实现、示例工程）

这些信息碎片化、易丢失、难检索。手工整理成工作目录耗时且易漏。

Chat2Work 把"消息→结构化任务工作目录"这一步自动化，填补了市面工具的空白（现有工具都只做到"摘要"）。

## 工作原理

```
微信消息 (MCP 自动采集)  或  聊天记录文件 (txt/json/html)
    ↓ mcp_fetcher.py / parser.py 归一化
统一消息结构 (messages.json)
    ↓ router.py 场景路由
course-maker | person-distiller
    ↓ 加载 prompts/*.md 模板
    ↓ LLM 提取（由 Claude Code/WorkBuddy 宿主执行）
目录树 JSON / SOUL.md 内容
    ↓ builder.py 实体化
工作目录 / 人物画像文件
```

## 安装

### 方式一：作为 Claude Code / WorkBuddy Skill

```bash
# 把 chat2work/ 目录复制到 skills 目录
cp -r chat2work ~/.workbuddy/skills/

# 或软链接
ln -s /path/to/chat2work ~/.workbuddy/skills/chat2work
```

然后在 Claude Code / WorkBuddy 里说：
> /chat2work course chat.json

或自然语言：
> 帮我整理这个群聊记录，转成工作目录

### 方式二：作为独立 Python 脚本

```bash
cd chat2work

# 方式 A：MCP 自动采集（推荐）
python scripts/mcp_fetcher.py --name "课程设计群" --limit 500 -o messages.json

# 方式 B：手动导出文件
python scripts/parser.py chat.txt -o messages.json

# 后续流程相同
python scripts/router.py messages.json --mode course -o scene.json
# （由宿主 AI 按 prompts/course-maker.md 处理 messages.json，产出 llm_output.json）
python scripts/builder.py llm_output.json --target-dir .
```

## 使用流程

### 快速开始（MCP 自动采集）

1. **配置 MCP**（只需一次）：
   - 下载 WeChatDataAnalysis：https://wechat-data-analysis.com/
   - 安装 → 设置 → MCP → 开启服务 → 复制 Token
   - 运行：`python scripts/mcp_fetcher.py --save-config --token "你的Token"`
   - 详细步骤见 [MCP_SETUP.md](MCP_SETUP.md)

2. **使用**：
   ```
   /chat2work course "课程设计群"
   /chat2work distill "工作群" --target "王总"
   ```

### 传统方式（手动导出）

#### Step 1: 导出聊天记录

用以下任一工具导出微信/QQ 群聊：
- **WechatDataAnalysis** — 微信（主要数据源，推荐导出 `.json`，字段最规整，含真名/群昵称）
- **qq-chat-exporter**（https://github.com/shuakami/qq-chat-exporter）— QQ

WechatDataAnalysis 可导出 txt/json/html 三种格式，本 skill 优先支持 **json**（senderDisplayName 真名、renderType 消息类型、文件路径都齐全），txt 次之，html 解析尚未完整适配。

#### Step 2: 运行 Chat2Work

在 Claude Code / WorkBuddy 里：
```
/chat2work course chat.json
```

或蒸馏某个人物：
```
/chat2work distill chat.json --target "张老师"
```

#### Step 3: 查看产物

- **course-maker** 模式：当前目录下生成 `课程设计-XXX/` 工作目录
- **person-distiller** 模式：当前目录下生成 `so-张老师.md` 人物画像

## 三种模式

| 模式 | 输入 | 输出 | 用途 |
|------|------|------|------|
| course-maker | 课程群聊记录 | 树形工作目录 | Claude Code/WorkBuddy 直接进工作 |
| person-distiller | 群聊 + 目标人名 | SOUL.md 人物画像 | 安装为 expert/skill |
| knowledge-extractor | 任意群聊 | knowledge-index.md | v2，暂未实现 |

## course-maker 输出结构

```
课程设计-XXX/
├── 00_README.md                  项目总览
├── 00_文件信息整理.md            自动生成的文件导航
├── 00_进度看板.md                todo + deadline 倒计时
├── 01_任务说明/
│   ├── 实验任务书.md            带 [src:msg#123] 溯源标签
│   └── 评分标准.md
├── 02_参考资料/
│   ├── 链接库.md                每条链接带 url+sender+time+why
│   ├── 设计参考资料大全.md
│   └── 原始资料包/              老师发的压缩包解压后原样保留
├── 03_我的实现/                 你的工作区
├── 04_提交/                     最终交付物
└── _provenance/                 隐藏目录，消息→文件映射
    └── msg-to-file.json
```

## 核心特性

- **provenance 溯源**：任何文件里的 `[src:msg#xxx]` 标签都可在 `_provenance/msg-to-file.json` 反查到原始聊天消息
- **自动维护的文件导航**：`00_文件信息整理.md` 由 builder 自动生成，重新运行即刷新
- **deadline 倒计时**：`00_进度看板.md` 自动计算剩余天数
- **多场景 prompt 模板**：在 `prompts/` 加一个 `.md` 即可扩展新场景，零代码改动
- **MCP 自动采集**：直接从本机微信读取数据，无需手动导出（需 WeChatDataAnalysis）

## 依赖

- Python 3.10+
- （可选）jinja2 — 模板渲染。未安装时退化到简单占位符替换
- （可选）beautifulsoup4 — 解析 HTML 格式聊天记录

```bash
pip install jinja2 beautifulsoup4
```

## MCP 配置方式

详细配置指南见 [MCP_SETUP.md](MCP_SETUP.md)

### 配置优先级

从高到低：
1. 命令行参数 `--mcp-url` / `--token`
2. 环境变量 `CHAT2WORK_MCP_URL` / `CHAT2WORK_MCP_TOKEN`
3. 用户目录配置文件 `~/.chat2work/mcp_config.json`
4. 工作目录配置文件 `./.chat2work/mcp_config.json`

### 常用命令

```bash
# 检测 MCP 状态
python scripts/mcp_fetcher.py --check

# 保存配置（推荐）
python scripts/mcp_fetcher.py --save-config --token "你的Token"

# 列出最近会话
python scripts/mcp_fetcher.py --list

# 搜索会话
python scripts/mcp_fetcher.py --search "张老师"

# 按名字拉取消息
python scripts/mcp_fetcher.py --name "课程设计群" --limit 500 -o messages.json

# 按会话 ID 拉取
python scripts/mcp_fetcher.py --session "123456789@chatroom" --limit 1000 -o messages.json
```

## 扩展新场景

1. 在 `prompts/` 新建 `<scene-name>.md`，遵循四段式结构：
   - Role（角色）
   - Extraction Rules（提取规则）
   - Output Format（输出格式）
   - Edge Cases（边界处理）
2. 在 `templates/` 新建对应输出模板目录（如需要）
3. 在 `router.py` 的关键词表里补充该场景的识别词
4. 在 `builder.py` 补充该模式的实体化逻辑

## 项目结构

```
chat2work/
├── SKILL.md                        入口文件
├── README.md                       本文件
├── MCP_SETUP.md                    MCP 配置详细指南
├── scripts/
│   ├── mcp_fetcher.py             MCP 连接器（拉取消息 → 转 chat2work 格式）
│   ├── parser.py                   消息归一化（txt/json/html → messages.json）
│   ├── router.py                   场景路由
│   ├── extractor.py                规则提取（链接/文件/日期/提取码）
│   └── builder.py                  目录/文件实体化
├── prompts/
│   ├── course-maker.md             课程设计场景 prompt 模板
│   ├── person-distiller.md         人物蒸馏场景 prompt 模板
│   └── knowledge-extractor.md      （v2 占位）
└── templates/
    ├── course-workspace/           course-maker 输出模板
    │   ├── 00_README.md.tmpl
    │   ├── 00_文件信息整理.md.tmpl
    │   ├── 00_进度看板.md.tmpl
    │   ├── 01_任务说明/
    │   │   ├── 实验任务书.md.tmpl
    │   │   └── 评分标准.md.tmpl
    │   └── 02_参考资料/
    │       ├── 链接库.md.tmpl
    │       └── 设计参考资料大全.md.tmpl
    └── persona/
        └── SOUL.md.tmpl            person-distiller 输出模板
```

## 不做的事（YAGNI）

- 不碰微信/QQ 数据库解密（通过 WeChatDataAnalysis MCP 或导出文件获取数据）
- 不写 llm_client（宿主即模型）
- 不自动清理聊天记录（只提示用户自行处理）
- 不弹窗（只用终端文本反馈）

## 开源协议

MIT License

## 致谢

- **WeChatDataAnalysis** — 微信聊天记录分析工具 + MCP 服务
- [qq-chat-exporter](https://github.com/shuakami/qq-chat-exporter) — QQ 数据源
- [colleague-skill](https://github.com/titanwings/colleague-skill) — 蒸馏思路参考
