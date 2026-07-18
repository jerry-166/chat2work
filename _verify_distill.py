import json, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
msgs = json.load(open(r'D:\workspace\demo\test_wechat_assistant\chat2work\tests\real_messages.json', encoding='utf-8'))['messages']
out = json.load(open(r'D:\workspace\demo\test_wechat_assistant\chat2work\tests\real_llm_output.json', encoding='utf-8'))
pat = re.compile(r'^msg#(\d+)$')
problems = []
for r in out['refs']:
    n = int(pat.match(r['src_msg']).group(1))
    actual = msgs[n]['sender']
    if actual != r['sender']:
        problems.append(f'ref [{r["title"][:20]}] msg#{n} 标注={r["sender"]} 实际={actual}')
for t in out['tasks']:
    for ref in t.get('src_msgs', []):
        n = int(pat.match(ref).group(1))
        if n >= len(msgs): problems.append(f'{t["name"]}: msg#{n} 越界')
print('refs 数:', len(out['refs']), '| tasks 数:', len(out['tasks']))
print('问题:', problems if problems else '无 ✓')
