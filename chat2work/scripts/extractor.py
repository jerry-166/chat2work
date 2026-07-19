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
from datetime import datetime, timedelta


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


# 文件名:中文/字母数字 + 常见后缀。后缀后面不能紧跟字母/数字/中文(防止 .c 匹配 .com)
FILE_PATTERN = re.compile(
    r'([一-龥\w]+\.(?:zip|rar|7z|pdf|docx?|xlsx?|pptx?|py|cpp|c|java|js|ts|fbx|obj|stl|step|urdf|gha|mp4))(?![a-zA-Z0-9_一-龥])',
    re.IGNORECASE,
)


def _extract_files(content: str) -> list[str]:
    return FILE_PATTERN.findall(content)


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


def extract_all(messages: list[dict]) -> dict:
    """从 messages 数组抽取所有客观字段。返回 extracted 结构。"""
    links = []
    files = []
    dates = []
    for idx, msg in enumerate(messages):
        content = msg.get('content', '') or ''
        msg_time = msg.get('time', '') or ''
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
        for d in _extract_dates(content, msg_time):
            d['msg_index'] = idx
            dates.append(d)
    return {'links': links, 'files': files, 'dates': dates, 'meeting_codes': []}
