"""端到端测试：parser → router → builder 完整流程。运行: pytest chat2work/tests/test_e2e_distill.py -v"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / 'scripts'
TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / 'fixtures'
SKILL_DIR = TESTS_DIR.parent
PYTHON = sys.executable

PARSER_PY = SCRIPTS_DIR / 'parser.py'
ROUTER_PY = SCRIPTS_DIR / 'router.py'
BUILDER_PY = SCRIPTS_DIR / 'builder.py'

# 真实数据 fixture（WechatDataAnalysis 原始 JSON 格式，29 条含 Yang 20 条）
REAL_DATA_FIXTURE = FIXTURES_DIR / 'distill_yang_messages.json'
# Golden LLM 输出（模拟 LLM 蒸馏结果）
GOLDEN_LLM_OUTPUT = FIXTURES_DIR / 'distill_llm_output.json'


def _run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    """运行命令，捕获输出。"""
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', **kwargs)


def test_e2e_real_yang_distillation(tmp_path):
    """端到端：用真实 147 条数据裁剪的 fixture 跑 parser→router→builder，产出 so-Yang.md。

    流程：
    1. parser 解析原始 JSON → 归一化 messages.json
    2. router 路由 --mode distill --target Yang → scene.json
    3. (模拟 LLM 步骤，用 golden llm_output.json)
    4. builder 渲染 → so-Yang.md
    """
    # Step 1: parser 解析原始数据
    messages_json = tmp_path / 'messages.json'
    result = _run([
        PYTHON, str(PARSER_PY), str(REAL_DATA_FIXTURE),
        '-o', str(messages_json)
    ])
    assert result.returncode == 0, f"parser 失败: {result.stderr}"
    parsed = json.loads(messages_json.read_text(encoding='utf-8'))
    assert parsed['total_messages'] > 0
    # Yang 应该在发送者列表中
    assert 'Yang' in parsed['senders']
    assert parsed['senders']['Yang'] >= 15  # 至少 15 条（fixture 含 20 条 Yang 消息）

    # Step 2: router 路由到 distill + Yang
    scene_json = tmp_path / 'scene.json'
    result = _run([
        PYTHON, str(ROUTER_PY), str(messages_json),
        '--mode', 'distill', '--target', 'Yang',
        '-o', str(scene_json)
    ])
    assert result.returncode == 0, f"router 失败: {result.stderr}"
    scene = json.loads(scene_json.read_text(encoding='utf-8'))
    assert scene['mode'] == 'person-distiller'
    assert scene['target']['found'] is True
    assert scene['target']['actual_name'] == 'Yang'
    assert scene['target']['message_count'] >= 15

    # Step 3: (模拟 LLM 步骤) 用 golden llm_output.json
    # Golden 已包含 Yang 的蒸馏结果，直接喂给 builder
    llm_output = json.loads(GOLDEN_LLM_OUTPUT.read_text(encoding='utf-8'))
    # 同步 message_count 到 router 实际产出的值
    llm_output['message_count'] = scene['target']['message_count']
    llm_output_for_e2e = tmp_path / 'llm_output.json'
    llm_output_for_e2e.write_text(
        json.dumps(llm_output, ensure_ascii=False, indent=2), encoding='utf-8'
    )

    # Step 4: builder 渲染 → so-Yang.md
    result = _run([
        PYTHON, str(BUILDER_PY), str(llm_output_for_e2e),
        '--target-dir', str(tmp_path),
        '--mode', 'distill',
        '--skill-dir', str(SKILL_DIR)
    ])
    assert result.returncode == 0, f"builder 失败: {result.stderr}"

    # 验证产物
    soul_md = tmp_path / 'so-Yang.md'
    assert soul_md.exists(), "so-Yang.md 未生成"
    content = soul_md.read_text(encoding='utf-8')

    # 文件 > 50 行
    assert len(content.split('\n')) > 50, f"SOUL.md 行数过少: {len(content.split('\n'))}"

    # frontmatter 含 5 个必需字段
    assert content.startswith('---\n')
    end = content.index('\n---\n', 4)
    frontmatter = content[4:end]
    for field in ['name:', 'summary:', 'distilled_from:', 'distilled_at:', 'target_actual_name:', 'message_count:', 'distill_version:']:
        assert field in frontmatter, f"frontmatter 缺字段: {field}"

    # 含 6 层标题 + 辅助信息 + 使用建议 + 溯源（v2.0 结构）
    v2_blocks = ['Layer 0', 'Layer 1', 'Layer 2', 'Layer 3', 'Layer 4', 'Layer 5',
                 '辅助信息', '使用建议', '诚实边界声明', '溯源']
    for block in v2_blocks:
        assert block in content, f"SOUL.md 缺关键区块: {block}"

    # 至少 3 处附原文示例（含 Yang 的特征内容）
    yang_signatures = ['DTS_Library', '辣椒油', '腾讯会议', 'MCP Server', '网盘分享']
    signature_count = sum(1 for s in yang_signatures if s in content)
    assert signature_count >= 3, f"原文示例不足: {signature_count} 处"


def test_e2e_small_dataset_warning(tmp_path):
    """< 10 条消息时 parser 打印"消息太少"警告但不崩溃。"""
    # 构造 < 10 条消息的 txt 文件
    small_txt = tmp_path / 'small.txt'
    small_txt.write_text(
        '[2026-07-13 21:58:18] Yang(wxid_yang001): 第一条消息\n'
        '[2026-07-13 22:00:00] 张老师(wxid_zhang): 第二条\n'
        '[2026-07-13 22:01:00] Yang(wxid_yang001): 第三条\n'
        '[2026-07-13 22:02:00] 荧光(wxid_yg): 第四条\n',
        encoding='utf-8'
    )

    out_json = tmp_path / 'messages.json'
    result = _run([
        PYTHON, str(PARSER_PY), str(small_txt),
        '-o', str(out_json)
    ])
    # 不崩溃（returncode 0）
    assert result.returncode == 0
    # stderr 含"消息太少"或"少于"警告
    assert '少' in result.stderr or '警告' in result.stderr
    # 产物仍生成
    parsed = json.loads(out_json.read_text(encoding='utf-8'))
    assert parsed['total_messages'] == 4
