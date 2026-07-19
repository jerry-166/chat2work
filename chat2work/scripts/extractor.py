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
from datetime import datetime, timedelta
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


# 腾讯会议号:8-13 位数字(可含连字符)
MEETING_CODE_PATTERN = re.compile(r'(?:腾讯会议号|#腾讯会议)[:：]?\s*([\d-]{8,})')


def _extract_meeting_codes(content: str) -> list[str]:
    return [m.strip() for m in MEETING_CODE_PATTERN.findall(content)]


def extract_all(messages: list[dict]) -> dict:
    """从 messages 数组抽取所有客观字段。返回 extracted 结构。"""
    links = []
    files = []
    dates = []
    meeting_codes = []
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
        for code in _extract_meeting_codes(content):
            meeting_codes.append({
                'code': code,
                'msg_index': idx,
                'sender': msg.get('sender'),
                'time': msg.get('time'),
            })
    return {'links': links, 'files': files, 'dates': dates, 'meeting_codes': meeting_codes}


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
