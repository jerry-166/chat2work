#!/usr/bin/env python3
"""
Chat2Work parser — 把 WechatDataAnalysis/QQ导出工具产出的聊天记录归一化为统一 Message 结构。

支持格式：
  - .txt  (WechatDataAnalysis 导出，格式: "[2026-07-08 10:35:01] 张老师(wxid_xxx) [avatar=...]: 消息内容")
  - .json (WechatDataAnalysis / qq-chat-exporter，多种 schema)
  - .html (WechatDataAnalysis 导出)

用法：
  python parser.py <chat_file> [--output messages.json]

输出：messages.json，每条消息含 source_line/source_msg_id 溯源字段。
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Message:
    sender: str
    sender_id: Optional[str]
    time: str  # ISO 8601 字符串，便于 JSON 序列化
    content: str
    msg_type: str  # text|link|file|image|voice|system
    meta: dict = field(default_factory=dict)
    source_line: Optional[int] = None
    source_msg_id: Optional[str] = None


# ---------- TXT 解析（WechatDataAnalysis 导出格式） ----------

# WechatDataAnalysis txt 格式示例：
# [2026-07-08 10:35:01] 张老师(wxid_xxx) [avatar=media/...]: 消息正文
# [2026-07-09 15:49:26] 张建兵(wxid_smdrxpo4dwa611) [avatar=...]: @李旺，今天最后上课...
# 多行消息的后续行不带时间戳前缀，直到下一个 [时间] 行
TXT_MSG_PATTERN = re.compile(
    r'^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]\s+(.+?)\s*(?:\[avatar=[^\]]*\])?\s*:\s*(.*)$'
)
# 从 "真名(wxid)" 里分离真名和 wxid
TXT_SENDER_PATTERN = re.compile(r'^(.+?)\((wxid_[A-Za-z0-9_]+|[^()]+)\)\s*$')


def parse_txt(path: Path) -> list[Message]:
    msgs = []
    with path.open('r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        m = TXT_MSG_PATTERN.match(line)
        if not m:
            i += 1
            continue

        time_str, sender_field, first_body = m.group(1), m.group(2).strip(), m.group(3)
        # 分离 真名(wxid)
        sender, sender_id = sender_field, None
        sm = TXT_SENDER_PATTERN.match(sender_field)
        if sm:
            sender = sm.group(1).strip()
            sender_id = sm.group(2)

        # 收集消息正文（第一行的 : 后内容 + 后续非时间戳行）
        body_lines = [first_body] if first_body else []
        start_line = i + 1
        i += 1
        while i < len(lines):
            next_line = lines[i].rstrip('\n')
            if TXT_MSG_PATTERN.match(next_line):
                break
            body_lines.append(next_line)
            i += 1

        content = '\n'.join(body_lines).strip()
        if not content:
            continue

        # TXT 特有：[文件]/[图片] 前缀
        msg_type, meta = classify_content(content)
        if content.startswith('[文件]'):
            msg_type = 'file'
            rest = content[len('[文件]'):]
            # 形如 "name名 size=123 path"；取第一个 token 做文件名
            meta['filename'] = rest.split('size=')[0].strip().split('media/')[-1].split('/')[-1].strip() or rest[:40]
        elif content.startswith('[图片]'):
            msg_type = 'image'
            meta['local_path'] = content[len('[图片]'):].strip()

        msgs.append(Message(
            sender=sender,
            sender_id=sender_id,
            time=time_str.replace(' ', 'T'),
            content=content,
            msg_type=msg_type,
            meta=meta,
            source_line=start_line,
        ))
    return msgs


# ---------- JSON 解析（多 schema 兼容） ----------

def parse_json(path: Path) -> list[Message]:
    with path.open('r', encoding='utf-8') as f:
        data = json.load(f)

    # 兼容多种 schema：
    # 1. WechatDataAnalysis (主): {"messages": [{"senderDisplayName": "张老师", "senderUsername": "wxid", "createTimeText": "...", "renderType": "text|file|image|link|quote|system", "content": "...", ...}]}
    # 2. qq-chat-exporter json: {"messages": [{"sender": ..., "time": ..., "content": ...}]}
    # 3. 自定义: [{"sender": ..., "time": ..., "content": ...}]

    raw_msgs = data if isinstance(data, list) else data.get('messages', data.get('data', []))
    if not isinstance(raw_msgs, list):
        raise ValueError(f"无法识别的 JSON 结构: {list(data.keys()) if isinstance(data, dict) else type(data)}")

    msgs = []
    for idx, item in enumerate(raw_msgs):
        if not isinstance(item, dict):
            continue

        # ---- sender 字段兼容（真名优先，wxid 退到 sender_id） ----
        # WechatDataAnalysis: senderDisplayName=群昵称/真名, senderUsername=wxid
        # 旧字段 displayName/display_name 兼容其它导出工具
        sender = (
            item.get('senderDisplayName')       # WechatDataAnalysis: 真名/群昵称
            or item.get('displayName')         # 通用：备注名
            or item.get('display_name')
            or item.get('nickname')
            or item.get('sender')               # qq-chat-exporter
            or item.get('talker')              # 旧 WeChatMsg v1
            or item.get('senderUsername')      # 兜底：wxid（无真名时）
            or ''
        ).strip()

        # ---- 跳过系统消息 ----
        render_type = item.get('renderType', '')
        if render_type == 'system' or not sender:
            continue

        # ---- time 字段兼容 ----
        time_val = (item.get('createTimeText') or item.get('str_time')
                    or item.get('time') or item.get('timestamp') or item.get('datetime'))
        if isinstance(time_val, (int, float)):
            time_str = datetime.fromtimestamp(time_val).isoformat()
        elif isinstance(time_val, str):
            time_str = normalize_time(time_val)
        else:
            time_str = datetime.now().isoformat()

        # ---- 读取原始内容字段 ----
        raw_content = (
            item.get('content')
            or item.get('msg')
            or item.get('text')
            or item.get('message')
            or ''
        ).strip()

        # ---- 根据 renderType 构建消息 ----
        msg_type = render_type if render_type else classify_content(raw_content)[0]
        meta = {}

        # 链接类消息：构建更好的描述（通常是分享的公众号/视频/文章）
        if render_type == 'link' and item.get('title'):
            desc = item.get('title', '')
            if item.get('from'):
                desc += f' [来源: {item["from"]}]'
            if item.get('content'):
                desc += f' ({item["content"]})'
            raw_content = desc

        if render_type == 'link':
            meta['primary_url'] = item.get('url', '')
            meta['title'] = item.get('title', '')
            meta['source_platform'] = item.get('from', '')

        # 文件类消息
        if render_type == 'file':
            meta['filename'] = item.get('title', '')
            meta['object_id'] = item.get('objectId', '')

        # 图片类消息
        if render_type == 'image':
            meta['image_md5'] = item.get('imageMd5', '')
            meta['thumb_url'] = item.get('thumbUrl', '')

        # 引用类消息
        if render_type == 'quote':
            meta['quote_sender'] = item.get('fromUsername', '')
            meta['quote_content'] = item.get('recordItem', '')

        # 合并已有的 url/filename 等
        for k in ('url', 'filename', 'file_size', 'local_path'):
            v = item.get(k)
            if v and k not in meta:
                meta[k] = v

        # 空内容跳过
        if not raw_content:
            continue

        msgs.append(Message(
            sender=sender,
            sender_id=item.get('senderUsername') or item.get('wxid') or item.get('user_id'),
            time=time_str,
            content=raw_content,
            msg_type=msg_type,
            meta=meta,
            source_msg_id=item.get('id') or item.get('msg_id') or f'json#{idx}',
        ))
    return msgs


# ---------- HTML 解析 ----------

def parse_html(path: Path) -> list[Message]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise RuntimeError("解析 HTML 需要 beautifulsoup4，请: pip install beautifulsoup4")

    with path.open('r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    msgs = []
    # 注意：此处选择器适配旧 WeChatMsg 的 HTML 结构。
    # WechatDataAnalysis 的 HTML 用 Tailwind class（data-render-type 属性标类型，
    # data-wce-create-time 标时间戳，真名在 <div class="text-[11px]...">），
    # 建议优先用其 .json 导出格式，字段更规整、真名/类型/文件路径都齐全。
    for idx, msg_div in enumerate(soup.select('.message, .msg, [class*=message]')):
        time_el = msg_div.select_one('.time, .datetime, [class*=time]')
        sender_el = msg_div.select_one('.sender, .nickname, [class*=sender]')
        content_el = msg_div.select_one('.content, .text, [class*=content]')

        time_str = normalize_time(time_el.get_text(strip=True)) if time_el else datetime.now().isoformat()
        sender = sender_el.get_text(strip=True) if sender_el else '未知'
        content = content_el.get_text('\n', strip=True) if content_el else ''
        if not content:
            continue

        # 提取链接
        a_tag = content_el.find('a') if content_el else None
        meta = {}
        if a_tag and a_tag.get('href'):
            meta['url'] = a_tag['href']
            meta['title'] = a_tag.get_text(strip=True)

        msg_type = 'link' if a_tag else 'text'
        msgs.append(Message(
            sender=sender,
            sender_id=None,
            time=time_str,
            content=content,
            msg_type=msg_type,
            meta=meta,
            source_msg_id=f'html#{idx}',
        ))
    return msgs


# ---------- 工具函数 ----------

URL_PATTERN = re.compile(r'https?://[^\s<>"]+')
FILE_PATTERN = re.compile(r'\.(zip|rar|7z|pdf|docx?|xlsx?|pptx?|py|cpp|c|java|js|ts|md|fbx|obj|stl)\b', re.IGNORECASE)


def classify_content(content: str) -> tuple[str, dict]:
    """根据内容判断消息类型，返回 (msg_type, meta)。"""
    meta = {}

    # 系统消息
    if content.startswith('【系统消息】') or content.startswith('[系统]'):
        return 'system', {'action': content}

    # 链接
    urls = URL_PATTERN.findall(content)
    if urls:
        meta['urls'] = urls
        meta['primary_url'] = urls[0]
        return 'link', meta

    # 文件名提及
    file_match = FILE_PATTERN.search(content)
    if file_match:
        meta['filename'] = file_match.group(0)
        return 'file', meta

    return 'text', meta


def normalize_time(s: str) -> str:
    """把各种时间字符串归一化为 ISO 8601。"""
    s = s.strip()
    for fmt in (
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y/%m/%d %H:%M:%S',
        '%Y/%m/%d %H:%M',
        '%Y年%m月%d日 %H:%M:%S',
        '%Y年%m月%d日 %H:%M',
    ):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue
    # 已经是 ISO 格式
    try:
        return datetime.fromisoformat(s).isoformat()
    except ValueError:
        return s  # 兜底，原样返回


def sniff_format(path: Path) -> str:
    """根据扩展名+内容嗅探格式。"""
    ext = path.suffix.lower()
    if ext == '.txt':
        return 'txt'
    if ext == '.json':
        return 'json'
    if ext in ('.html', '.htm'):
        return 'html'
    # 兜底：看内容首行
    with path.open('r', encoding='utf-8', errors='ignore') as f:
        first = f.read(200)
    if first.lstrip().startswith('{') or first.lstrip().startswith('['):
        return 'json'
    if '<html' in first.lower() or '<!doctype' in first.lower():
        return 'html'
    return 'txt'


def parse_file(path: Path) -> list[Message]:
    fmt = sniff_format(path)
    if fmt == 'txt':
        return parse_txt(path)
    if fmt == 'json':
        return parse_json(path)
    if fmt == 'html':
        return parse_html(path)
    raise ValueError(f"不支持的格式: {fmt}")


def main():
    ap = argparse.ArgumentParser(description='Chat2Work parser — 聊天记录归一化')
    ap.add_argument('chat_file', help='聊天记录文件路径 (txt/json/html)')
    ap.add_argument('-o', '--output', default='messages.json', help='输出 JSON 路径')
    args = ap.parse_args()

    path = Path(args.chat_file)
    if not path.exists():
        print(f"错误：文件不存在 {path}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] 解析 {path.name} (格式: {sniff_format(path)})", file=sys.stderr)
    msgs = parse_file(path)
    print(f"[*] 共 {len(msgs)} 条消息", file=sys.stderr)

    if len(msgs) < 5:
        print(f"警告：消息太少 ({len(msgs)} < 5)，蒸馏效果可能不佳", file=sys.stderr)

    # 统计
    senders = {}
    types = {}
    for m in msgs:
        senders[m.sender] = senders.get(m.sender, 0) + 1
        types[m.msg_type] = types.get(m.msg_type, 0) + 1

    out = {
        'source_file': str(path),
        'total_messages': len(msgs),
        'senders': senders,
        'msg_types': types,
        'time_range': {
            'start': min(m.time for m in msgs) if msgs else None,
            'end': max(m.time for m in msgs) if msgs else None,
        },
        'messages': [asdict(m) for m in msgs],
    }

    out_path = Path(args.output)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[*] 输出: {out_path}", file=sys.stderr)
    print(f"[*] 发送者: {len(senders)} 人, 类型分布: {types}", file=sys.stderr)


if __name__ == '__main__':
    main()
