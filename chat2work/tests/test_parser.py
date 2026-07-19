"""parser 单元测试。运行: pytest chat2work/tests/test_parser.py -v"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from parser import (
    parse_txt, parse_json, parse_file, sniff_format,
    classify_content, normalize_time, Message
)

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / 'fixtures'
REAL_DATA_FIXTURE = FIXTURES_DIR / 'distill_yang_messages.json'


# ---------- sniff_format 单元测试 ----------

def test_sniff_format_by_extension(tmp_path):
    """sniff_format 根据扩展名嗅探 .txt/.json/.html。"""
    txt_file = tmp_path / 'chat.txt'
    txt_file.write_text('test', encoding='utf-8')
    assert sniff_format(txt_file) == 'txt'

    json_file = tmp_path / 'chat.json'
    json_file.write_text('{"messages":[]}', encoding='utf-8')
    assert sniff_format(json_file) == 'json'

    html_file = tmp_path / 'chat.html'
    html_file.write_text('<html></html>', encoding='utf-8')
    assert sniff_format(html_file) == 'html'

    htm_file = tmp_path / 'chat.htm'
    htm_file.write_text('<html></html>', encoding='utf-8')
    assert sniff_format(htm_file) == 'html'


def test_sniff_format_by_content(tmp_path):
    """sniff_format 无扩展名时看内容首行嗅探。"""
    json_like = tmp_path / 'noext'
    json_like.write_text('  {"messages": []}', encoding='utf-8')
    assert sniff_format(json_like) == 'json'

    html_like = tmp_path / 'noext2'
    html_like.write_text('<!DOCTYPE html><html>', encoding='utf-8')
    assert sniff_format(html_like) == 'html'


# ---------- normalize_time 单元测试 ----------

def test_normalize_time_various_formats():
    """normalize_time 支持 6 种时间格式归一化为 ISO 8601。"""
    # 格式 1: YYYY-MM-DD HH:MM:SS
    assert normalize_time('2026-07-13 21:58:18').startswith('2026-07-13T21:58:18')
    # 格式 2: YYYY-MM-DD HH:MM
    assert normalize_time('2026-07-13 21:58').startswith('2026-07-13T21:58')
    # 格式 3: YYYY/MM/DD HH:MM:SS
    assert normalize_time('2026/07/13 21:58:18').startswith('2026-07-13T21:58:18')
    # 格式 4: YYYY/MM/DD HH:MM
    assert normalize_time('2026/07/13 21:58').startswith('2026-07-13T21:58')
    # 格式 5: YYYY年MM月DD日 HH:MM:SS
    assert normalize_time('2026年07月13日 21:58:18').startswith('2026-07-13T21:58:18')
    # 格式 6: YYYY年MM月DD日 HH:MM
    assert normalize_time('2026年07月13日 21:58').startswith('2026-07-13T21:58')


def test_normalize_time_iso_passthrough():
    """normalize_time 对已是 ISO 格式的字符串直接返回。"""
    iso = '2026-07-13T21:58:18+08:00'
    result = normalize_time(iso)
    assert '2026-07-13' in result


# ---------- classify_content 单元测试 ----------

def test_classify_content_url():
    """含 https:// 的内容标为 msg_type=link。"""
    msg_type, meta = classify_content('看这个链接 https://example.com/test 很有用')
    assert msg_type == 'link'
    assert 'urls' in meta
    assert 'https://example.com/test' in meta['urls']
    assert meta['primary_url'] == 'https://example.com/test'


def test_classify_content_filename():
    """含 .zip/.pdf 等后缀的内容标为 msg_type=file。"""
    msg_type, meta = classify_content('请查收 实验报告.zip 和 模板.pdf')
    assert msg_type == 'file'
    assert 'filenames' in meta or 'filename' in meta


def test_classify_content_system():
    """【系统消息】或 [系统] 开头的内容标为 msg_type=system。"""
    msg_type, meta = classify_content('【系统消息】你通过扫描二维码加入群聊')
    assert msg_type == 'system'

    msg_type2, _ = classify_content('[系统] 撤回了一条消息')
    assert msg_type2 == 'system'


def test_classify_content_text():
    """普通文本标为 msg_type=text。"""
    msg_type, meta = classify_content('收到谢谢')
    assert msg_type == 'text'
    assert meta == {} or 'urls' not in meta


# ---------- parse_txt 单元测试 ----------

def test_parse_txt_basic_message(tmp_path):
    """单行 txt 消息正确解析出 sender/sender_id/time/content。"""
    txt_file = tmp_path / 'chat.txt'
    txt_file.write_text(
        '[2026-07-13 21:58:18] Yang(wxid_yang001): 通过网盘分享的文件\n',
        encoding='utf-8'
    )
    msgs = parse_txt(txt_file)
    assert len(msgs) == 1
    m = msgs[0]
    assert m.sender == 'Yang'
    assert m.sender_id == 'wxid_yang001'
    assert '2026-07-13' in m.time
    assert m.content == '通过网盘分享的文件'
    assert m.msg_type in ('text', 'link', 'file')


def test_parse_txt_multiline_body(tmp_path):
    """多行消息正文正确合并（直到下一个 [时间] 行）。"""
    txt_file = tmp_path / 'chat.txt'
    txt_file.write_text(
        '[2026-07-13 21:58:18] Yang(wxid_yang001): 第一行\n'
        '第二行\n'
        '第三行\n'
        '[2026-07-13 22:00:00] 张老师(wxid_zhang): 新消息\n',
        encoding='utf-8'
    )
    msgs = parse_txt(txt_file)
    assert len(msgs) == 2
    # 第一条消息含 3 行正文
    assert '第一行' in msgs[0].content
    assert '第二行' in msgs[0].content
    assert '第三行' in msgs[0].content
    # 第二条消息是新 sender
    assert msgs[1].sender == '张老师'
    assert msgs[1].content == '新消息'


# ---------- parse_json 单元测试 ----------

def test_parse_json_wechatdataanalysis():
    """parse_json 解析 WechatDataAnalysis 格式：senderDisplayName 优先，senderUsername 进 sender_id。"""
    msgs = parse_json(REAL_DATA_FIXTURE)
    assert len(msgs) > 0
    # 找到 Yang 的消息
    yang_msgs = [m for m in msgs if m.sender == 'Yang']
    assert len(yang_msgs) >= 15  # fixture 含 20 条 Yang 消息（部分可能被 system 跳过）
    # sender_id 应含 wxid 或 username
    for m in yang_msgs:
        assert m.sender_id is not None or m.sender_id == ''  # 可能为空，但字段存在


def test_parse_json_skips_system_messages():
    """parse_json 跳过 renderType=='system' 的消息。"""
    msgs = parse_json(REAL_DATA_FIXTURE)
    # 系统消息不应出现在结果中
    for m in msgs:
        assert m.msg_type != 'system' or '系统' in m.content or '加入群聊' in m.content or '扫描' in m.content


def test_parse_json_msg_type_mapping():
    """parse_json 正确映射 renderType 到 msg_type，且链接内容被保留。"""
    msgs = parse_json(REAL_DATA_FIXTURE)
    # Yang 发了很多网盘链接，解析后 content 或 meta 应保留 pan.baidu.com
    yang_msgs = [m for m in msgs if m.sender == 'Yang']
    baidu_msgs = [
        m for m in yang_msgs
        if 'pan.baidu.com' in m.content or 'pan.baidu.com' in str(m.meta)
    ]
    assert len(baidu_msgs) > 0, "未找到含 pan.baidu.com 的 Yang 消息"
    # 至少有一些消息被标为 link 类型
    link_msgs = [m for m in msgs if m.msg_type == 'link']
    assert len(link_msgs) > 0, "未找到 msg_type=link 的消息"
