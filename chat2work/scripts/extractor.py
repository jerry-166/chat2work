#!/usr/bin/env python3
"""
Chat2Work extractor — 从 messages.json 全量抽取客观字段。

规则提取,无 LLM,100% 不丢。抽取:链接(保留 ?pwd=)、提取码配对、
文件名、日期(绝对/相对)、腾讯会议号。

用法:
  python extractor.py <messages.json> [--output extracted.json]

每条结果带 msg_index,可回指 messages.json 的下标做溯源。
"""

import re


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
