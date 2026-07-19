---
name: chat2work
description: 群聊记录转任务驱动工作空间的助手。输入 WechatDataAnalysis/QQ导出工具产出的 txt/json 聊天记录，自动构建树形工作目录或人物画像。当用户说"整理群聊/课程设计资料/蒸馏某人/聊天记录转工作目录"时激活。
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

## 三种模式

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

### 3. knowledge-extractor（v2，暂未实现）
输入：任意群聊
输出：knowledge-index.md 知识点索引

## 完整工作流（宿主 AI 执行时遵循）

收到 `/chat2work [mode] <chat_file> [--target name]` 后：

1. **解析输入**：调用 `python scripts/parser.py <chat_file>` 得到 `messages.json`
   - parser 自动嗅探格式（txt/json），归一化为统一 Message 结构
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

## 边界与错误处理

- 输入文件格式无法识别 → 报错并提示支持的格式
- 聊天记录 < 5 条 → 报错"消息太少，无法蒸馏"
- LLM 输出非合法 JSON → 重试一次，仍失败则保留原始输出到 `_debug/`
- 目标目录已存在 → 询问：覆盖 / 合并 / 重命名
- `--target` 指定的人不存在 → 列出所有 sender 让用户重选
- 解压资料包失败 → 跳过，记录到 `_debug/unzip_errors.log`

## 不做的事

- 不碰微信/QQ 数据库解密（用 WechatDataAnalysis 等工具的输出作输入）
- 不写 llm_client（宿主即模型）
- 不自动清理聊天记录（只提示用户自行处理）
- 不弹窗（只用终端文本反馈）

## 扩展新场景

在 `prompts/` 加一个 `<scene-name>.md`，遵循四段式结构即可。无需改代码。router.py 的关键词表可按需补充。
