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
