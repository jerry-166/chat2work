# chat2work v2 规则提取器(extractor)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `scripts/extractor.py`,用正则从 messages.json 全量抽取链接/文件/提取码/日期/会议号(100% 不丢),并接入 pipeline,让 LLM 不再自己扫链接、只做语义标注。

**Architecture:** extractor 是 parser 和 LLM 之间的一个纯函数式中间件——输入 messages.json,输出 extracted.json。pipeline 变为 `parser → extractor → LLM(读 extracted,只标语义)→ builder`。builder 的链接库.md 改为优先用 extracted.links(保证不丢),llm_output.refs 只贡献 why/title。

**Tech Stack:** Python 3.10+(用 `re`、`pathlib`、`argparse`、`json` 标准库,零新依赖)、pytest(测试)、jinja2(已有,builder 渲染)。

---

## File Structure

- **Create** `chat2work/scripts/extractor.py` — 规则提取器主体,CLI 入口 + 各类提取函数。单一职责:从 messages 抽客观字段,不做任何语义判断。
- **Create** `chat2work/tests/test_extractor.py` — extractor 单元测试,pytest 格式。
- **Create** `chat2work/tests/fixtures/extractor_messages.json` — 测试用的构造消息数据(含百度网盘+提取码、腾讯会议号、相对/绝对日期、各类文件名)。
- **Modify** `chat2work/prompts/course-maker.md` — 告诉 LLM 链接/文件/提取码已在输入 extracted 字段给出,不要自己重扫,只标语义。
- **Modify** `chat2work/scripts/builder.py` — 读 extracted.json,链接库.md 用 extracted.links 做主表,llm_output.refs 只 join 语义字段。

---

## Task 1: 搭测试骨架 + fixtures

**Files:**
- Create: `chat2work/tests/fixtures/extractor_messages.json`
- Create: `chat2work/tests/test_extractor.py`

- [ ] **Step 1: 建 fixtures 目录和构造数据**

写入 `chat2work/tests/fixtures/extractor_messages.json`(覆盖所有提取场景:网盘+提取码、腾讯会议、绝对日期、相对日期、多种文件后缀、纯闲聊):

```json
{
  "messages": [
    {"sender": "Yang", "sender_id": "wxid_a", "time": "2026-07-14T09:03:00", "content": "分享个网盘 链接: https://pan.baidu.com/s/1IWgZBqY8nigCCkL8D_fK2Q?pwd=vp2i 提取码: vp2i", "msg_type": "text"},
    {"sender": "Yang", "sender_id": "wxid_a", "time": "2026-07-14T09:10:00", "content": "腾讯会议 邀请链接：https://meeting.tencent.com/dm/gDzNYijsmS5L #腾讯会议号：460-149-615", "msg_type": "text"},
    {"sender": "张老师", "sender_id": "wxid_b", "time": "2026-07-10T11:13:00", "content": "产品页 https://www.waveshare.net/wiki/WAVEGO 先看介绍", "msg_type": "text"},
    {"sender": "张老师", "sender_id": "wxid_b", "time": "2026-07-10T14:32:00", "content": "提交方式：上传学习通 截止时间：2026-07-25 23:59", "msg_type": "text"},
    {"sender": "张老师", "sender_id": "wxid_b", "time": "2026-07-12T14:01:00", "content": "报告模板发群文件了，叫 实验报告模板.docx；补丁代码 wavego_twin_patch.zip", "msg_type": "text"},
    {"sender": "李同学", "sender_id": "wxid_c", "time": "2026-07-15T10:00:00", "content": "收到，谢谢老师！", "msg_type": "text"},
    {"sender": "张老师", "sender_id": "wxid_b", "time": "2026-07-15T11:00:00", "content": "纸质报告下周交", "msg_type": "text"}
  ]
}
```

- [ ] **Step 2: 写第一个失败测试(链接提取,带 ?pwd= 不截断)**

写入 `chat2work/tests/test_extractor.py`:

```python
"""extractor 单元测试。运行: pytest chat2work/tests/test_extractor.py -v"""
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from extractor import extract_all

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'extractor_messages.json'


def load_messages():
    data = json.loads(FIXTURE.read_text(encoding='utf-8'))
    return data['messages']


def test_extract_links_keeps_pwd_query_string():
    """百度网盘链接的 ?pwd=vp2i 必须完整保留,不能截断。"""
    result = extract_all(load_messages())
    urls = [l['url'] for l in result['links']]
    assert 'https://pan.baidu.com/s/1IWgZBqY8nigCCkL8D_fK2Q?pwd=vp2i' in urls
```

- [ ] **Step 3: 运行测试,确认失败(模块不存在)**

Run: `py -m pytest chat2work/tests/test_extractor.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'extractor'`

- [ ] **Step 4: 提交测试骨架**

```bash
git add chat2work/tests/fixtures/extractor_messages.json chat2work/tests/test_extractor.py
git commit -m "test(extractor): 搭测试骨架 + fixtures(链接/文件/提取码/会议号/日期)"
```

---

## Task 2: 链接提取 + 提取码配对

**Files:**
- Create: `chat2work/scripts/extractor.py`
- Modify: `chat2work/tests/test_extractor.py`(追加测试)

- [ ] **Step 1: 追加失败测试(提取码配对 + 普通链接)**

在 `test_extractor.py` 末尾追加:

```python
def test_extract_links_pairs_extract_code():
    """同消息里的提取码要与链接绑定到 extract_code 字段。"""
    result = extract_all(load_messages())
    baidu = next(l for l in result['links'] if 'pan.baidu.com' in l['url'])
    assert baidu['extract_code'] == 'vp2i'
    assert baidu['msg_index'] == 0
    assert baidu['sender'] == 'Yang'


def test_extract_links_without_code_has_none():
    """无提取码的链接,extract_code 为 None。"""
    result = extract_all(load_messages())
    wiki = next(l for l in result['links'] if 'waveshare' in l['url'])
    assert wiki['extract_code'] is None
    assert wiki['msg_index'] == 2


def test_extract_links_tencent_meeting_kept():
    """腾讯会议邀请链接也要抽出。"""
    result = extract_all(load_messages())
    urls = [l['url'] for l in result['links']]
    assert 'https://meeting.tencent.com/dm/gDzNYijsmS5L' in urls
```

- [ ] **Step 2: 运行测试,确认 4 个全失败**

Run: `py -m pytest chat2work/tests/test_extractor.py -v`
Expected: FAIL(4 个 test,extractor 模块不存在)

- [ ] **Step 3: 实现 extractor.py 的链接提取**

写入 `chat2work/scripts/extractor.py`:

```python
#!/usr/bin/env python3
"""
Chat2Work extractor — 从 messages.json 全量抽取客观字段。

规则提取,无 LLM,100% 不丢。抽取:链接(保留 ?pwd=)、提取码配对、
文件名、日期(绝对/相对)、腾讯会议号。

用法:
  python extractor.py <messages.json> [--output extracted.json]

每条结果带 msg_index,可回指 messages.json 的下标做溯源。
"""

import argparse
import json
import re
import sys
from pathlib import Path


# 链接:保留完整 query string(?pwd=xxx 不截断)。停在空白/中文标点/引号/括号
LINK_PATTERN = re.compile(r'https?://[^\s<>"\'，。、）)】\]]+')

# 提取码:pwd=xxx 或 "提取码: xxx" / "提取码：xxx"
PWD_QUERY_PATTERN = re.compile(r'[?&]pwd=([a-zA-Z0-9]{4})')
PWD_TEXT_PATTERN = re.compile(r'提取码[:：]\s*([a-zA-Z0-9]{4})')


def _extract_links(content: str) -> list[dict]:
    """从单条消息内容抽链接 + 配对本消息里的提取码。"""
    links = []
    for url in LINK_PATTERN.findall(content):
        # 先看 URL 自带的 ?pwd=
        code_match = PWD_QUERY_PATTERN.search(url)
        if code_match:
            code = code_match.group(1)
        else:
            # 再看消息正文里独立的"提取码: xxx"
            text_match = PWD_TEXT_PATTERN.search(content)
            code = text_match.group(1) if text_match else None
        links.append({'url': url, 'extract_code': code})
    return links


def extract_all(messages: list[dict]) -> dict:
    """从 messages 数组抽取所有客观字段。返回 extracted 结构。"""
    links = []
    for idx, msg in enumerate(messages):
        content = msg.get('content', '') or ''
        for link in _extract_links(content):
            link['msg_index'] = idx
            link['sender'] = msg.get('sender')
            link['time'] = msg.get('time')
            links.append(link)
    return {'links': links, 'files': [], 'dates': [], 'meeting_codes': []}
```

- [ ] **Step 4: 运行测试,确认 4 个全过**

Run: `py -m pytest chat2work/tests/test_extractor.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add chat2work/scripts/extractor.py chat2work/tests/test_extractor.py
git commit -m "feat(extractor): 链接提取 + 提取码配对(?pwd= 不截断)"
```

---

## Task 3: 文件名提取

**Files:**
- Modify: `chat2work/scripts/extractor.py`(追加 extract_files)
- Modify: `chat2work/tests/test_extractor.py`(追加测试)

- [ ] **Step 1: 追加失败测试**

```python
def test_extract_files_multiple_extensions():
    """一条消息里多个不同后缀的文件都要抽出。"""
    result = extract_all(load_messages())
    names = [f['filename'] for f in result['files']]
    assert '实验报告模板.docx' in names
    assert 'wavego_twin_patch.zip' in names
    # 抽到的那条 msg_index 是 msg#4
    for f in result['files']:
        assert f['msg_index'] == 4
        assert f['sender'] == '张老师'


def test_extract_files_no_false_positive_on_plain_text():
    """纯闲聊消息(msg#5 "收到谢谢")不应抽到任何文件。"""
    result = extract_all(load_messages())
    for f in result['files']:
        assert f['msg_index'] != 5
```

- [ ] **Step 2: 运行测试,确认失败**

Run: `py -m pytest chat2work/tests/test_extractor.py::test_extract_files_multiple_extensions -v`
Expected: FAIL(files 为空)

- [ ] **Step 3: 实现文件提取**

在 `extractor.py` 的 `extract_all` 前追加:

```python
# 文件名:中文/字母数字 + 常见后缀。要求前面是文件名边界(非字母数字则 ok)
FILE_PATTERN = re.compile(
    r'([一-龥\w]+\.(?:zip|rar|7z|pdf|docx?|xlsx?|pptx?|py|cpp|c|java|js|ts|fbx|obj|stl|step|urdf|gha|mp4))',
    re.IGNORECASE,
)


def _extract_files(content: str) -> list[str]:
    return FILE_PATTERN.findall(content)
```

然后把 `extract_all` 改为同时填 files:

```python
def extract_all(messages: list[dict]) -> dict:
    links = []
    files = []
    for idx, msg in enumerate(messages):
        content = msg.get('content', '') or ''
        for link in _extract_links(content):
            link['msg_index'] = idx
            link['sender'] = msg.get('sender')
            link['time'] = msg.get('time')
            links.append(link)
        for filename in _extract_files(content):
            files.append({
                'filename': filename,
                'msg_index': idx,
                'sender': msg.get('sender'),
                'time': msg.get('time'),
            })
    return {'links': links, 'files': files, 'dates': [], 'meeting_codes': []}
```

- [ ] **Step 4: 运行测试,确认全过**

Run: `py -m pytest chat2work/tests/test_extractor.py -v`
Expected: PASS(6 passed)

- [ ] **Step 5: 提交**

```bash
git add chat2work/scripts/extractor.py chat2work/tests/test_extractor.py
git commit -m "feat(extractor): 文件名提取(多后缀,闲聊无误报)"
```

---

## Task 4: 日期提取(绝对 + 相对)

**Files:**
- Modify: `chat2work/scripts/extractor.py`
- Modify: `chat2work/tests/test_extractor.py`

- [ ] **Step 1: 追加失败测试**

```python
def test_extract_dates_absolute():
    """绝对日期 YYYY-MM-DD 直接抽。"""
    result = extract_all(load_messages())
    absolutes = [d for d in result['dates'] if not d['uncertain']]
    assert any(d['absolute'] == '2026-07-25' for d in absolutes)


def test_extract_dates_relative_marks_uncertain():
    """相对日期"下周交"以消息发送时间为基准转绝对,标 uncertain=True。"""
    result = extract_all(load_messages())
    # msg#6 (2026-07-15) "下周交" -> 2026-07-22(下一周)
    rels = [d for d in result['dates'] if d['uncertain']]
    assert any(d['msg_index'] == 6 for d in rels)
    next_week = next(d for d in rels if d['msg_index'] == 6)
    assert next_week['absolute'] == '2026-07-22'
    assert '下周' in next_week['raw']
```

- [ ] **Step 2: 运行测试,确认失败**

Run: `py -m pytest chat2work/tests/test_extractor.py -v`
Expected: FAIL(dates 相关 2 个)

- [ ] **Step 3: 实现日期提取**

在 `extractor.py` 追加(注意相对日期转绝对需要消息发送时间):

```python
from datetime import datetime, timedelta

# 绝对日期
ABS_DATE_PATTERN = re.compile(r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})')
# 相对:"下周X" / "本周X"
WEEKDAY_MAP = {'一': 0, '二': 1, '三': 2, '四': 3, '五': 4, '六': 5, '日': 6, '天': 6}
REL_WEEK_PATTERN = re.compile(r'(下周|本周)([一二三四五六日天])')


def _to_weekday_date(base_iso: str, weekday_cn: str) -> str:
    """base_iso 这周的第 weekday_cn 天的日期(ISO 字符串转 YYYY-MM-DD)。"""
    try:
        base = datetime.fromisoformat(base_iso)
    except ValueError:
        return ''
    target_wd = WEEKDAY_MAP[weekday_cn]
    delta = (target_wd - base.weekday()) % 7
    if delta == 0:
        delta = 7  # 同一天算"下周"的下一个
    return (base + timedelta(days=delta)).date().isoformat()


def _extract_dates(content: str, msg_time: str) -> list[dict]:
    dates = []
    # 绝对
    for raw in ABS_DATE_PATTERN.findall(content):
        normalized = raw.replace('/', '-')
        dates.append({'raw': raw, 'absolute': normalized, 'uncertain': False})
    # 相对
    for prefix, wd in REL_WEEK_PATTERN.findall(content):
        abs_date = _to_weekday_date(msg_time, wd)
        dates.append({
            'raw': f'{prefix}{wd}',
            'absolute': abs_date,
            'uncertain': True,
        })
    return dates
```

然后在 `extract_all` 循环里追加(放在 files 之后):

```python
        for d in _extract_dates(content, msg.get('time', '')):
            d['msg_index'] = idx
            dates.append(d)
```

并在函数顶部初始化 `dates = []`,返回值填上。

- [ ] **Step 4: 运行测试,确认全过**

Run: `py -m pytest chat2work/tests/test_extractor.py -v`
Expected: PASS(8 passed)

- [ ] **Step 5: 提交**

```bash
git add chat2work/scripts/extractor.py chat2work/tests/test_extractor.py
git commit -m "feat(extractor): 日期提取(绝对+相对,相对标 uncertain)"
```

---

## Task 5: 会议号提取 + CLI 入口

**Files:**
- Modify: `chat2work/scripts/extractor.py`
- Modify: `chat2work/tests/test_extractor.py`

- [ ] **Step 1: 追加失败测试**

```python
def test_extract_meeting_code():
    """腾讯会议号 460-149-615 要抽出。"""
    result = extract_all(load_messages())
    codes = [m['code'] for m in result['meeting_codes']]
    assert '460-149-615' in codes
    meeting = next(m for m in result['meeting_codes'] if m['code'] == '460-149-615')
    assert meeting['msg_index'] == 1


def test_extract_all_returns_full_structure():
    """extract_all 返回 5 个顶层 key。"""
    result = extract_all(load_messages())
    assert set(result.keys()) == {'links', 'files', 'dates', 'meeting_codes'}
```

- [ ] **Step 2: 运行测试,确认失败**

Run: `py -m pytest chat2work/tests/test_extractor.py -v`
Expected: FAIL(meeting_codes 相关)

- [ ] **Step 3: 实现会议号 + CLI**

在 `extractor.py` 追加:

```python
# 腾讯会议号:8-13 位数字(可含连字符)
MEETING_CODE_PATTERN = re.compile(r'(?:腾讯会议号|#腾讯会议)[:：]?\s*([\d-]{8,})')


def _extract_meeting_codes(content: str) -> list[str]:
    return [m.strip() for m in MEETING_CODE_PATTERN.findall(content)]
```

在 `extract_all` 循环里追加,并初始化 `meeting_codes = []`:

```python
        for code in _extract_meeting_codes(content):
            meeting_codes.append({
                'code': code,
                'msg_index': idx,
                'sender': msg.get('sender'),
                'time': msg.get('time'),
            })
```

在文件末尾追加 CLI(参照 parser/builder 风格):

```python
def main():
    ap = argparse.ArgumentParser(description='Chat2Work extractor — 客观字段规则提取')
    ap.add_argument('messages_file', help='parser 输出的 messages.json')
    ap.add_argument('-o', '--output', default='extracted.json', help='输出 JSON 路径')
    args = ap.parse_args()

    path = Path(args.messages_file)
    if not path.exists():
        print(f'错误:文件不存在 {path}', file=sys.stderr)
        sys.exit(1)

    data = json.loads(path.read_text(encoding='utf-8'))
    messages = data['messages'] if isinstance(data, dict) else data
    result = extract_all(messages)

    out_path = Path(args.output)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[*] 提取完成: {len(result["links"])} 链接, '
          f'{len(result["files"])} 文件, '
          f'{len(result["dates"])} 日期, '
          f'{len(result["meeting_codes"])} 会议号', file=sys.stderr)
    print(f'[*] 输出: {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: 运行测试,确认全过**

Run: `py -m pytest chat2work/tests/test_extractor.py -v`
Expected: PASS(10 passed)

- [ ] **Step 5: 手动跑 CLI 验证**

Run: `PYTHONIOENCODING=utf-8 py chat2work/scripts/extractor.py chat2work/tests/messages.json -o .chat2work_tmp/extracted_sample.json`
Expected: stderr 打印"提取完成: X 链接 ...",输出文件存在。

- [ ] **Step 6: 提交**

```bash
git add chat2work/scripts/extractor.py chat2work/tests/test_extractor.py
git commit -m "feat(extractor): 会议号提取 + CLI 入口"
```

---

## Task 6: prompt 改造(LLM 读 extracted,不自己扫链接)

**Files:**
- Modify: `chat2work/prompts/course-maker.md`

- [ ] **Step 1: 改 prompt 的 Extraction Rules 和 Output Format**

在 `prompts/course-maker.md` 的 "## 3. 参考资料(链接)" 章节开头插入一段说明,明确链接已预置:

把现有的:

```markdown
## 3. 参考资料（链接）
- 提取所有 http(s) 链接
- 每条链接记录：url、谁发的、什么时候发的、为什么发（看上下文）
- 公众号文章、GitHub 仓库、Wiki、商品页等都要收录
```

改为:

```markdown
## 3. 参考资料（链接）

**重要:链接、文件、提取码、会议号已由 extractor 规则预抽好,在输入的 `extracted` 字段里给出。你不要自己重新扫描消息抽取链接,直接引用 `extracted.links` 即可。** 你只负责给每条链接标语义:

- 读 `extracted.links` 里的每条 url,看它在原文里的上下文,标 `why`(这是干嘛的:产品页/网盘/会议/登记表/参考文章)
- `extracted.links` 里没有的链接不得编造;若有遗漏也不要补(规则保证不丢)
- 每条链接记录:url、sender、time、why,`src_msg` 用 `msg#N`(N 来自 extracted.links 的 msg_index)
- 文件同理:用 `extracted.files`,标 note(这文件是干嘛的)
- 日期用 `extracted.dates`(已含 uncertain 标记),归到对应 task
```

- [ ] **Step 2: 改 Output Format 的 JSON 示例**

在 JSON 示例里,给 refs 加一行说明 `// url/extract_code 来自 extracted.links,why 由你填`,并在顶部加一段提示输入结构:

在 `# Output Format` 章节顶部、"输出严格 JSON" 那行之后插入:

```markdown
> **输入预置**:pipeline 会把 `extracted.json`(extractor 规则预抽的 links/files/dates/meeting_codes)和 messages.json 一起给你。refs 字段的 url/extract_code/src_msg 直接从 extracted.links 取,你只补 why/title。
```

- [ ] **Step 3: 提交**

```bash
git add chat2work/prompts/course-maker.md
git commit -m "docs(prompt): course-maker 读 extracted 预置字段,LLM 只标语义不扫链接"
```

---

## Task 7: builder 接入 extracted.json

**Files:**
- Modify: `chat2work/scripts/builder.py`

- [ ] **Step 1: 读现有 builder 的 build_course_workspace,定位链接库渲染处**

读 `chat2work/scripts/builder.py:150-285`(build_course_workspace 函数)。注意 context 里有 `refs` 字段(来自 llm_output.refs),链接库模板 `02_参考资料/链接库.md.tmpl` 用 `refs` 渲染主表。

- [ ] **Step 2: 让 builder 支持 extracted_file 参数**

在 `build_course_workspace` 函数顶部(local 变量区,约 line 159 后)追加读取 extracted:

```python
    extracted_file = llm_output.get('extracted_file')
    extracted = {}
    if extracted_file and Path(extracted_file).exists():
        try:
            extracted = json.loads(Path(extracted_file).read_text(encoding='utf-8'))
            print(f"  [+] 载入 extracted: "
                  f"{len(extracted.get('links', []))} 链接", file=sys.stderr)
        except Exception as e:
            print(f"  [!] extracted 载入失败: {e}", file=sys.stderr)
```

- [ ] **Step 3: 把 extracted.links 与 llm_output.refs 合并(链接不丢)**

在上一段之后追加合并逻辑(extracted.links 为主表,refs 只补 why/title):

```python
    # 链接主表:以 extracted.links 为准(规则保证不丢),refs 只贡献语义字段
    merged_links = []
    ref_by_url = {r.get('url'): r for r in refs if r.get('url')}
    for link in extracted.get('links', []):
        url = link.get('url')
        ref = ref_by_url.get(url, {})
        merged_links.append({
            'url': url,
            'title': ref.get('title', ''),
            'sender': link.get('sender') or ref.get('sender', ''),
            'time': link.get('time') or ref.get('time', ''),
            'why': ref.get('why', '[未标注]'),
            'extract_code': link.get('extract_code'),
            'src_msg': f"msg#{link.get('msg_index')}" if link.get('msg_index') is not None else (ref.get('src_msg', '')),
        })
    # extracted 缺失时退回 refs(v1 行为,不破坏)
    if not merged_links:
        merged_links = refs
```

然后把 context 里的 `'refs': refs` 改为 `'refs': merged_links`。

- [ ] **Step 4: 加 CLI 参数**

在 `main()` 的 argparse 区(约 line 313)追加:

```python
    ap.add_argument('--extracted-file', help='extractor 输出的 extracted.json 路径')
```

在解析 llm_output 后(约 line 322 后)追加:

```python
    if args.extracted_file:
        llm_output['extracted_file'] = args.extracted_file
```

- [ ] **Step 5: 用 21 条样例端到端验证(回归)**

构造一个最小 llm_output(只含 project_name + 一个空 refs),跑 builder + extracted:

Run:
```bash
PYTHONIOENCODING=utf-8 py chat2work/scripts/extractor.py chat2work/tests/messages.json -o .chat2work_tmp/ext.json
PYTHONIOENCODING=utf-8 py chat2work/scripts/builder.py chat2work/tests/llm_output_mock.json --extracted-file .chat2work_tmp/ext.json --target-dir .chat2work_tmp/build_test
```
Expected: stderr 显示"载入 extracted: 3 链接",生成的 `链接库.md` 包含 3 条链接(规则抽出的)。

打开 `.chat2work_tmp/build_test/课程设计-*/02_参考资料/链接库.md` 确认链接数 ≥ 3 且 URL 完整。

- [ ] **Step 6: 提交**

```bash
git add chat2work/scripts/builder.py
git commit -m "feat(builder): 接入 extracted.json,链接库以规则抽取为主表不丢"
```

---

## Task 8: 端到端回归(147 条真实数据)

**Files:** 无新建,验证用。

- [ ] **Step 1: 对 147 条 FreeDo3D 跑 extractor**

Run: `PYTHONIOENCODING=utf-8 py chat2work/scripts/extractor.py "weChatDataAnalysis/chat_log/real_test_json/conversations/0001_õ©ôõ©Üի×õ¦á2026_58040226786@chatroom_b8c6158e/messages.json" -o .chat2work_tmp/ext_147.json`
Expected: stderr 报"X 链接",X 应 ≥ 19(之前规则手测是 19+)。

- [ ] **Step 2: 验收:链接数 ≥ 19**

```bash
py -c "import json; d=json.load(open('.chat2work_tmp/ext_147.json',encoding='utf-8')); print('links:', len(d['links'])); [print(l['url'][:80], '| code:', l['extract_code']) for l in d['links'][:5]]"
```
Expected: 打印 `links: 19`(或更多),前 5 条含百度网盘链接且 extract_code 非 None。

- [ ] **Step 3: 验收:21 条机器狗样例不退化**

Run: `py chat2work/scripts/extractor.py chat2work/tests/messages.json -o .chat2work_tmp/ext_21.json && py -c "import json; print('links:', len(json.load(open('.chat2work_tmp/ext_21.json',encoding='utf-8'))['links']))"`
Expected: `links: 3`(不退化)。

- [ ] **Step 4: 清理临时产物**

```bash
rm -f .chat2work_tmp/ext.json .chat2work_tmp/ext_147.json .chat2work_tmp/ext_21.json
rm -rf .chat2work_tmp/build_test
```

- [ ] **Step 5: 更新 skill 文档(SKILL.md 工作流加 extractor 步骤)**

读 `chat2work/SKILL.md` 的"完整工作流"章节,在第 2 步(场景路由)和第 4 步(LLM 处理)之间插入新步骤:

在 `3. **加载 prompt 模板**...` 之后插入:

```markdown
3.5 **规则提取客观字段**:调用 `python scripts/extractor.py messages.json -o extracted.json`
   - 纯规则全量抽取链接/文件/提取码/日期/会议号,100% 不丢
   - 产出的 extracted.json 喂给 LLM 作输入,LLM 不再自己扫链接
```

并把第 5 步 builder 调用改为带 `--extracted-file extracted.json`。

- [ ] **Step 6: 提交**

```bash
git add chat2work/SKILL.md
git commit -m "docs(skill): 工作流加入 extractor 步骤"
```

---

## Self-Review

**1. Spec coverage:**
- 链接提取(保留 ?pwd=)→ Task 2 ✓
- 提取码配对 → Task 2 ✓
- 文件名 → Task 3 ✓
- 日期(绝对+相对 uncertain) → Task 4 ✓
- 会议号 → Task 5 ✓
- extractor.py CLI → Task 5 ✓
- prompt 改造(LLM 读 extracted) → Task 6 ✓
- builder 接入(链接库用 extracted 主表) → Task 7 ✓
- 147条回归 ≥19 链接 + 21条不退化 → Task 8 ✓
- 开放问题1(无语义的链接是否进库)→ Task 7 merged_links 里 why=`[未标注]`,进库 ✓
- 开放问题2(相对时间基准)→ Task 4 用消息自身发送时间 ✓

**2. Placeholder scan:** 无 TBD/TODO。每个代码步骤都给了完整代码。

**3. Type consistency:**
- `extract_all` 返回 `{links, files, dates, meeting_codes}` 贯穿 Task 2-5 ✓
- links 条目字段 `{url, extract_code, msg_index, sender, time}` 全程一致 ✓
- builder Task 7 的 merged_links 字段 `{url, title, sender, time, why, extract_code, src_msg}` 与链接库模板期望的 refs 字段兼容 ✓
- `msg_index` vs `src_msg`:extractor 用 msg_index(int),builder 合并时转成 `msg#N` 字符串 ✓

**注意点:**
- Task 4 相对日期 "下周三" 在 base 是周三时 delta=0→7(算下下周的同一天),已处理。若 base 已过该 weekday,delta 为正数指向本周剩余的那个,语义上"下周X"可能略偏——但 prompt 已要求 LLM 对 uncertain 日期加 deadline_uncertain,Builder 会标⚠️,可接受。
- Task 7 依赖 `llm_output_mock.json` 已存在于 chat2work/tests/——Step 5 前需确认该文件存在,若不存在则用 Task 1 fixtures 同源的最小 mock。
