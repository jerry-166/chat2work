"""router 单元测试。运行: pytest chat2work/tests/test_router.py -v"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from router import find_target

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / 'scripts'
ROUTER_PY = SCRIPTS_DIR / 'router.py'
TESTS_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable


# ---------- mock messages（归一化后的格式，含 sender 字段） ----------

def make_msg(sender: str, time: str, content: str = "test") -> dict:
    return {
        'sender': sender,
        'sender_id': f'wxid_{sender.lower()}',
        'time': time,
        'content': content,
        'msg_type': 'text',
        'meta': {},
    }


MOCK_MESSAGES = [
    make_msg('Yang', '2026-07-13T21:58:18+08:00', '通过网盘分享的文件：DTS_Library_V6.pak'),
    make_msg('Yang', '2026-07-14T09:03:00+08:00', '辣椒油 邀请您参加腾讯会议'),
    make_msg('Yang', '2026-07-14T13:31:00+08:00', '会议录屏'),
    make_msg('张老师', '2026-07-13T22:00:00+08:00', '收到谢谢'),
    make_msg('张三老师', '2026-07-14T08:00:00+08:00', '好的'),
    make_msg('荧光', '2026-07-14T10:00:00+08:00', '感谢分享'),
]


# ---------- find_target 单元测试 ----------

def test_find_target_exact_match():
    """精确匹配：sender == target_name，返回 actual_name == requested。"""
    result = find_target(MOCK_MESSAGES, 'Yang')
    assert result['found'] is True
    assert result['requested'] == 'Yang'
    assert result['actual_name'] == 'Yang'
    assert result['message_count'] == 3


def test_find_target_fuzzy_match():
    """模糊匹配：'张老师' 匹配 '张三老师'（target_name in sender）。"""
    result = find_target(MOCK_MESSAGES, '张老师')
    # 注意：精确匹配优先，'张老师' 在 MOCK_MESSAGES 中存在（第 4 条）
    assert result['found'] is True
    assert result['actual_name'] == '张老师'
    assert result['message_count'] == 1


def test_find_target_fuzzy_match_only():
    """仅模糊匹配：'张三' 匹配 '张三老师'（target_name in sender 的子串匹配）。"""
    # 移除精确的 '张三老师'，用 '张三' 做模糊匹配
    msgs_with_zhangsan = [
        make_msg('张三老师', '2026-07-14T08:00:00+08:00', '好的'),
        make_msg('Yang', '2026-07-14T09:00:00+08:00', '分享'),
    ]
    result = find_target(msgs_with_zhangsan, '张三')
    # '张三' in '张三老师' → True
    assert result['found'] is True
    assert result['actual_name'] == '张三老师'
    assert result['message_count'] == 1


def test_find_target_not_found():
    """未找到：返回 found=False + available_senders 列表。"""
    result = find_target(MOCK_MESSAGES, '不存在的人')
    assert result['found'] is False
    assert result['requested'] == '不存在的人'
    assert 'available_senders' in result
    assert 'Yang' in result['available_senders']
    assert '张老师' in result['available_senders']


def test_find_target_time_range():
    """time_range 字段正确反映目标人物的最早和最晚消息时间。"""
    result = find_target(MOCK_MESSAGES, 'Yang')
    assert result['found'] is True
    assert result['time_range']['start'] == '2026-07-13T21:58:18+08:00'
    assert result['time_range']['end'] == '2026-07-14T13:31:00+08:00'


# ---------- main() CLI 集成测试 ----------

def _run_router(messages_file: Path, *args) -> subprocess.CompletedProcess:
    """运行 router.py CLI，返回 CompletedProcess。"""
    return subprocess.run(
        [PYTHON, str(ROUTER_PY), str(messages_file), *args],
        capture_output=True, text=True, encoding='utf-8'
    )


def _write_messages_json(tmp_path: Path, messages: list) -> Path:
    """把 mock messages 写成 messages.json（router 期望 {messages: [...]} 结构）。"""
    f = tmp_path / 'messages.json'
    f.write_text(json.dumps({'messages': messages}, ensure_ascii=False), encoding='utf-8')
    return f


def test_router_mode_course_default(tmp_path):
    """不指定 --mode 时默认 course-maker。"""
    msg_file = _write_messages_json(tmp_path, MOCK_MESSAGES)
    out_file = tmp_path / 'scene.json'
    result = _run_router(msg_file, '-o', str(out_file))
    assert result.returncode == 0
    scene = json.loads(out_file.read_text(encoding='utf-8'))
    assert scene['mode'] == 'course-maker'
    assert scene['detail']['source'] == 'default'


def test_router_mode_distill_with_target(tmp_path):
    """--mode distill --target Yang 正确路由。"""
    msg_file = _write_messages_json(tmp_path, MOCK_MESSAGES)
    out_file = tmp_path / 'scene.json'
    result = _run_router(msg_file, '--mode', 'distill', '--target', 'Yang', '-o', str(out_file))
    assert result.returncode == 0
    scene = json.loads(out_file.read_text(encoding='utf-8'))
    assert scene['mode'] == 'person-distiller'
    assert scene['target']['found'] is True
    assert scene['target']['actual_name'] == 'Yang'
    assert scene['target']['message_count'] == 3


def test_router_distill_no_target_auto_pick(tmp_path):
    """distill 无 --target 时自动选最活跃发言者（Yang 有 3 条，最多）。"""
    msg_file = _write_messages_json(tmp_path, MOCK_MESSAGES)
    out_file = tmp_path / 'scene.json'
    result = _run_router(msg_file, '--mode', 'distill', '-o', str(out_file))
    assert result.returncode == 0
    scene = json.loads(out_file.read_text(encoding='utf-8'))
    assert scene['target']['found'] is True
    assert scene['target']['actual_name'] == 'Yang'
    assert '自动选最活跃发言者' in result.stderr


def test_router_distill_target_not_in_messages_exits(tmp_path):
    """target 不存在时 sys.exit(1)，stderr 提示可用发送者。"""
    msg_file = _write_messages_json(tmp_path, MOCK_MESSAGES)
    out_file = tmp_path / 'scene.json'
    result = _run_router(msg_file, '--mode', 'distill', '--target', '不存在', '-o', str(out_file))
    assert result.returncode == 1
    assert '找不到' in result.stderr
    assert '可用发送者' in result.stderr


def test_router_output_has_no_legacy_score_fields(tmp_path):
    """回归用例：scene.json 输出不含旧版自动路由字段（course_score/distill_score/course_hits/distill_hits）。"""
    msg_file = _write_messages_json(tmp_path, MOCK_MESSAGES)
    out_file = tmp_path / 'scene.json'
    result = _run_router(msg_file, '--mode', 'distill', '--target', 'Yang', '-o', str(out_file))
    assert result.returncode == 0
    scene = json.loads(out_file.read_text(encoding='utf-8'))
    # 防止旧版自动路由回潮
    assert 'course_score' not in scene
    assert 'distill_score' not in scene
    assert 'course_hits' not in scene
    assert 'distill_hits' not in scene
    assert 'top_sender' not in scene
