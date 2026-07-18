import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
msgs = json.load(open(r'D:\workspace\demo\test_wechat_assistant\chat2work\tests\real_messages.json', encoding='utf-8'))['messages']
for n in [0,1,2,4,5,7,8,9]:
    m = msgs[n]
    print(f'msg#{n} -> id={m["source_msg_id"]}')
    print(f'         sender={m["sender"]} | {m["content"][:50].replace(chr(10)," ")}')
