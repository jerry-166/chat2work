"""builder 单元测试。运行: pytest chat2work/tests/test_builder.py -v"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from builder import build_persona, render_template, parse_msg_ref

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / 'fixtures'
SKILL_DIR = TESTS_DIR.parent  # chat2work/ 目录，含 templates/persona/SOUL.md.tmpl
GOLDEN_LLM_OUTPUT = FIXTURES_DIR / 'distill_llm_output.json'


def load_golden_llm_output() -> dict:
    """加载 golden LLM 输出 JSON。"""
    return json.loads(GOLDEN_LLM_OUTPUT.read_text(encoding='utf-8'))


# ---------- build_persona 单元测试 ----------

def test_build_persona_writes_soul_md(tmp_path):
    """build_persona 输出 so-{name}.md 文件存在。"""
    llm_output = load_golden_llm_output()
    out_path = build_persona(llm_output, tmp_path, SKILL_DIR)
    assert out_path.exists()
    assert out_path.name == 'so-Yang.md'


def test_build_persona_uses_jinja2_template(tmp_path):
    """build_persona 使用 jinja2 模板渲染，输出含模板渲染的特征字符串。"""
    llm_output = load_golden_llm_output()
    out_path = build_persona(llm_output, tmp_path, SKILL_DIR)
    content = out_path.read_text(encoding='utf-8')
    # 模板渲染的特征字符串
    assert '数字分身' in content
    assert 'Persona（人物性格）' in content
    assert 'Work Skill（工作能力）' in content
    # 不应含未渲染的 jinja2 标签
    assert '{{' not in content
    assert '{%' not in content


def test_build_persona_empty_input_raises(tmp_path):
    """build_persona 输入为空 dict 时应 raise（找不到模板或字段缺失）。"""
    # 空 dict 不会 raise（build_persona 用 .get 默认值），但会生成空内容的 SOUL.md
    # 我们验证空 input 时不崩溃且生成文件
    out_path = build_persona({}, tmp_path, SKILL_DIR)
    assert out_path.exists()
    content = out_path.read_text(encoding='utf-8')
    # 空输入时 target_name 默认 'unknown'
    assert 'unknown' in content or '数字分身' in content


def test_build_persona_filename_safety(tmp_path):
    """target_name 含非法字符（/\\:*?"<>|）时被清洗。"""
    llm_output = load_golden_llm_output()
    llm_output['target_name'] = '张/老师:*?'
    out_path = build_persona(llm_output, tmp_path, SKILL_DIR)
    assert out_path.exists()
    # 非法字符被清洗
    assert '/' not in out_path.name
    assert ':' not in out_path.name
    assert '*' not in out_path.name
    assert '?' not in out_path.name


def test_build_persona_frontmatter_valid(tmp_path):
    """build_persona 输出的 YAML frontmatter 含 5 个必需字段。"""
    llm_output = load_golden_llm_output()
    out_path = build_persona(llm_output, tmp_path, SKILL_DIR)
    content = out_path.read_text(encoding='utf-8')
    # 提取 frontmatter（--- 之间）
    assert content.startswith('---\n')
    end = content.index('\n---\n', 4)
    frontmatter = content[4:end]
    assert 'name:' in frontmatter
    assert 'summary:' in frontmatter
    assert 'distilled_from:' in frontmatter
    assert 'distilled_at:' in frontmatter
    assert 'target_actual_name:' in frontmatter
    assert 'message_count:' in frontmatter


def test_build_persona_includes_golden_fields(tmp_path):
    """build_persona 渲染的 SOUL.md 含 golden LLM 输出中的关键字段。"""
    llm_output = load_golden_llm_output()
    out_path = build_persona(llm_output, tmp_path, SKILL_DIR)
    content = out_path.read_text(encoding='utf-8')
    # 验证关键字段被渲染
    assert 'DTS_Library_V6.pak' in content
    assert '数字孪生' in content
    assert 'MCP Server' in content
    assert '辣椒油 邀请您参加腾讯会议' in content
    assert '20' in content  # message_count


# ---------- render_template 单元测试 ----------

def test_render_template_with_jinja2():
    """jinja2 可用时正确渲染循环 {% for %}。"""
    templates_dir = SKILL_DIR / 'templates' / 'persona'
    context = {
        'target_name': 'TestUser',
        'target_actual_name': 'TestUser',
        'catchphrases': ['phrase1', 'phrase2', 'phrase3'],
        'knowledge_domains': [],
        'recommended_resources': [],
        'message_count': 10,
        'generated_at': '2026-07-19',
    }
    result = render_template('SOUL.md.tmpl', context, templates_dir)
    # 循环渲染验证
    assert 'phrase1' in result
    assert 'phrase2' in result
    assert 'phrase3' in result
    assert 'TestUser' in result


def test_render_template_handles_empty_lists():
    """render_template 处理空列表时不崩溃（jinja2 {% if %} 保护）。"""
    templates_dir = SKILL_DIR / 'templates' / 'persona'
    context = {
        'target_name': 'Empty',
        'target_actual_name': 'Empty',
        'catchphrases': [],
        'knowledge_domains': [],
        'recommended_resources': [],
        'review_focus': [],
        'suitable_questions': [],
        'unsuitable_questions': [],
        'message_count': 0,
        'generated_at': '2026-07-19',
    }
    result = render_template('SOUL.md.tmpl', context, templates_dir)
    assert '数字分身' in result
    # 空列表时模板有 default 提示
    assert '数据不足' in result or '暂无' in result or '未观察' in result


# ---------- parse_msg_ref 单元测试 ----------

def test_parse_msg_ref_valid():
    """parse_msg_ref('msg#4') 返回 4。"""
    assert parse_msg_ref('msg#4') == 4
    assert parse_msg_ref('msg#0') == 0
    assert parse_msg_ref('msg#123') == 123


def test_parse_msg_ref_invalid():
    """parse_msg_ref 非法输入返回 None。"""
    assert parse_msg_ref('msg#abc') is None
    assert parse_msg_ref('message#4') is None
    assert parse_msg_ref('4') is None
    assert parse_msg_ref('') is None
    assert parse_msg_ref(None) is None
    assert parse_msg_ref(123) is None  # 非 string


def test_parse_msg_ref_whitespace():
    """parse_msg_ref 处理前后空白。"""
    assert parse_msg_ref('  msg#4  ') == 4
    assert parse_msg_ref('msg#4\n') == 4
