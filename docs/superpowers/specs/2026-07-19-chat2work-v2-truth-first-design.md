# chat2work v2 设计:规则提取器(extractor.py)

> 日期:2026-07-19
> 状态:待评审
> 修订:v1(全推翻式重组)→ v2(外科手术式,仅加规则提取器)

## 背景:为什么范围缩小了

最初怀疑 v1"信息丢失率太高、不如直接用聊天记录",设计了全推翻式的重组方案(消息全保留+目录重组+闲聊分流)。

随后做了**同源对比实验**(21条机器狗样例,子会话当 LLM 跑完整 pipeline),数据说话:

| 场景 | v1 表现 |
|---|---|
| 21条干净数据 | 链接 3/3 全中、deadline 准、任务书结构清晰、溯源完整 → **v1 很好** |
| 147条FreeDo3D(大消息量+链接密集) | LLM 漏抽链接、meeting 链接被 content_preview 截断 → **v1 会漏** |

**真正结论**:v1 在小/干净数据上够用;瓶颈是**消息量大+链接密集时 LLM 提取环节漏抽**。其余 v1 结构(任务书、目录树、provenance)实验证明能留。

因此 v2 缩小为**一个外科手术式改动:加规则提取器,把链接/文件/提取码/会议号的提取从 LLM 手里拿走,交给正则(100%不丢)**。LLM 只保留语义标注职责。

不在本次范围(YAGNI,实验未证明必要):
- 消息全文保留到 03_讨论记录/
- 目录重组
- 闲聊分流
- 软链接

## 设计

### 新组件:`scripts/extractor.py`

纯规则,无 LLM,无外部依赖。输入 messages.json,输出 extracted.json:

```json
{
  "links": [
    {
      "url": "https://pan.baidu.com/s/1IWgZBqY8nigCCkL8D_fK2Q?pwd=vp2i",
      "extract_code": "vp2i",
      "msg_index": 114,
      "sender": "Yang",
      "time": "2026-07-14T..."
    }
  ],
  "files": [
    {"filename": "wavego_twin_patch.zip", "msg_index": 10, "sender": "张老师", "time": "..."}
  ],
  "dates": [
    {"raw": "2026-07-25", "absolute": "2026-07-25", "uncertain": false, "msg_index": 7}
  ],
  "meeting_codes": [
    {"code": "460-149-615", "msg_index": 113}
  ]
}
```

### 提取规则

- **链接**:`https?://[^\s,。、"'<>)）]\]+`,保留完整 query string(`?pwd=xxx` 不截断)
- **提取码配对**:同一条消息里 `pwd=([a-z0-9]{4})` 或 `提取码[:：]\s*([a-z0-9]{4})`,与该消息里的链接绑定;无链接则单独记
- **文件名**:`[\w一-龥]+\.(zip|rar|pdf|docx?|xlsx?|py|fbx|gha|mp4|step|stl|urdf)` 等
- **日期**:`\d{4}[/-]\d{1,2}[/-]\d{1,2}` 优先;`下周[一二三四五六日天]`/`本周[...]` 相对时间→绝对(以消息发送时间为基准,标 `uncertain: true`)
- **会议号**:`腾讯会议号[:：]?\s*([\d-]{8,})`

每条结果都带 `msg_index`(回指 messages.json 的下标),可溯源。

### pipeline 接入

```
parser.py → messages.json
               │
               ├─→ extractor.py ─→ extracted.json  ★ 新增
               │       (规则,100%不丢)
               │
               └─→ LLM(course-maker prompt)
                       ↑ 拿 extracted.json 作输入
                       │ LLM 不再自己扫链接,只做语义标注
                       ↓
                   llm_output.json
                       ↓
                   builder.py(基本不动)
```

### prompt 改动(`prompts/course-maker.md`)

LLM 输入里**预置** extractor 抽好的 links/files/dates,LLM 只需:
- 给每条 link 标 `why`(这是干嘛的)——语义
- 把 dates 归到对应 task ——语义
- 写 task 描述、评分标准 ——语义

prompt 里明确写:**"链接/文件/提取码已在输入的 extracted 字段给出,不要自己重新扫描消息抽取,直接引用即可"**。

### builder 改动(最小)

- 读 extracted.json,合并进 context
- 链接库.md 的"链接清单"表格**优先用 extracted.links**(而非 llm_output.refs),保证不丢
- llm_output.refs 只贡献 `why`/`title` 语义字段,通过 url 与 extracted.links join

### 验收标准

用 147 条 FreeDo3D 真实数据回归:
1. 链接库.md 包含 **≥19 条链接**(规则全量抽,带完整 ?pwd=)
2. 每条链接的提取码(若有)正确配对
3. 会议号 460-149-615 等被抽出
4. 21条机器狗样例回归:链接仍 3/3,不退化

## 不做的事

- 不改目录结构(实验证明没必要)
- 不保留消息全文(实验证明没必要)
- 不做闲聊分流(实验证明没必要)
- 不做软链接(用户已否决)

## 开放问题

(评审时确认)
1. extractor 抽出的链接,若 LLM 完全没提到(没标 why),要不要进链接库?默认:**进**,why 留空,标注 `[未标注]`。规则优先于语义,不丢是第一原则。
2. 相对时间"下周"转绝对,用哪条消息作基准?默认:出现该相对时间的那条消息的发送时间。
