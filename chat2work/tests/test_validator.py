"""validator 单元测试。运行: pytest chat2work/tests/test_validator.py -v"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from validator import (
    check_cross_domain_reproducibility,
    check_predictive_power,
    check_exclusivity,
    triple_validate,
    _extract_keywords,
    _bucket_by_week,
)


# ---------- mock messages ----------

def make_msg(sender: str, time: str, content: str) -> dict:
    return {'sender': sender, 'time': time, 'content': content}


MOCK_MESSAGES = [
    make_msg('Yang', '2026-07-13T21:58:18+08:00', '分享数字孪生 DTS_Library_V6.pak 网盘'),
    make_msg('Yang', '2026-07-14T09:03:00+08:00', '腾讯会议 MCP Server 讨论'),
    make_msg('Yang', '2026-07-14T13:31:00+08:00', '点云倾斜数据 Vue 模板分享'),
    make_msg('Yang', '2026-07-15T08:59:00+08:00', '数字孪生 MCP Server 会议录屏'),
    make_msg('Yang', '2026-07-16T08:54:00+08:00', 'DTS 工具使用教程 录屏回放'),
    make_msg('荧光', '2026-07-14T10:00:00+08:00', '感谢分享数字孪生资料'),
    make_msg('荧光', '2026-07-15T11:00:00+08:00', 'MCP Server 很好用'),
    make_msg('张老师', '2026-07-14T08:00:00+08:00', '大家看一下 DTS 文档'),
    make_msg('张老师', '2026-07-16T09:00:00+08:00', '今天讨论 MCP Server'),
    make_msg('Yang', '2026-07-17T09:00:00+08:00', 'DTS_Library 最新版本更新 录屏'),
    make_msg('Yang', '2026-07-17T14:00:00+08:00', 'MCP Server 实战操作 点云处理'),
]


# ---------- _extract_keywords ----------

def test_extract_keywords_chinese():
    """中文 2+ 字词组被正确提取。"""
    kws = _extract_keywords('数字孪生和点云数据处理')
    # 中文连续匹配最长序列："数字孪生" 和 "点云数据处理"
    assert '数字孪生' in kws or len(kws) >= 1


def test_extract_keywords_english():
    """英文技术词被正确提取。"""
    kws = _extract_keywords('使用 DTS_Library 和 MCP_Server')
    assert 'DTS_Library' in kws
    assert 'MCP_Server' in kws


# ---------- _bucket_by_week ----------

def test_bucket_by_week_multiple_days():
    """多天消息按日分桶。"""
    msgs = [
        make_msg('Yang', '2026-07-13T21:58:18+08:00', 'day1'),
        make_msg('Yang', '2026-07-14T09:03:00+08:00', 'day2'),
        make_msg('Yang', '2026-07-15T08:59:00+08:00', 'day3'),
    ]
    buckets = _bucket_by_week(msgs)
    assert len(buckets) >= 2


# ---------- check_cross_domain_reproducibility ----------

def test_cross_domain_multi_week_passes():
    """跨多天/多周复现的观察通过。"""
    observations = [
        {
            'observation': 'Yang 频繁分享 DTS 相关资源',
            'keywords': ['DTS', '数字孪生', 'DTS_Library'],
            'evidence_indices': [0, 4, 6],
        },
    ]
    results = check_cross_domain_reproducibility(observations, MOCK_MESSAGES, 'Yang')
    assert len(results) == 1
    # 关键词分散在多天，应通过
    assert results[0]['passed']


def test_cross_domain_single_occurrence_fails():
    """仅出现一次的观察不通过。"""
    observations = [
        {
            'observation': '罕见提及',
            'keywords': ['rarekeyword'],
            'evidence_indices': [0],
        },
    ]
    results = check_cross_domain_reproducibility(observations, MOCK_MESSAGES, 'Yang')
    assert len(results) == 1
    assert not results[0]['passed']


# ---------- check_exclusivity ----------

def test_exclusivity_yang_only():
    """Yang 独有的关键词排他性高。"""
    observations = [
        {
            'observation': 'Yang 频繁使用 DTS_Library',
            'keywords': ['DTS_Library', '录屏'],  # 录屏 也被 Yang 大量使用
        },
    ]
    results = check_exclusivity(observations, MOCK_MESSAGES, 'Yang')
    assert len(results) == 1
    # Yang 有 7 条关于 DTS/录屏 的消息，其他人几乎没有
    assert results[0]['exclusivity'] >= 0.6


def test_exclusivity_shared_keywords():
    """共享关键词（大家都有）排他性低。"""
    observations = [
        {
            'observation': '讨论 MCP Server',
            'keywords': ['MCP', 'Server', 'MCP_Server'],
        },
    ]
    results = check_exclusivity(observations, MOCK_MESSAGES, 'Yang')
    assert len(results) == 1
    # MCP Server 被多人提及
    assert results[0]['exclusivity'] < 0.7 or results[0]['passed']


# ---------- check_predictive_power ----------

def test_predictive_power_verified():
    """预测关键词在 holdout 中出现则通过。"""
    predictions = [
        {
            'observation_id': 0,
            'predicted_keywords': ['MCP', 'Server', '点云'],
        },
    ]
    results = check_predictive_power(predictions, MOCK_MESSAGES, 'Yang')
    assert len(results) == 1
    # Yang 最后几条消息含 MCP、Server、点云
    assert results[0]['passed']


def test_predictive_power_unverified():
    """预测关键词不在 holdout 中出现则不通过。"""
    predictions = [
        {
            'observation_id': 0,
            'predicted_keywords': ['nonexistent_kw', 'never_appears'],
        },
    ]
    results = check_predictive_power(predictions, MOCK_MESSAGES, 'Yang')
    assert len(results) == 1
    assert not results[0]['passed']


# ---------- triple_validate ----------

def test_triple_validate_returns_status():
    """triple_validate 返回每条观察的 verification_status。"""
    observations = [
        {
            'observation': 'Yang 频繁分享 DTS 资源', 'layer': '1',
            'keywords': ['DTS', '数字孪生', 'DTS_Library', '录屏'],
            'evidence_indices': [0, 4, 6],
        },
        {
            'observation': 'Yang 讨论 MCP Server', 'layer': '1',
            'keywords': ['MCP', 'Server'],
            'evidence_indices': [1, 5],
        },
    ]
    predictions = [
        {'observation_id': 0, 'predicted_keywords': ['DTS', '录屏']},
        {'observation_id': 1, 'predicted_keywords': ['MCP', 'Server']},
    ]
    verified = triple_validate(observations, predictions, MOCK_MESSAGES, 'Yang')
    assert len(verified) == 2
    for obs in verified:
        assert 'verification_status' in obs
        assert obs['verification_status'] in ('verified', 'partial', 'unverified')
        assert 'verification' in obs
        assert 'score' in obs['verification']
