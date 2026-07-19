# 人物蒸馏 Skill 三阶段改进计划

> 项目：`D:\workspace\demo\test_wechat_assistant\chat2work\` 的 person-distiller 模式
> 范围：路径 1（夯实骨架）+ 路径 2（6 层扩层）+ 路径 3（三重验证简化版），6-8 周交付
> 应用场景：A（蒸馏活人）+ D（蒸馏自己）私人使用，最高隐私要求

---

## 0. 现状速览（探索结论）

### 0.1 代码骨架已搭好但未跑通
- `chat2work/scripts/`：parser.py（397 行）、router.py（115 行）、builder.py（390 行）、extractor.py（194 行）—— 共 1096 行
- `chat2work/templates/persona/SOUL.md.tmpl`（137 行 jinja2 模板）已写好但**未被使用**
- `chat2work/prompts/person-distiller.md`（124 行，5 条抽取规则）让 LLM 直接产出 markdown 全文
- `chat2work/tests/test_extractor.py` 是唯一测试（9 个用例）；router/builder/parser 共 0 测试

### 0.2 四个核心问题（已验证）
| # | 问题 | 证据位置 |
|---|---|---|
| 1 | 双轨设计不一致 | `builder.py` L329-344 `build_persona()` 直接 `out_path.write_text(soul_content)`，未调 `render_template`；`SKILL.md` L74却说"builder 用 jinja2 渲染 templates/" |
| 2 | 测试完全空白 | person-distiller 0 测试；router/builder/parser 899 行无测试 |
| 3 | 陈旧产物 | `tests/scene.json` 含 `course_score:17, distill_score:2, course_hits:[...]`，与当前 `--mode` 显式路由哲学冲突 |
| 4 | 缺真实产物 | `tests/` 下无任何 `so-*.md` 样例 |

### 0.3 真实数据与外部参考
- **真实数据**：`weChatDataAnalysis/chat_log/real_test_json/conversations/0001_.../messages.json`，147 条消息，其中 "Yang" 20 条（最活跃发言者），内容覆盖网盘分享、腾讯会议邀请、技术链接、会议录屏——**适合作为路径 1 黄金样例**。
- **WorkBuddy Expert 标准格式**：参考 `C:\Users\ASUS\.workbuddy\plugins\marketplaces\experts\plugins\senior-developer\agents\senior-developer.md`，标准结构为：
  - YAML frontmatter：`name / description / color / emoji / vibe`
  - Identity directive（最高优先级身份指令）
  - Philosophy / Rules / Process / Skills 集成 / Final identity reminder
- **WorkBuddy 自身 SOUL.md**：`~/.workbuddy/SOUL.md`（44 行简洁版，含 Core Truths / Boundaries / Vibe / Continuity），是 workspace 级灵魂文件。

---

## 1. 路径 1：夯实骨架（1-2 周）

### 1.1 双轨问题修复方案

**推荐方案：启用 jinja2 渲染（混合方案）**

理由：
1. SOUL.md 模板已写好且字段设计合理，废弃浪费
2. LLM 直接产 markdown 全文容易字段遗漏、格式漂移、难程序化校验
3. 与 course-maker 模式保持一致（course-maker 也是 LLM 出 JSON + jinja2 渲染）
4. 退化机制已存在（`render_template` 在无 jinja2 时做简单 `{{ var }}` 替换）
5. 路径 2 扩 6 层时，结构化 JSON + 模板渲染远比让 LLM 直接产全文可控

**关键折中**：LLM 输出从"markdown 全文"改为"结构化 JSON"，builder 用 jinja2 渲染。

#### 1.1.1 修改 `prompts/person-distiller.md`
- 删除当前 `# Output Format` 段（让 LLM 直接产 markdown 全文的部分，L47-106）
- 改为要求 LLM 输出严格 JSON，字段对齐 SOUL.md.tmpl 的变量：

```json
{
  "mode": "person-distiller",
  "target_name": "Yang",
  "target_actual_name": "Yang",
  "source_file": "<messages.json 绝对路径>",
  "message_count": 20,
  "time_range_start": "2026-07-13T13:58:18",
  "time_range_end": "2026-07-17T15:32:53",
  "speech_style": "<语气+长度+标点 emoji 习惯，附 1-2 条原文示例>",
  "catchphrases": ["<口头禅1>", "<口头禅2>"],
  "expression_habits": "<喜欢代码示例/类比/列要点？>",
  "qa_pattern": "<回答提问时的模式>",
  "evaluation_focus": "<评估方案时的关注点>",
  "knowledge_domains": [
    {"name": "<领域>", "topics": [...], "references": [...], "example": "<脱敏原文>"}
  ],
  "recommended_resources": [
    {"name": "<资源>", "url": "<url>", "reason": "<为什么推荐>"}
  ],
  "tech_preference": "<技术选型倾向>",
  "problem_solving_path": "<问题处理步骤>",
  "review_focus": ["<关注点1>", "<关注点2>"],
  "suitable_questions": ["<适合问1>"],
  "unsuitable_questions": ["<不适合问1>"]
}
```

- 保留 `# Edge Cases` 段（数据不足/只发链接/同名/极度简短/隐私脱敏）
- 保留 `# 行为约束` 段（不编造、附原文示例、name 字段格式）

#### 1.1.2 修改 `builder.py` 的 `build_persona()`
- 删除当前 L329-344 的"直接写 soul_content"逻辑
- 改为：

```python
def build_persona(llm_output: dict, target_dir: Path, skill_dir: Path) -> Path:
    """用 jinja2 渲染 SOUL.md.tmpl，写成 so-{name}.md"""
    target_name = llm_output.get('target_name', 'unknown')
    
    # 准备模板上下文（字段对齐 SOUL.md.tmpl 的变量名）
    context = {
        'target_name': target_name,
        'target_actual_name': llm_output.get('target_actual_name', target_name),
        'source_file': llm_output.get('source_file', ''),
        'message_count': llm_output.get('message_count', 0),
        'time_range_start': llm_output.get('time_range_start', ''),
        'time_range_end': llm_output.get('time_range_end', ''),
        'generated_at': datetime.now().strftime('%Y-%m-%d'),
        'speech_style': llm_output.get('speech_style', ''),
        'catchphrases': llm_output.get('catchphrases', []),
        'expression_habits': llm_output.get('expression_habits', ''),
        'qa_pattern': llm_output.get('qa_pattern', ''),
        'evaluation_focus': llm_output.get('evaluation_focus', ''),
        'knowledge_domains': llm_output.get('knowledge_domains', []),
        'recommended_resources': llm_output.get('recommended_resources', []),
        'tech_preference': llm_output.get('tech_preference', ''),
        'problem_solving_path': llm_output.get('problem_solving_path', ''),
        'review_focus': llm_output.get('review_focus', []),
        'suitable_questions': llm_output.get('suitable_questions', []),
        'unsuitable_questions': llm_output.get('unsuitable_questions', []),
    }
    
    templates_dir = skill_dir / 'templates' / 'persona'
    soul_content = render_template('SOUL.md.tmpl', context, templates_dir)
    
    safe_name = ''.join(c for c in target_name if c not in '/\\:*?"<>|').strip()
    out_path = target_dir / f'so-{safe_name}.md'
    out_path.write_text(soul_content, encoding='utf-8')
    print(f"[*] 人物画像已生成: {out_path}", file=sys.stderr)
    return out_path
```

- 同步修改 `main()` 中 distill 分支：传入 `skill_dir` 参数（当前未传）

#### 1.1.3 修改 `SKILL.md` 第 6 步表述
- 当前 L73-78 已经说"builder 用 jinja2 渲染 templates/"，描述本来是对的，是 builder 实现错了
- 修改后 builder 行为与文档一致，无需改 SKILL.md 文字

### 1.2 测试空白补全

新增三个测试文件 + 一个 fixtures 目录：

#### 1.2.1 `tests/test_parser.py`（新增）
| 用例 | 验证点 |
|---|---|
| `test_parse_txt_basic_message` | 单行 txt 消息正确解析出 sender/sender_id/time/content |
| `test_parse_txt_multiline_body` | 多行消息正文正确合并（直到下一个 [时间] 行） |
| `test_parse_txt_file_prefix` | `[文件] xxx.zip` 标为 msg_type=file，meta.filename 正确 |
| `test_parse_txt_image_prefix` | `[图片] xxx` 标为 msg_type=image |
| `test_parse_json_wechatdataanalysis` | senderDisplayName 优先，senderUsername 进 sender_id，renderType 映射 msg_type |
| `test_parse_json_skips_system_messages` | renderType=='system' 被跳过 |
| `test_parse_json_link_type_meta` | renderType=='link' 时 meta 含 primary_url/title/source_platform |
| `test_normalize_time_various_formats` | 6 种时间格式都被正确归一化 |
| `test_classify_content_url` | 含 https:// 标 msg_type=link |
| `test_classify_content_filename` | 含 .zip/.pdf 标 msg_type=file |
| `test_classify_content_system` | `【系统消息】` 标 msg_type=system |
| `test_sniff_format_by_extension` | .txt/.json/.html 嗅探正确 |

#### 1.2.2 `tests/test_router.py`（新增）
| 用例 | 验证点 |
|---|---|
| `test_find_target_exact_match` | sender 精确匹配，返回 actual_name == requested |
| `test_find_target_fuzzy_match` | "张老师" 模糊匹配 "张三老师" |
| `test_find_target_not_found` | 返回 found=False + available_senders 列表 |
| `test_router_mode_course_default` | 不指定 --mode 默认 course-maker |
| `test_router_mode_distill_with_target` | --mode distill --target Yang 正确路由 |
| `test_router_distill_no_target_auto_pick` | distill 无 --target 时自动选最活跃 sender |
| `test_router_distill_target_not_in_messages_exits` | target 不存在时 sys.exit(1) |
| `test_router_output_has_no_legacy_score_fields` | **回归用例**：scene.json 输出不含 course_score/distill_score/course_hits/distill_hits（防止旧版自动路由回潮） |

#### 1.2.3 `tests/test_builder.py`（新增）
| 用例 | 验证点 |
|---|---|
| `test_build_persona_writes_soul_md` | 输出 `so-{name}.md` 文件存在 |
| `test_build_persona_uses_jinja2_template` | 输出文件含模板渲染的特征字符串（如"数字分身"标题） |
| `test_build_persona_empty_input_raises` | llm_output 为空 dict 时 raise ValueError 或返回明确错误 |
| `test_build_persona_filename_safety` | target_name 含 `/\\:*?` 等非法字符时被清洗 |
| `test_build_persona_frontmatter_valid` | 输出 .md 的 YAML frontmatter 含 name/summary/distilled_from/distilled_at/target_actual_name/message_count 五个必需字段 |
| `test_render_template_with_jinja2` | jinja2 可用时正确渲染循环 `{% for %}` |
| `test_render_template_fallback_without_jinja2` | 无 jinja2 时退化到 `{{ var }}` 替换（mock HAS_JINJA=False） |
| `test_build_provenance_msg_ref_parsing` | `parse_msg_ref('msg#4')` 返回 4，非法返回 None |

#### 1.2.4 `tests/test_e2e_distill.py`（端到端，新增）
| 用例 | 验证点 |
|---|---|
| `test_e2e_real_yang_distillation` | 用真实 147 条消息跑 parser→router(distill,Yang)→builder，产出 `so-Yang.md`，校验文件存在 + frontmatter 合法 + 含 6 大块标题 |
| `test_e2e_small_dataset_warning` | < 10 条消息时 stderr 打印"数据量不足"警告但不崩溃 |

### 1.3 陈旧产物清理

| 文件 | 操作 | 理由 |
|---|---|---|
| `tests/scene.json` | **删除** | 含 `course_score/distill_score/course_hits/distill_hits` 旧字段，是已废弃的"自动路由"产物 |
| `tests/real_scene.json` | **删除** | 同上 |
| `tests/messages.json` | 保留 | course-maker 测试输入数据 |
| `tests/real_messages.json` | 保留 | 真实测试输入数据（147 条） |
| `tests/mock_course_chat.txt` | 保留 | txt 格式测试夹具 |
| `tests/llm_output_mock.json` | 保留 | course-maker LLM 输出夹具 |
| `tests/real_llm_output.json` | 保留 | course-maker 真实 LLM 输出 |
| `tests/output/` | 保留 | course-maker 黄金产物对照 |
| `tests/output_real/` | 保留 | course-maker 真实产物对照 |

新增 `tests/fixtures/distill_llm_output.json`：手工填充的 Yang 蒸馏 LLM 输出 JSON（作为 builder 单测的 golden input）。

### 1.4 真实跑通黄金样例

**数据源**：`weChatDataAnalysis/chat_log/real_test_json/conversations/0001_.../messages.json`（147 条，Yang 20 条）

**目标人物**：Yang（最活跃发言者，发言覆盖网盘分享/腾讯会议/技术链接/录屏，足够提炼 Persona + Work Skill）

**产出文件**（放在 `tests/` 下作为黄金样例）：
- `tests/so-Yang.md`：跑通后的真实 SOUL.md 产物（路径 1 阶段是 2 层结构，路径 2 升级到 6 层）
- `tests/so-Yang.llm_output.json`：对应 LLM 输出 JSON（作为端到端 fixture，未来 regression 用）
- `tests/fixtures/distill_yang_messages.json`：从真实数据裁剪的子集（仅 Yang 的 20 条 + 必要上下文 10 条），作为离线 fixture（避免依赖完整 147 条数据）

**验证脚本**：`tests/test_e2e_distill.py` 自动跑通并校验。

**手工验收清单**：
- [ ] `so-Yang.md` 文件存在且 > 50 行
- [ ] YAML frontmatter 含 5 个必需字段
- [ ] 含 Persona / Work Skill / 决策模式 / 使用建议 / 溯源 5 大块
- [ ] 至少 3 处附原文示例（脱敏后）
- [ ] 可被 Claude Code 当 expert 加载（手工把 `so-Yang.md` 复制到 `~/.workbuddy/experts/` 试加载）

### 1.5 路径 1 文件清单

| 文件 | 操作 | 主要变更 |
|---|---|---|
| `chat2work/prompts/person-distiller.md` | 修改 | Output Format 段从"产 markdown 全文"改为"产 JSON"，字段对齐 SOUL.md.tmpl 变量 |
| `chat2work/scripts/builder.py` | 修改 | `build_persona()` 改用 jinja2 渲染；`main()` distill 分支传入 skill_dir |
| `chat2work/scripts/builder.py` | 修改 | （可选）`build_persona` 加 `--no-archive` 选项，旧版本归档到 `so-{name}.archive/` |
| `chat2work/SKILL.md` | 无需改 | 当前文字本来就是说用 jinja2 渲染 |
| `chat2work/tests/test_parser.py` | 新建 | 12 个用例 |
| `chat2work/tests/test_router.py` | 新建 | 8 个用例（含 1 个回归） |
| `chat2work/tests/test_builder.py` | 新建 | 8 个用例 |
| `chat2work/tests/test_e2e_distill.py` | 新建 | 2 个端到端用例 |
| `chat2work/tests/fixtures/distill_yang_messages.json` | 新建 | Yang 黄金 fixture |
| `chat2work/tests/fixtures/distill_llm_output.json` | 新建 | LLM 输出 golden JSON |
| `chat2work/tests/so-Yang.md` | 新建 | 真实跑通产物样例 |
| `chat2work/tests/so-Yang.llm_output.json` | 新建 | 真实 LLM 输出存档 |
| `chat2work/tests/scene.json` | 删除 | 陈旧自动路由产物 |
| `chat2work/tests/real_scene.json` | 删除 | 陈旧自动路由产物 |

---

## 2. 路径 2：6 层扩层（2-3 周）

### 2.1 6 层字段设计（对齐 colleague-skill，适配 A+D 私人场景）

| Layer | 名称 | 字段 | 类型 | A 场景填充策略 | D 场景填充策略 |
|---|---|---|---|---|---|
| **0** | 硬规则/价值观底色 | `core_values[]`<br>`hard_rules[]`<br>`red_lines[]` | string[] | 从发言中反推（如"绝不让步的质量标准"） | 本人直接填（最强信号） |
| **1** | 基础身份 | `name`<br>`role`<br>`mbti`<br>`tech_stack[]`<br>`background_summary`<br>`known_resources[]{name,url,reason}` | mixed | 从消息反推（tech_stack 从发言主题抽取） | 本人补充（mbti/背景） |
| **2** | 表达风格 | `speech_style`<br>`catchphrases[]`<br>`emoji_habits`<br>`tone_switches{context→tone}`<br>`length_tendency` | mixed | 从消息高频模式抽取 | 本人补充（私人习惯） |
| **3** | 决策逻辑 | `tech_preference`<br>`problem_solving_path`<br>`evaluation_focus[]`<br>`push_or_pause{push_factor[],pause_factor[]}` | mixed | 从分歧/评估场景反推 | 本人补充（隐性决策依据） |
| **4** | 人际网络 | `audience_specific[]{audience,tone,topics[],examples[]}` | object[] | 重点（不同对象差异化沟通，从回复消息抽） | 弱化（自己视角难客观） |
| **5** | 红线与避坑 + Correction | `avoid_topics[]`<br>`corrections[]{user_said,prev_belief,corrected_to,source}` | object[] | 从拒绝/否定发言抽 | 本人补充 + 用户反馈即写入 |

**A/D 差异化策略**：同一套模板，D 场景由用户在 builder 调用时通过 `--self-mode` 标志补充本人直填字段；A 场景完全靠 LLM 从消息反推。

### 2.2 prompts/person-distiller.md 升级

5 条规则 → **8 条规则**（对齐 6 层）：

```
# Extraction Rules

## 1. 筛选目标人物的消息（保留原 #1）

## 2. Layer 0 — 价值观底色（新）
扫描发言中的"绝不让步"表达：
- 反复强调的原则（如"代码必须能跑才提交"）
- 拒绝/否定的话（如"不要用 XX 框架"）
- 价值排序（性能 vs 可读性 vs 工程性）

## 3. Layer 1 — 基础身份（原 #3 知识领域升级）
- 角色（老师/学生/工程师/...）
- 技术栈（从发言主题反推，按频率排序）
- 已知资源（书/工具/项目/课程，从 recommended_resources 提升）
- 背景摘要（一句话）

## 4. Layer 2 — 表达风格（原 #2 升级）
- 语气倾向 + 语境切换（同人对学生 vs 对同事语气不同）
- 口头禅（出现 ≥3 次）
- emoji/标点习惯
- 长度倾向

## 5. Layer 3 — 决策逻辑（原 #4 升级）
- 技术选型倾向
- 问题处理路径（步骤化）
- 评估方案时的关注点
- push 因素（推动决策的）vs pause 因素（让决策搁置的）

## 6. Layer 4 — 人际网络差异化（新）
寻找目标人物对不同对象的不同沟通方式：
- 对学生提问 vs 对同事讨论 vs 对上级汇报
- 每类对象记 audience/tone/topics/examples

## 7. Layer 5 — 红线与避坑（新）
- 避免的话题（明显回避或转移的）
- 红线（明确说"不能这样做"的）
- Correction 修正机制（详见行为约束）

## 8. Correction 修正机制（新）
若 llm_output 中带 `corrections` 字段（用户反馈），合并到 Layer 5。
```

**输出格式**：JSON，字段对齐升级后的 SOUL.md.tmpl 变量（见 2.3）。

### 2.3 templates/persona/SOUL.md.tmpl 升级

将当前 137 行 2 层模板升级为 6 层结构：

```jinja2
---
name: so-{{ target_name | lower | replace(' ', '-') }}
summary: 从群聊记录蒸馏的人物画像，可作为 Claude Code expert / WorkBuddy skill 安装
distilled_from: {{ source_file }}
distilled_at: {{ generated_at }}
target_actual_name: {{ target_actual_name }}
message_count: {{ message_count }}
distill_version: 2.0
scenario: {{ scenario | default('A') }}  {# A=蒸馏活人, D=蒸馏自己 #}
---

# {{ target_name }} — 数字分身

> 本画像由 Chat2Work 从 {{ message_count }} 条群聊发言中蒸馏生成
> 时间跨度：{{ time_range_start }} ~ {{ time_range_end }}
> 蒸馏版本：v2.0（6 层结构）
> 安装方式：把此文件放到 `~/.workbuddy/experts/agents/` 或 Claude Code skills 目录

---

## Layer 0 — 价值观底色（最高优先级）

{% if core_values %}
### 核心价值观
{% for v in core_values %}
- {{ v }}
{% endfor %}
{% endif %}

{% if hard_rules %}
### 硬规则（绝不让步）
{% for r in hard_rules %}
- {{ r }}
{% endfor %}
{% endif %}

{% if red_lines %}
### 红线（明确拒绝）
{% for r in red_lines %}
- {{ r }}
{% endfor %}
{% endif %}

---

## Layer 1 — 基础身份

- **姓名/角色**：{{ target_actual_name }} / {{ role | default('-') }}
- **MBTI**：{{ mbti | default('未推断') }}
- **技术栈**：{{ tech_stack | join('、') if tech_stack else '-' }}
- **背景**：{{ background_summary | default('-') }}

{% if known_resources %}
### 已知资源
{% for res in known_resources %}
- **{{ res.name }}**{% if res.url %}（{{ res.url }}）{% endif %} — {{ res.reason | default('-') }}
{% endfor %}
{% endif %}

---

## Layer 2 — 表达风格

### 说话风格
{{ speech_style | default('数据不足。') }}

{% if catchphrases %}
### 口头禅
{% for p in catchphrases %}- "{{ p }}"
{% endfor %}
{% endif %}

{% if tone_switches %}
### 语境切换
{% for ctx, tone in tone_switches.items() %}
- 对**{{ ctx }}**：{{ tone }}
{% endfor %}
{% endif %}

- **emoji/标点习惯**：{{ emoji_habits | default('-') }}
- **长度倾向**：{{ length_tendency | default('-') }}

---

## Layer 3 — 决策逻辑

### 技术选型倾向
{{ tech_preference | default('数据不足。') }}

### 问题处理路径
{{ problem_solving_path | default('数据不足。') }}

{% if evaluation_focus %}
### 评估关注点
{% for f in evaluation_focus %}- {{ f }}{% endfor %}
{% endif %}

{% if push_or_pause %}
### 推动 vs 搁置
- **推动因素**：{{ push_or_pause.push | join('、') if push_or_pause.push else '-' }}
- **搁置因素**：{{ push_or_pause.pause | join('、') if push_or_pause.pause else '-' }}
{% endif %}

---

## Layer 4 — 人际网络差异化

{% if audience_specific %}
{% for a in audience_specific %}
### 对 {{ a.audience }}
- 语气：{{ a.tone | default('-') }}
- 话题：{{ a.topics | join('、') if a.topics else '-' }}
- 示例：{{ a.examples | join(' / ') if a.examples else '-' }}
{% endfor %}
{% else %}
发言样本中未观察到对不同对象的差异化沟通模式。
{% endif %}

---

## Layer 5 — 红线与避坑 + Correction 修正层

{% if avoid_topics %}
### 避免话题
{% for t in avoid_topics %}- {{ t }}{% endfor %}
{% endif %}

{% if corrections %}
### Correction 修正记录
{% for c in corrections %}
- **用户反馈**："{{ c.user_said }}"
  - 原画像：{{ c.prev_belief }}
  - 修正为：{{ c.corrected_to }}
  - 来源：{{ c.source | default('用户反馈') }}
  - 时间：{{ c.corrected_at | default('-') }}
{% endfor %}
{% else %}
> 若画像与实际不符，请直接编辑此节添加 correction 记录，下次蒸馏时会被合并。
{% endif %}

---

## 使用建议

### 适合问
{% for q in suitable_questions %}- {{ q }}{% endfor %}

### 不适合问
{% for q in unsuitable_questions %}- {{ q }}{% endfor %}

---

## 诚实边界声明

> 本画像存在以下局限，使用时请知悉：
> 1. **蒸馏不了直觉**：仅能从公开文字推断，无法捕捉隐性经验
> 2. **捕捉不了突变**：数据有时效性，人物想法会变化
> 3. **公开表达 ≠ 真实想法**：聊天 ≠ 内心，群聊发言带社交滤镜
> 4. **样本偏差**：群聊场景下发言未必代表该人物全貌

---

## 溯源

- **源文件**：{{ source_file }}
- **消息条数**：{{ message_count }}
- **时间范围**：{{ time_range_start }} ~ {{ time_range_end }}
- **蒸馏时间**：{{ generated_at }}
- **蒸馏版本**：v2.0（6 层结构）

---

*此人物画像由 Chat2Work 自动生成，仅供私人学习研究使用。请勿用于冒充本人或商业用途。*
```

### 2.4 builder.py build_persona 升级

```python
def build_persona(llm_output: dict, target_dir: Path, skill_dir: Path,
                  scenario: str = 'A', archive_previous: bool = True) -> Path:
    """用 jinja2 渲染 6 层 SOUL.md.tmpl，写成 so-{name}.md。
    
    Args:
        scenario: 'A'=蒸馏活人, 'D'=蒸馏自己（影响某些字段的默认填充）
        archive_previous: 旧版本是否归档到 so-{name}.archive/
    """
    target_name = llm_output.get('target_name', 'unknown')
    safe_name = ''.join(c for c in target_name if c not in '/\\:*?"<>|').strip()
    out_path = target_dir / f'so-{safe_name}.md'
    
    # 旧版本归档（colleague-skill 的版本回滚特性）
    if archive_previous and out_path.exists():
        archive_dir = target_dir / f'so-{safe_name}.archive'
        archive_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        archive_path = archive_dir / f'so-{safe_name}.{timestamp}.md'
        shutil.move(str(out_path), str(archive_path))
        print(f"[*] 旧版本已归档: {archive_path}", file=sys.stderr)
    
    # 合并 corrections（用户反馈合并到 Layer 5）
    corrections = llm_output.get('corrections', [])
    if archive_previous:
        # 从归档目录读取历史 corrections
        corrections = _merge_historical_corrections(corrections, target_dir / f'so-{safe_name}.archive')
    
    context = {
        # Layer 0
        'core_values': llm_output.get('core_values', []),
        'hard_rules': llm_output.get('hard_rules', []),
        'red_lines': llm_output.get('red_lines', []),
        # Layer 1
        'target_name': target_name,
        'target_actual_name': llm_output.get('target_actual_name', target_name),
        'role': llm_output.get('role', ''),
        'mbti': llm_output.get('mbti', ''),
        'tech_stack': llm_output.get('tech_stack', []),
        'background_summary': llm_output.get('background_summary', ''),
        'known_resources': llm_output.get('known_resources', []),
        # Layer 2
        'speech_style': llm_output.get('speech_style', ''),
        'catchphrases': llm_output.get('catchphrases', []),
        'tone_switches': llm_output.get('tone_switches', {}),
        'emoji_habits': llm_output.get('emoji_habits', ''),
        'length_tendency': llm_output.get('length_tendency', ''),
        # Layer 3
        'tech_preference': llm_output.get('tech_preference', ''),
        'problem_solving_path': llm_output.get('problem_solving_path', ''),
        'evaluation_focus': llm_output.get('evaluation_focus', []),
        'push_or_pause': llm_output.get('push_or_pause', {}),
        # Layer 4
        'audience_specific': llm_output.get('audience_specific', []),
        # Layer 5
        'avoid_topics': llm_output.get('avoid_topics', []),
        'corrections': corrections,
        # 溯源
        'source_file': llm_output.get('source_file', ''),
        'message_count': llm_output.get('message_count', 0),
        'time_range_start': llm_output.get('time_range_start', ''),
        'time_range_end': llm_output.get('time_range_end', ''),
        'generated_at': datetime.now().strftime('%Y-%m-%d'),
        'scenario': scenario,
    }
    
    templates_dir = skill_dir / 'templates' / 'persona'
    soul_content = render_template('SOUL.md.tmpl', context, templates_dir)
    out_path.write_text(soul_content, encoding='utf-8')
    return out_path


def _merge_historical_corrections(new_corrections: list, archive_dir: Path) -> list:
    """从归档目录的历史 SOUL.md 中提取 corrections 并合并到新列表。"""
    if not archive_dir.exists():
        return new_corrections
    historical = []
    for archived_md in sorted(archive_dir.glob('*.md'), reverse=True):
        try:
            text = archived_md.read_text(encoding='utf-8')
            # 简单解析 ### Correction 修正记录 之后的列表项
            in_section = False
            for line in text.split('\n'):
                if '### Correction 修正记录' in line:
                    in_section = True
                    continue
                if in_section:
                    if line.startswith('---'):
                        break
                    if line.startswith('- **用户反馈**'):
                        historical.append({'user_said': line, 'prev_belief': '', 'corrected_to': '', 'source': '历史归档'})
        except Exception:
            continue
    return historical + new_corrections
```

### 2.5 路径 2 文件清单

| 文件 | 操作 | 主要变更 |
|---|---|---|
| `chat2work/prompts/person-distiller.md` | 修改 | 5 条规则 → 8 条规则；Output 格式扩展到 6 层字段 |
| `chat2work/templates/persona/SOUL.md.tmpl` | 修改 | 137 行 2 层 → 约 200 行 6 层结构 + 诚实边界声明 + Correction 模板 |
| `chat2work/scripts/builder.py` | 修改 | `build_persona()` 支持 6 层字段；加 `--scenario` 和 `--archive-previous` 选项；加 `_merge_historical_corrections` |
| `chat2work/tests/test_builder.py` | 修改 | 新增 6 层字段渲染、归档、corrections 合并用例 |
| `chat2work/tests/so-Yang.md` | 重新生成 | 6 层结构真实样例 |
| `chat2work/tests/so-Yang.llm_output.json` | 重新生成 | 6 层字段 LLM 输出 golden |
| `chat2work/tests/fixtures/distill_llm_output.json` | 修改 | 同步 6 层字段 |

---

## 3. 路径 3：三重验证简化版（3-4 周）

### 3.1 不照搬 nuwa-skill 6 Agent 并行的理由

- nuwa-skill 用 6 个独立 Agent 并行采集 40+ 信息源，对一人公司过重
- 我们的目标是 A+D 私人场景，数据源单一（微信），不需要并行采集
- 但 nuwa-skill 的"三重验证"思想可移植为单 Agent 多轮 + 规则过滤

### 3.2 单 Agent 多轮提炼流程

```
LLM 第 1 轮：行为观察视角
  输入：messages + extracted + 6 层 prompt
  输出：observations[] = [{layer, observation, evidence_msgs[], confidence}]
  视角提示词："你是一位行为观察员，只记录观察到的行为，不做推断"

LLM 第 2 轮：动机推理视角
  输入：第 1 轮的 observations[] + 原始 messages
  输出：inferences[] = [{observation_id, inferred_motivation, supporting_msgs[], contradicting_msgs[]}]
  视角提示词："基于观察，推断目标人物的动机和偏好"

LLM 第 3 轮：预测验证视角
  输入：第 2 轮的 inferences[] + 原始 messages（去掉某些消息作 holdout）
  输出：predictions[] = [{inference_id, predicted_behavior, holdout_msgs[], verified:bool}]
  视角提示词："如果推断正确，那目标人物在 holdout 消息中应该表现出什么？验证之"

合并：observations + inferences + predictions → 蒸馏字段填充
```

**实现**：新增 `chat2work/scripts/validator.py`（约 200 行），编排 3 轮 LLM 调用（实际由宿主 AI 执行，validator 只产 prompt 和合并结果）。

### 3.3 三重过滤的简化实现（规则化自动检查）

不依赖 LLM 自我评审，改用**纯规则**做硬过滤（可重现、可解释）：

#### 3.3.1 跨域复现（cross_domain_reproducibility）
```python
def check_cross_domain_reproducibility(observations, messages, target_name):
    """同一观察在 ≥2 个不同主题/时间段的发言中出现才算稳。"""
    target_msgs = [m for m in messages if m['sender'] == target_name]
    # 按时间分桶（每周一段）
    buckets = bucket_by_week(target_msgs)
    # 按主题分桶（用 jieba 抽关键词聚类）
    topic_buckets = bucket_by_topic(target_msgs)
    
    results = []
    for obs in observations:
        evidence_msgs = obs.get('evidence_msgs', [])
        # 该观察的证据消息分布在几个时间桶/主题桶
        time_buckets_hit = len({get_bucket(m) for m in evidence_msgs if get_bucket(m) in buckets})
        topic_buckets_hit = len({get_topic(m) for m in evidence_msgs})
        reproducibility_score = min(time_buckets_hit, topic_buckets_hit)
        results.append({
            'observation': obs['observation'],
            'reproducibility': reproducibility_score,
            'passed': reproducibility_score >= 2,
        })
    return results
```

#### 3.3.2 预测力（predictive_power）
```python
def check_predictive_power(predictions, holdout_msgs):
    """观察的预测能在 holdout 消息中被验证。"""
    results = []
    for pred in predictions:
        verified_count = 0
        for holdout_msg in holdout_msgs:
            # 关键词匹配（简化版；可用 embedding 相似度升级）
            if any(kw in holdout_msg['content'] for kw in pred['predicted_keywords']):
                verified_count += 1
        power_score = verified_count / max(1, len(holdout_msgs))
        results.append({
            'prediction': pred['predicted_behavior'],
            'verified_count': verified_count,
            'power_score': power_score,
            'passed': power_score >= 0.3,  # 至少 30% holdout 验证
        })
    return results
```

#### 3.3.3 排他性（exclusivity）
```python
def check_exclusivity(observations, all_messages, target_name):
    """观察的发出者 unique 占比 ≥ 阈值。"""
    other_senders = {m['sender'] for m in all_messages if m['sender'] != target_name}
    results = []
    for obs in observations:
        # 该观察的关键词在其他人的发言里出现几次
        other_hits = sum(
            1 for m in all_messages
            if m['sender'] in other_senders
            and any(kw in m['content'] for kw in obs['keywords'])
        )
        target_hits = len(obs.get('evidence_msgs', []))
        exclusivity = target_hits / max(1, target_hits + other_hits)
        results.append({
            'observation': obs['observation'],
            'exclusivity': exclusivity,
            'passed': exclusivity >= 0.6,  # 60% 以上来自目标人物
        })
    return results
```

#### 3.3.4 综合三重过滤
```python
def triple_validate(observations, predictions, all_messages, target_name):
    """三重过滤，未通过的观察标 [unverified] 但保留。"""
    repro = check_cross_domain_reproducibility(observations, all_messages, target_name)
    power = check_predictive_power(predictions, [m for m in all_messages if m['sender'] == target_name][-5:])  # 后 5 条作 holdout
    exclu = check_exclusivity(observations, all_messages, target_name)
    
    # 合并到 observations，加 verification_status 字段
    for obs, r, p, e in zip(observations, repro, power, exclu):
        obs['verification'] = {
            'cross_domain': r['passed'],
            'predictive': p['passed'],
            'exclusive': e['passed'],
            'score': sum([r['passed'], p['passed'], e['passed']]),  # 0-3
        }
        obs['verification_status'] = (
            'verified' if obs['verification']['score'] == 3
            else 'partial' if obs['verification']['score'] >= 1
            else 'unverified'
        )
    return observations
```

**SOUL.md.tmpl 渲染时**：每个观察后附 `<verification_status: verified|partial|unverified>` 标签。

### 3.4 诚实边界声明模板

固定写在 SOUL.md.tmpl 末尾（已含在 2.3 的模板里）：

```markdown
## 诚实边界声明

> 本画像存在以下局限，使用时请知悉：
> 1. **蒸馏不了直觉**：仅能从公开文字推断，无法捕捉隐性经验
> 2. **捕捉不了突变**：数据有时效性，人物想法会变化
> 3. **公开表达 ≠ 真实想法**：聊天 ≠ 内心，群聊发言带社交滤镜
> 4. **样本偏差**：群聊场景下发言未必代表该人物全貌
> 5. **验证状态**：每条观察带 verified/partial/unverified 标签，未验证的请谨慎采信
```

### 3.5 路径 3 文件清单

| 文件 | 操作 | 主要变更 |
|---|---|---|
| `chat2work/scripts/validator.py` | 新建 | 单 Agent 多轮编排 + 三重过滤规则化（约 250 行） |
| `chat2work/prompts/person-distiller.md` | 修改 | 新增"多轮提炼视角"和"verification_status 输出"段 |
| `chat2work/templates/persona/SOUL.md.tmpl` | 修改 | 每个观察后附 verification_status 标签（在路径 2 基础上） |
| `chat2work/scripts/builder.py` | 修改 | 调 validator 后再渲染 |
| `chat2work/tests/test_validator.py` | 新建 | 三重过滤各 2-3 个用例 |
| `chat2work/scripts/extractor.py` | 修改 | 新增 `_extract_keywords(content)` 用 jieba，供 validator 复用 |
| `chat2work/tests/so-Yang.md` | 重新生成 | 含 verification_status 的最终样例 |

---

## 4. 已确认的关键决策

> 用户已于 2026-07-19 确认以下 4 个决策点，全部采用推荐方案。

### 4.1 双轨问题：启用 jinja2 渲染 ✅
LLM 输出从"markdown 全文"改为"结构化 JSON"，builder 用 jinja2 渲染 SOUL.md.tmpl。
- 与 course-maker 模式一致（同为 LLM 出 JSON + jinja2 渲染）
- 字段可程序化校验，避免 LLM 全文输出的字段遗漏/格式漂移
- 路径 2 扩 6 层时结构化 JSON + 模板渲染远比 LLM 全文输出可控
- prompt 复杂度增加约 30 行可接受

### 4.2 A/D 差异化：单模板 + --self-mode 标志 ✅
同一套 6 层模板，D 场景通过 `--self-mode` 标志补充本人直填字段（mbti/background/avoid_topics 等）。
- 模板单一易维护，路径 2/3 迭代不需双份工作
- A 场景完全靠 LLM 从消息反推
- D 场景由用户在 builder 调用时通过标志补充本人字段
- 模板靠字段 default 处理空值，不分支

### 4.3 三重验证：纯规则硬过滤 ✅
跨域复现/预测力/排他性都用 Python 规则检查（关键词匹配/时间分桶/发送者占比），不引入 LLM 自我评审。
- 规则可重现、可解释、零额外 LLM 成本
- 避免 LLM 自我评审"自己说自己好"的可信度问题
- 多轮提炼（路径 3.2）已引入 LLM 多视角，过滤阶段不再叠 LLM
- 阈值放 `validator.py` 顶部常量，可调

### 4.4 Correction 机制：双轨触发 ✅
- 自动：用户编辑 SOUL.md 的 Correction 节后，下次蒸馏自动合并归档目录的历史 corrections（详见 2.4 的 `_merge_historical_corrections`）
- 手动：通过 `chat2work correct so-Yang.md --user-said "..." --prev "..." --corrected "..."` 命令直接写入

### 4.5 数据源扩展排期（次要决策，已采纳推荐）
当前仅支持微信（WechatDataAnalysis JSON）。colleague-skill 的 8 种数据源（飞书/钉钉/Slack/微信/PDF/邮件/JSON/Markdown）**不进路径 1-3**，放在路径 3 完成后作为独立 v1.5 阶段（约 1 周）。避免主线被打断。

---

## 5. 风险与边界

### 5.1 蒸馏自己 vs 蒸馏他人的伦理边界

| 风险 | 缓解措施 |
|---|---|
| 蒸馏他人侵犯隐私 | parser 阶段加 `--redact` 选项（默认开）：电话/邮箱/wxid/真实姓名自动 mask；SOUL.md 不保留原始消息全文，只保留脱敏后的示例片段 |
| 蒸馏自己被"自己骗自己" | D 场景强制要求至少 30 条本人发言；引入路径 3 的"排他性"检查（自己 vs 其他人的发言模式差异） |
| 数字分身被用于冒充 | SOUL.md frontmatter 强制声明 `for_personal_use_only: true`；末尾固定声明"请勿用于冒充本人或商业用途" |
| 数据泄露 | 默认所有产物落在用户当前工作目录（不写 skill 目录）；归档目录 `.archive/` 加 .gitignore 建议 |

### 5.2 隐私脱敏具体实现策略

在 `parser.py` 加 `redact_pii(text)` 函数：
```python
PHONE_PATTERN = re.compile(r'1[3-9]\d{9}')
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
WXID_PATTERN = re.compile(r'wxid_[a-zA-Z0-9_]+')
ID_CARD_PATTERN = re.compile(r'\d{17}[\dXx]')

def redact_pii(text: str) -> str:
    text = PHONE_PATTERN.sub('[PHONE]', text)
    text = EMAIL_PATTERN.sub('[EMAIL]', text)
    text = WXID_PATTERN.sub('[WXID]', text)
    text = ID_CARD_PATTERN.sub('[IDCARD]', text)
    return text
```
- 默认对 SOUL.md 中所有"原文示例"段应用 `redact_pii`
- 在 frontmatter 加 `pii_redacted: true` 标记
- parser 不动 messages.json（原始数据保留），只在 builder 输出 SOUL.md 时脱敏

### 5.3 与现有 course-maker 模式的兼容性

| 兼容性维度 | 措施 |
|---|---|
| router.py 主入口 | 不变：`--mode course|distill` 显式路由；distill 加 `--target` |
| builder.py 主入口 | 不变：根据 `mode` 字段分发；distill 分支多传 `skill_dir` |
| extractor.py | person-distiller 也复用 extracted（链接/文件/日期/会议号 → recommended_resources / known_resources），不另写规则 |
| prompts/ 扩展机制 | 不变：加新场景只需在 prompts/ 加 .md + templates/ 加模板目录 |
| 测试 | course-maker 测试不动；新增 distill 测试独立 |

**关键不变量**：course-maker 模式的 147 条真实数据回归验证（README 提到）必须不被破坏。新增 distill 测试独立，不动 course-maker 测试文件。

### 5.4 与 WorkBuddy Expert 系统的兼容性

参考 `~/.workbuddy/plugins/marketplaces/experts/plugins/senior-developer/agents/senior-developer.md`：
- SOUL.md frontmatter 字段对齐 WorkBuddy expert 标准（name/summary + 新增 distilled_from/distilled_at/target_actual_name/message_count）
- 安装路径建议：`~/.workbuddy/experts/agents/so-{name}.md`（如果 WorkBuddy 未来支持 user-level experts）
- 当前作为 fallback：用户手工把 `so-Yang.md` 复制到任意 Claude Code/WorkBuddy skills 目录即可加载
- 不依赖 WorkBuddy 内部 API，纯文件级兼容

### 5.5 风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| jinja2 未安装导致退化模式字段缺失 | 中 | 中 | 退化模式仅做 `{{ var }}` 替换，复杂 `{% for %}` 不渲染——在 builder 启动时检测 HAS_JINJA，未安装时警告并退出（强制要求 jinja2） |
| 真实数据中 Yang 发言偏少（20 条）蒸馏质量不够 | 中 | 高 | 20 条够路径 1 验证骨架；路径 2/3 跑 6 层时若质量不够，再补充更多 conversation 数据 |
| Correction 合并逻辑复杂导致回归 | 低 | 中 | 用归档目录只读历史 corrections，不修改归档文件本身；加单测覆盖 |
| 三重验证规则阈值（0.3/0.6/2）不准 | 高 | 中 | 阈值放 `validator.py` 顶部常量，可调；初期用宽松阈值，跑通后再收紧 |
| 隐私脱敏漏掉新 PII 模式 | 中 | 高 | `redact_pii` 设计为可扩展（patterns 数组），用户可补充；脱敏后 frontmatter 标 `pii_redacted: true` 让用户知悉 |

---

## 6. 完整文件清单汇总

### 6.1 路径 1（1-2 周）
| 路径 | 操作 | 主要变更 |
|---|---|---|
| `chat2work/prompts/person-distiller.md` | 修改 | Output Format 改为 JSON |
| `chat2work/scripts/builder.py` | 修改 | `build_persona()` 用 jinja2；`main()` 传 skill_dir |
| `chat2work/tests/test_parser.py` | 新建 | 12 用例 |
| `chat2work/tests/test_router.py` | 新建 | 8 用例 |
| `chat2work/tests/test_builder.py` | 新建 | 8 用例 |
| `chat2work/tests/test_e2e_distill.py` | 新建 | 2 用例 |
| `chat2work/tests/fixtures/distill_yang_messages.json` | 新建 | Yang 黄金 fixture |
| `chat2work/tests/fixtures/distill_llm_output.json` | 新建 | LLM 输出 golden |
| `chat2work/tests/so-Yang.md` | 新建 | 真实跑通产物 |
| `chat2work/tests/so-Yang.llm_output.json` | 新建 | 真实 LLM 输出存档 |
| `chat2work/tests/scene.json` | 删除 | 陈旧自动路由产物 |
| `chat2work/tests/real_scene.json` | 删除 | 陈旧自动路由产物 |

### 6.2 路径 2（2-3 周）
| 路径 | 操作 | 主要变更 |
|---|---|---|
| `chat2work/prompts/person-distiller.md` | 修改 | 5 → 8 条规则 |
| `chat2work/templates/persona/SOUL.md.tmpl` | 修改 | 2 层 → 6 层结构 |
| `chat2work/scripts/builder.py` | 修改 | `build_persona` 支持 6 层 + 归档 + scenario |
| `chat2work/tests/test_builder.py` | 修改 | 新增 6 层渲染用例 |
| `chat2work/tests/so-Yang.md` | 重新生成 | 6 层真实样例 |
| `chat2work/tests/so-Yang.llm_output.json` | 重新生成 | 6 层字段 golden |
| `chat2work/tests/fixtures/distill_llm_output.json` | 修改 | 同步 6 层字段 |

### 6.3 路径 3（3-4 周）
| 路径 | 操作 | 主要变更 |
|---|---|---|
| `chat2work/scripts/validator.py` | 新建 | 多轮编排 + 三重过滤（约 250 行） |
| `chat2work/prompts/person-distiller.md` | 修改 | 新增多轮视角和 verification 段 |
| `chat2work/templates/persona/SOUL.md.tmpl` | 修改 | 每观察附 verification_status |
| `chat2work/scripts/builder.py` | 修改 | 调 validator 后再渲染 |
| `chat2work/tests/test_validator.py` | 新建 | 三重过滤用例 |
| `chat2work/scripts/extractor.py` | 修改 | 新增 `_extract_keywords` |
| `chat2work/tests/so-Yang.md` | 重新生成 | 含 verification_status 终版 |

### 6.4 全局新增依赖
- `jinja2`（已在 tool-WeChatMsg/.venv 中，确认 chat2work 也装上）
- `jieba`（路径 3 关键词聚类用，已在 tool-WeChatMsg/.venv 中）

---

## 7. 里程碑验收标准

### 路径 1 验收（2 周末）
- [ ] `pytest chat2work/tests/ -v` 全绿（含新增 30 个用例）
- [ ] `tests/so-Yang.md` 存在且通过手工验收清单（1.4）
- [ ] `tests/scene.json` 和 `tests/real_scene.json` 已删除
- [ ] builder 行为与 SKILL.md 第 6 步描述一致

### 路径 2 验收（5 周末）
- [ ] `so-Yang.md` 升级为 6 层结构，所有 Layer 0-5 字段都有内容
- [ ] Correction 修正层模板可用（手工编辑后下次蒸馏能合并）
- [ ] D 场景能通过 `--self-mode` 补充本人字段
- [ ] 与 course-maker 模式回归测试全绿

### 路径 3 验收（8 周末）
- [ ] `validator.py` 三重过滤跑通，每条 observation 带 verification_status
- [ ] `so-Yang.md` 含"诚实边界声明"段
- [ ] 三重过滤阈值可调（常量化）
- [ ] 跑通后 SOUL.md 可被 Claude Code 当 expert 加载（手工验证）

---

## 8. 执行顺序建议

1. **第 1 周**：路径 1.1（双轨修复）+ 1.3（清理陈旧产物）+ 1.4（真实跑通黄金样例）
2. **第 2 周**：路径 1.2（补测试）+ 验收
3. **第 3-4 周**：路径 2（6 层扩层 + Correction + 归档）
4. **第 5 周**：路径 2 验收 + 路径 3 启动（validator 骨架）
5. **第 6-7 周**：路径 3（三重过滤 + 多轮编排）
6. **第 8 周**：路径 3 验收 + 全局回归

---

## 附录 A：真实数据探索结论

### A.1 Yang 发言样本（20 条，2026-07-13 至 2026-07-17）
- 主要类型：百度网盘分享（含 pwd 提取码）、腾讯会议邀请、技术链接分享、会议录屏
- 推断 Persona：技术布道者，频繁组织线上会议，分享数字孪生/UE/MCP 相关资源
- 推断 Work Skill：数字孪生（DTS_Library_V6.pak）、UE Vue 模板、MCP Server
- 推断 Decision Pattern：偏好实操（先发会议邀请→发资料→发录屏回放）

### A.2 WorkBuddy Expert 标准格式（参考 senior-developer.md）
- YAML frontmatter：`name / description / color / emoji / vibe`
- Identity directive 段（最高优先级身份指令）
- Philosophy / Rules / Process / Skills 集成 / Final identity reminder
- 我们 SOUL.md 不强求对齐此格式（私人用），但保证 frontmatter 字段兼容

### A.3 当前 SOUL.md.tmpl 字段清单
target_name / source_file / generated_at / message_count / time_range_start / time_range_end / speech_style / catchphrases / expression_habits / qa_pattern / evaluation_focus / knowledge_domains[]{name,topics,references,example} / recommended_resources[]{name,url,reason} / tech_preference / problem_solving_path / review_focus[] / suitable_questions[] / unsuitable_questions[]

### A.4 路径 2 升级后的字段清单
路径 1 字段全部保留 + 新增：
- Layer 0：core_values[] / hard_rules[] / red_lines[]
- Layer 1：role / mbti / tech_stack[] / background_summary / known_resources[]{name,url,reason}（原 recommended_resources 升级）
- Layer 2：tone_switches{} / emoji_habits / length_tendency
- Layer 3：push_or_pause{push[],pause[]}
- Layer 4：audience_specific[]{audience,tone,topics[],examples[]}
- Layer 5：avoid_topics[] / corrections[]{user_said,prev_belief,corrected_to,source,corrected_at}
- 元数据：distill_version / scenario

---

## 附录 B：与原用户决策的对应

| 用户决策 | 计划响应 |
|---|---|
| 决策 1：路径 1+2+3 三阶段渐进，不做自进化 | 完整覆盖路径 1+2+3，6-8 周；未做路径 4（Hermes） |
| 决策 2：A+D 私人使用，隐私最高，与 WorkBuddy expert 兼容 | 5.2 隐私脱敏；2.1 表中 A/D 差异化；5.4 WorkBuddy 兼容 |
| 决策 3：6 层全量版对齐 colleague-skill | 2.1 表对齐 6 层；2.2-2.4 同步升级 prompt/template/builder |
| 决策 4：覆盖 1+2+3 全部三阶段，6-8 周交付 | 第 8 节执行顺序，8 周交付 |
