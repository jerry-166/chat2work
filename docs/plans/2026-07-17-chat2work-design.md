# Chat2Work 设计文档

> 群聊记录 → 任务驱动工作空间 的 Claude Code / WorkBuddy Skill
> 创建日期：2026-07-17
> 状态：brainstorming 完成，待进入实现阶段

---

## 一、项目背景

### 1.1 痛点

计算机专业学生在课程设计等开放性实践课程中，老师在微信群/QQ群散落发布资料：
- 语言指示（"下周三交实验报告"）
- 网页链接（公众号文章、GitHub 仓库、Wiki）
- 资料包（压缩包、PDF、docx）
- 代码包（参考实现、示例工程）

这些信息碎片化、易丢失、难检索。手工整理成工作目录耗时且易漏。

### 1.2 现有工具调研结论

三轮调研覆盖三个赛道，结论是 Chat2Work 有新作必要，但要定位准确：

| 赛道 | 代表项目 | 已覆盖 | Chat2Work 关系 |
|------|----------|--------|----------------|
| 消息提取（红海） | WeChatMsg/留痕、PyWxDump、qq-chat-exporter | 数据库解密+导出 txt/json/html | **作为数据源，不重做** |
| AI 摘要（占位） | wechat-digest、WeChat Radar、wechatNotice | 消息→摘要.md/PDF | **输出形态不同（目录树≠摘要）** |
| 蒸馏 Skills（爆发中） | colleague-skill(11k★)、nuwa-skill(4.3k★) | 聊天记录→人物 SOUL.md | **person-distiller 模式借鉴** |

**关键空白点**：现有工具输出都是"文档"（摘要/PDF/HTML），无人做"消息→结构化任务工作目录"的跃迁。Chat2Work 的差异化正在于此。

### 1.3 项目目标

做一个开源 Claude Code / WorkBuddy Skill：
- 输入：WeChatMsg / qq-chat-exporter 产出的 txt/json/html 聊天记录
- 输出：任务驱动的树形工作目录（course-maker）或人物画像文件（person-distiller）
- 不碰微信/QQ 解密，专注上层智能
- 既作求职亮点（技术栈完整、故事性强），也为计算机学子提效

---

## 二、设计决策汇总

| # | 决策点 | 结论 | 理由 |
|---|--------|------|------|
| ① | 数据源边界 | 只做上层整理，输入 txt/json/html | 解密易失效、维护重，已有成熟工具 |
| ② | 输出形态 | Claude Code / WorkBuddy Skill（含脚本） | 蹭 skill 生态热度，求职故事最强 |
| ③ | LLM 调用 | 不写 llm_client，宿主即模型 | Claude Code/WorkBuddy 自带模型 |
| ④ | 场景范围 | 多场景分支 prompt 模板 | 一套引擎多种用途 |
| ⑤ | chat-cleaner | 砍掉，改为完成后一句话提示 | 自动清理权限过大、风险高 |
| ⑥ | 输出位置 | 用户当前工作目录，不在 skill 目录内 | skill 是只读工具包 |
| ⑦ | v1 范围 | course-maker + person-distiller | knowledge-extractor 作追加持分项 |

---

## 三、整体架构

```
┌─────────────────────────────────────────────────────────────┐
│  Input: chat.txt / chat.json / chat.html                    │
│  (from WeChatMsg / qq-chat-exporter)                        │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  scripts/parser.py  →  Unified Message Struct               │
│  归一化不同来源的消息格式                                    │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  scripts/router.py  →  Scene Detection                     │
│  自动检测场景 或 读取 --mode 标志                            │
└─────────┬───────────────────────────────────┬───────────────┘
          ▼ course                           ▼ distill
┌──────────────────────┐              ┌──────────────────────┐
│ prompts/             │              │ prompts/             │
│ course-maker.md      │              │ person-distiller.md  │
│                      │              │                      │
│ 提取：任务名/deadline │              │ 提取：说话风格/       │
│ 参考资料/代码包/      │              │ 知识领域/决策模式/    │
│ 提交方式/评分标准     │              │ 常用参考              │
│                      │              │                      │
│ 输出：JSON 树结构     │              │ 输出：SOUL.md         │
└──────────┬───────────┘              └──────────┬───────────┘
           ▼                                     ▼
┌──────────────────────┐              ┌──────────────────────┐
│ scripts/builder.py   │              │ scripts/builder.py   │
│ 实体化目录树 + 文件   │              │ 写单个 .md 文件       │
│ 落到用户当前工作目录  │              │                      │
└──────────┬───────────┘              └──────────┬───────────┘
           ▼                                     ▼
      工作目录树                              SOUL.md / persona.md
      (给 Claude Code/WorkBuddy 直接进)       (可安装为 expert/skill)

           ┌───────────────────────────────────────┐
           │  收尾提示（所有模式共用）：             │
           │  "Done! The original chat file is      │
           │   yours to delete — I wouldn't dare :)"│
           └───────────────────────────────────────┘
```

---

## 四、Skill 文件结构

```
chat2work/                          (skill 根目录)
├── SKILL.md                        (入口，定义命令/mode/触发词)
├── scripts/
│   ├── parser.py                   (输入归一化)
│   ├── router.py                   (场景路由)
│   └── builder.py                  (目录/文件实体化)
├── prompts/
│   ├── course-maker.md             (课程设计场景 prompt 模板)
│   ├── person-distiller.md         (人物蒸馏场景 prompt 模板)
│   └── knowledge-extractor.md      (知识提取场景 prompt 模板, v2)
├── templates/
│   ├── course-workspace/           (course-maker 输出模板)
│   │   ├── 00_README.md.tmpl
│   │   ├── 00_文件信息整理.md.tmpl
│   │   ├── 00_进度看板.md.tmpl
│   │   ├── 01_任务说明/实验任务书.md.tmpl
│   │   ├── 01_任务说明/评分标准.md.tmpl
│   │   ├── 02_参考资料/链接库.md.tmpl
│   │   └── 02_参考资料/设计参考资料大全.md.tmpl
│   └── persona/                    (person-distiller 输出模板)
│       └── SOUL.md.tmpl
└── README.md                       (用户文档：安装/使用/扩展)
```

**设计要点**：
- 新增场景只需在 `prompts/` 加一个 `.md`，不改代码
- `templates/` 存放输出骨架，`builder.py` 用 jinja2 渲染
- 不含 `outputs/` 目录——产物落到用户当前工作目录

---

## 五、核心数据结构

### 5.1 统一消息结构（parser.py 输出）

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Message:
    sender: str                    # 发送者显示名 "张老师"
    sender_id: Optional[str]       # 原始 ID "wxid_xxx" 或 QQ 号
    time: datetime                 # 消息时间
    content: str                   # 正文（已清洗）
    msg_type: str                  # text | link | file | image | voice | system
    meta: dict = field(default_factory=dict)
    # meta 字段按 msg_type 不同：
    #   link:  {url, title, description}
    #   file:  {filename, size, local_path}
    #   image: {local_path, width, height}
    #   voice: {duration_sec, transcript}  # 转写文本（如有）
    #   system:{action}  # 撤回/入群/拍一拍等

    # 溯源：原始消息在源文件中的位置
    source_line: Optional[int] = None    # 在 chat.txt 的第几行
    source_msg_id: Optional[str] = None  # json 源里的 msgId
```

### 5.2 Parser 支持的输入格式

| 格式 | 来源工具 | parser 实现 |
|------|----------|-------------|
| `.txt` | WeChatMsg 导出 | 正则匹配 `2026-07-10 14:26:23 张老师\n消息内容` |
| `.json` | WeChatMsg / qq-chat-exporter | 按 schema 解析，统一到 Message |
| `.html` | WeChatMsg 导出 | BeautifulSoup 提取，结构同 txt |

parser 自动嗅探格式（看文件扩展名 + 内容首行），用户无需指定。

---

## 六、Prompt 模板设计

### 6.1 模板通用结构

每个 `prompts/*.md` 都遵循四段式：

```markdown
---
mode: course-maker
description: 课程设计场景，从群聊提取任务并构建工作目录
input_schema: messages[]   # 接收 parser 输出的消息数组
output_schema: workspace_tree   # 输出目录树 JSON
---

# Role
你是一位课程设计助教...

# Extraction Rules
1. 任务名：从老师消息中识别明确的任务...
2. Deadline：解析"下周三""7月20日前"等相对时间，转为绝对日期...
3. 参考资料：提取所有 http(s) 链接、附件、压缩包...
...

# Output Format
输出严格 JSON：
{
  "project_name": "...",
  "deadline": "YYYY-MM-DD",
  "tasks": [...],
  "refs": [...],
  "dir_tree": {
    "name": "课程设计-XXX",
    "type": "dir",
    "children": [...]
  }
}

# Edge Cases
- 重复消息：按 (sender, content_hash) 去重
- 时间歧义：相对时间用最新消息时间作基准
- 链接失效：仍收录，标记 [unverified]
- 老师撤回：保留撤回前内容，标记 [recalled]
```

### 6.2 course-maker 提取项

| 提取项 | 用途 | 落到哪个文件 |
|--------|------|--------------|
| 任务名 + 描述 | 项目标识 | 00_README.md, 01_任务说明/实验任务书.md |
| Deadline | 进度追踪 | 00_进度看板.md |
| 参考资料（链接） | 检索 | 02_参考资料/链接库.md |
| 代码包/资料包 | 原始素材 | 02_参考资料/原始资料包/ |
| 提交方式 | 验收 | 01_任务说明/实验任务书.md |
| 评分标准 | 自检 | 01_任务说明/评分标准.md |

### 6.3 person-distiller 提取项

| 提取项 | 用途 |
|--------|------|
| 说话风格 | Persona 还原（语气、口头禅、表达习惯） |
| 知识领域 | 标注最擅长的方向、常引用的书/工具 |
| 决策模式 | 遇到某类问题的处理路径 |
| 常用参考 | 经常推荐的文章/工具/项目 |

输出 SOUL.md 格式（参考 colleague-skill 的两层结构：Work Skill + Persona）。

---

## 七、course-maker 输出模板（基于真实样例改进）

### 7.1 目录树

```
课程设计-<项目名>/
├── 00_README.md                    项目总览，一句话说明+deadline
├── 00_文件信息整理.md              自动生成的文件导航
├── 00_进度看板.md                  todo 清单 + deadline 倒计时
├── 01_任务说明/
│   ├── 实验任务书.md              带 [src:msg#123] 溯源标签
│   └── 评分标准.md
├── 02_参考资料/
│   ├── 链接库.md                  每条链接带 url+sender+time+why
│   ├── 设计参考资料大全.md        综合性参考
│   └── 原始资料包/                老师发的压缩包解压后原样保留
├── 03_我的实现/                   用户工作区，Claude Code/WorkBuddy 直接进
├── 04_提交/                       报告/源码/演示视频
└── _provenance/                   隐藏目录
    └── msg-to-file.json           消息ID → 落到哪个文件的映射
```

### 7.2 关键文件内容示例

**00_文件信息整理.md**（自动生成）：
```markdown
# 文件信息整理

> 由 Chat2Work 自动生成，请勿手动编辑。重新运行 /chat2work 会刷新。

| 文件 | 类型 | 说明 | 来源 |
|------|------|------|------|
| 01_任务说明/实验任务书.md | 任务 | 实验总体要求与步骤 | 张老师 7/10 14:26 [msg#123] |
| 01_任务说明/评分标准.md | 评分 | 100 分制评分量表 | 张老师 7/10 14:30 [msg#125] |
| 02_参考资料/链接库.md | 链接 | 6 条外部链接 | 多人合并 |
| 02_参考资料/原始资料包/WAVEGO_3D_MODEL-main | 代码包 | GitHub 模型仓库 | 张老师 7/10 11:13 [msg#118] |
```

**02_参考资料/链接库.md**（带溯源）：
```markdown
# 链接库

| URL | 标题 | 发送者 | 时间 | 上下文/为什么发 |
|-----|------|--------|------|----------------|
| https://www.waveshare.net/wiki/WAVEGO | WAVEGO Wiki | 张老师 | 2026-07-10 11:13 | 介绍机器狗产品页 [msg#118] |
| https://github.com/arnaucresp0/WAVEGO_3D_MODEL | 3D 模型仓库 | 李同学 | 2026-07-10 13:45 | 分享社区逆向模型 [msg#121] |
```

**00_进度看板.md**：
```markdown
# 进度看板

## Deadline
- **2026-07-25** 实验报告提交（剩余 8 天）

## Todo
- [ ] 实验一：环境与硬件认知
- [ ] 实验二：构建虚拟机器狗
- [ ] 实验三：通信桥接与协议转换
- [ ] 实验四：联调、测试与验收

## 已完成
- [x] 工作目录已由 Chat2Work 自动生成（2026-07-17）
```

### 7.3 provenance（溯源）机制

`_provenance/msg-to-file.json` 示例：
```json
{
  "msg#118": {
    "sender": "张老师",
    "time": "2026-07-10 11:13",
    "content_preview": "这是 WAVEGO 的官方 Wiki...",
    "landed_at": "02_参考资料/链接库.md#row-1"
  },
  "msg#123": {
    "sender": "张老师",
    "time": "2026-07-10 14:26",
    "content_preview": "下周三前交实验报告...",
    "landed_at": "01_任务说明/实验任务书.md#deadline"
  }
}
```

任何文件里的 `[src:msg#123]` 标签都可通过这个映射反查原始消息。

---

## 八、router.py 场景检测

自动检测场景的启发式规则（用户也可用 `--mode` 显式指定）：

| 信号 | course-maker | person-distiller |
|------|--------------|------------------|
| 关键词 | "作业/课程设计/实验/截止/提交/答辩" | "蒸馏/某老师/某同学/风格/决策" |
| `--target` 参数 | 无 | 有（指定人物名） |
| 消息分布 | 多人多话题 | 聚焦某一人发言 |
| 默认 | 命中即用 | 命中即用，否则 fallback 到 course-maker |

---

## 九、错误处理与边界

| 场景 | 处理 |
|------|------|
| 输入文件格式无法识别 | 报错并提示支持的格式 |
| 聊天记录为空或 < 5 条 | 报错"消息太少，无法蒸馏" |
| LLM 输出非合法 JSON | 重试一次，仍失败则保留原始输出到 `_debug/` |
| 目标目录已存在 | 询问：覆盖 / 合并 / 重命名 |
| `--target` 指定的人在聊天中不存在 | 列出所有 sender 让用户重选 |
| 解压资料包失败 | 跳过，记录到 `_debug/unzip_errors.log` |

---

## 十、实现路径

### v1（MVP，2-3 周）
- [ ] SKILL.md + README.md
- [ ] parser.py 支持 txt + json
- [ ] router.py 基础场景检测
- [ ] course-maker.md prompt 模板
- [ ] builder.py 实体化目录树
- [ ] 7 个模板文件（00_/01_/02_）
- [ ] provenance 映射机制
- [ ] 用真实数据（用户 WAVEGO 课程群）测试一轮

### v1.5（1 周）
- [ ] person-distiller.md prompt 模板
- [ ] SOUL.md 输出模板
- [ ] parser.py 补充 html 格式

### v2（按需）
- [ ] knowledge-extractor.md 模板
- [ ] 跨项目资料软链接
- [ ] 用户自定义 prompt 模板加载
- [ ] GUI（如果需要）

### 不做（YAGNI）
- ❌ 微信/QQ 数据库解密
- ❌ llm_client.py（宿主即模型）
- ❌ 自动清理聊天记录
- ❌ 弹窗式收尾提示（只用一句话）

---

## 十一、求职亮点叙事

项目可讲的故事线：
1. **发现问题**：作为计算机学生，课程群里资料散落、整理耗时
2. **市场调研**：发现现有工具都在做"摘要"，没人做"工作目录"
3. **架构决策**：不重复造轮子（用 WeChatMsg 做数据源），专注上层智能
4. **技术创新**：provenance 溯源机制、多场景 prompt 模板、自动维护的文件导航
5. **生态借力**：做成 Claude Code Skill，蹭蒸馏 skill 生态热度
6. **真实验证**：用自己的 WAVEGO 课程设计群聊记录跑了通

技术栈：Python / 数据解析 / LLM prompt 工程 / 文件系统操作 / Skill 生态 / jinja2 模板。

---

## 十二、待确认事项

1. **项目命名**：暂定 `Chat2Work`，是否换更上口的名字？
2. **测试数据**：用户能否提供一份脱敏后的真实课程群聊记录用于开发期测试？
3. **person-distiller 输出**：SOUL.md 是否要做成可直接 `npx skills add` 的格式？还是先做通用 .md，安装步骤手写？
4. **GitHub 仓库**：开源协议选 MIT 还是 Apache 2.0？

---

*设计文档结束。下一步：用户确认后进入实现阶段，建议从 v1 MVP 起步。*
