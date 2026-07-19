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
