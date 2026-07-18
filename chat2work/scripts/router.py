#!/usr/bin/env python3
"""
Chat2Work router — 场景路由。

场景由用户意图决定（不分析聊天内容）：用 --mode 显式指定 course/distill；
未指定时默认 course-maker。distill 模式需 --target 指定蒸馏目标人物。

用法：
  python router.py messages.json [--mode course|distill] [--target "张老师"]

输出：scene.json，含 mode、target。
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def find_target(messages: list[dict], target_name: str) -> dict:
    """验证 --target 指定的人在消息中是否存在，返回该人的统计。"""
    target_msgs = [m for m in messages if m.get('sender') == target_name]
    if not target_msgs:
        # 模糊匹配
        fuzzy = [m for m in messages if target_name in m.get('sender', '')]
        if fuzzy:
            target_msgs = fuzzy
            actual_name = fuzzy[0]['sender']
        else:
            return {
                'found': False,
                'requested': target_name,
                'available_senders': list({m.get('sender') for m in messages}),
            }
    else:
        actual_name = target_name

    return {
        'found': True,
        'requested': target_name,
        'actual_name': actual_name,
        'message_count': len(target_msgs),
        'time_range': {
            'start': min(m['time'] for m in target_msgs),
            'end': max(m['time'] for m in target_msgs),
        },
    }


def main():
    ap = argparse.ArgumentParser(description='Chat2Work router — 场景路由')
    ap.add_argument('messages_json', help='parser 产出的 messages.json')
    ap.add_argument('--mode', choices=['course', 'distill'], help='显式指定场景')
    ap.add_argument('--target', help='蒸馏目标人物名（distill 模式必填）')
    ap.add_argument('-o', '--output', default='scene.json', help='输出路径')
    args = ap.parse_args()

    path = Path(args.messages_json)
    if not path.exists():
        print(f"错误：文件不存在 {path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(path.read_text(encoding='utf-8'))
    messages = data.get('messages', [])
    print(f"[*] 载入 {len(messages)} 条消息", file=sys.stderr)

    # 显式 mode 优先；未指定时默认 course-maker（不猜测用户意图）
    if args.mode == 'course':
        mode = 'course-maker'
        detail = {'source': 'user-specified'}
    elif args.mode == 'distill':
        mode = 'person-distiller'
        detail = {'source': 'user-specified'}
    else:
        mode = 'course-maker'
        detail = {'source': 'default'}
        print(f"[*] 未指定 --mode，默认 course-maker（如需蒸馏人物请加 --mode distill --target 名字）",
              file=sys.stderr)

    # distill 模式必须验证 target
    target_info = None
    if mode == 'person-distiller':
        if not args.target:
            # 自动选 top sender
            senders = Counter(m.get('sender', '') for m in messages)
            if senders:
                args.target = senders.most_common(1)[0][0]
                print(f"[*] 未指定 --target，自动选最活跃发言者: {args.target}", file=sys.stderr)
            else:
                print("错误：distill 模式需要 --target，且消息列表为空", file=sys.stderr)
                sys.exit(1)
        target_info = find_target(messages, args.target)
        if not target_info.get('found'):
            print(f"错误：在消息中找不到 '{args.target}'", file=sys.stderr)
            print(f"可用发送者: {target_info.get('available_senders', [])}", file=sys.stderr)
            sys.exit(1)
        print(f"[*] 目标人物: {target_info['actual_name']} ({target_info['message_count']} 条消息)", file=sys.stderr)

    out = {
        'mode': mode,
        'target': target_info,
        'detail': detail,
        'messages_file': args.messages_json,
    }

    out_path = Path(args.output)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[*] 场景: {mode}", file=sys.stderr)
    print(f"[*] 输出: {out_path}", file=sys.stderr)


if __name__ == '__main__':
    main()
