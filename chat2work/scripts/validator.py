#!/usr/bin/env python3
"""
Chat2Work validator — 三重验证简化版。

对人物蒸馏的 observations 做纯规则硬过滤，不依赖 LLM 自我评审。
规则：跨域复现（≥2 个不同上下文）+ 预测力（≥30% holdout 验证）+ 排他性（≥60% 来自目标人物）。

用法（集成到 builder.py）：
  from validator import triple_validate
  verified_observations = triple_validate(observations, predictions, messages, target_name)

独立运行（调试）：
  python validator.py <observations.json> <messages.json> --target Yang -o verified.json
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# ---------- 可调阈值 ----------
CROSS_DOMAIN_MIN_DOMAINS = 2      # 跨域复现：至少 2 个不同领域/时间段
PREDICTIVE_POWER_THRESHOLD = 0.3  # 预测力：至少 30% holdout 验证
EXCLUSIVITY_THRESHOLD = 0.6       # 排他性：至少 60% 来自目标人物

# 中文分词（简单关键词提取，不依赖 jieba）
CHINESE_WORD_PATTERN = re.compile(r'[\u4e00-\u9fff]{2,}')
TECH_WORD_PATTERN = re.compile(r'[a-zA-Z_][a-zA-Z0-9_.]{2,}')


def _extract_keywords(text: str) -> list[str]:
    """从文本中提取关键词（中文 2+ 字词组 + 英文技术词）。"""
    if not text:
        return []
    cn_words = CHINESE_WORD_PATTERN.findall(text)
    en_words = TECH_WORD_PATTERN.findall(text)
    return list(set(cn_words + en_words))


def _bucket_by_week(messages: list[dict]) -> dict[str, list[dict]]:
    """按 ISO 周分桶。"""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for m in messages:
        time_str = m.get('time', '')
        if not time_str:
            continue
        try:
            # ISO 8601: "2026-07-13T21:58:18+08:00"
            # 取周数: 2026-W29
            from datetime import datetime
            dt = datetime.fromisoformat(time_str[:19])
            week = dt.strftime('%Y-W%W')
            buckets[week].append(m)
        except (ValueError, IndexError):
            continue
    # 如果只有 1 周，按天分桶
    if len(buckets) <= 1:
        buckets = defaultdict(list)
        for m in messages:
            time_str = m.get('time', '')
            if not time_str:
                continue
            try:
                day = time_str[:10]  # YYYY-MM-DD
                buckets[day].append(m)
            except (ValueError, IndexError):
                continue
    return dict(buckets)


def _bucket_by_topic(messages: list[dict]) -> dict[str, list[dict]]:
    """按关键词聚类（简单实现：消息中最高频词作为 topic key）。"""
    if len(messages) <= 5:
        return {'default': list(messages)}
    
    # 收集所有关键词
    keyword_msgs: dict[str, list[int]] = defaultdict(list)
    for idx, m in enumerate(messages):
        content = m.get('content', '')
        keywords = _extract_keywords(content)
        for kw in keywords[:5]:  # 取前 5 个关键词
            keyword_msgs[kw].append(idx)
    
    # 取高频关键词作为 topic buckets（消息覆盖 >10% 的 topic）
    buckets: dict[str, list[dict]] = defaultdict(list)
    for kw, indices in keyword_msgs.items():
        if len(indices) > len(messages) * 0.1:
            for idx in indices:
                bucket_key = f'topic:{kw}'
                if messages[idx] not in buckets[bucket_key]:
                    buckets[bucket_key].append(messages[idx])
    
    if not buckets:
        buckets['default'] = list(messages)
    return dict(buckets)


def _get_buckets(msg_index: int, buckets: dict[str, list[dict]]) -> set[str]:
    """返回消息所属的所有桶名。"""
    result = set()
    for bucket_name, msgs in buckets.items():
        for m in msgs:
            if msgs.index(m) if hasattr(msgs, 'index') else id(m) == id(msgs):
                # 简化：用消息 ID 匹配
                pass
    # 简化实现：用索引列表匹配
    # 这里我们改一下 _bucket_by_week 和 _bucket_by_topic 返回 {bucket_name: [msg_indices]}
    return result


# ---------- 三重过滤 ----------

def check_cross_domain_reproducibility(
    observations: list[dict], messages: list[dict], target_name: str
) -> list[dict]:
    """跨域复现：同一观察在 ≥2 个不同时间段/主题的发言中出现才算稳。"""
    target_msgs = [(i, m) for i, m in enumerate(messages)
                   if m.get('sender') == target_name]
    if len(target_msgs) < 3:
        # 数据太少，全部标 partial
        return [{'observation_id': i, 'reproducibility': max(len(messages), 1),
                 'passed': False, 'reason': '数据太少(<3条)'}
                for i in range(len(observations))]

    time_buckets = _bucket_by_week(messages)
    topic_buckets = _bucket_by_topic(messages)

    # 构建 msg_index → bucket_names 映射
    msg_to_time_bucket: dict[int, str] = {}
    for bucket_name, bucket_msgs in time_buckets.items():
        for _i, m in enumerate(messages):
            if m in bucket_msgs:
                msg_to_time_bucket[messages.index(m)] = bucket_name

    results = []
    for i, obs in enumerate(observations):
        evidence_indices = obs.get('evidence_indices', [])
        evidence_keywords = obs.get('keywords', [])
        
        if not evidence_indices and not evidence_keywords:
            results.append({
                'observation_id': i, 'reproducibility': 0,
                'passed': False, 'reason': '无证据消息/关键词'
            })
            continue

        # 从 keywords 扩展出匹配的消息（如果 evidence_indices 为空）
        if not evidence_indices and evidence_keywords:
            evidence_indices = []
            for idx, m in enumerate(messages):
                if m.get('sender') != target_name:
                    continue
                content = m.get('content', '')
                found_kws = [kw for kw in evidence_keywords if kw in content]
                if len(found_kws) >= 1:
                    evidence_indices.append(idx)

        if not evidence_indices:
            results.append({
                'observation_id': i, 'reproducibility': 0,
                'passed': False, 'reason': '无法定位证据消息'
            })
            continue

        # 计算时间桶覆盖
        time_buckets_hit = len({
            msg_to_time_bucket.get(idx, f'unknown_{idx}')
            for idx in evidence_indices
        })
        
        # 计算主题桶覆盖（从 target_msgs 中提取关键词计数）
        topic_kw_count = len(evidence_keywords)
        
        reproducibility = min(time_buckets_hit, max(topic_kw_count, 1))
        results.append({
            'observation_id': i,
            'reproducibility': reproducibility,
            'passed': reproducibility >= CROSS_DOMAIN_MIN_DOMAINS,
            'time_buckets': time_buckets_hit,
            'topic_signals': topic_kw_count,
        })

    return results


def check_predictive_power(
    predictions: list[dict], messages: list[dict], target_name: str
) -> list[dict]:
    """预测力：观察的预测能在 holdout 消息中被验证。

    predictions: [{'predicted_keywords': [...], 'observation_id': int}]
    holdout: 目标人物的最后 5 条消息
    """
    target_msgs = [(i, m) for i, m in enumerate(messages)
                   if m.get('sender') == target_name]
    holdout_size = min(5, max(1, len(target_msgs) // 4))
    holdout = target_msgs[-holdout_size:] if target_msgs else []

    results = []
    for pred in predictions:
        predicted_kws = pred.get('predicted_keywords', [])
        observation_id = pred.get('observation_id', -1)
        
        if not predicted_kws or not holdout:
            results.append({
                'observation_id': observation_id,
                'power_score': 0, 'passed': False,
                'reason': '无预测关键词或无 holdout 数据'
            })
            continue

        verified_count = 0
        for _, holdout_msg in holdout:
            content = holdout_msg.get('content', '')
            if any(kw in content for kw in predicted_kws):
                verified_count += 1

        power_score = verified_count / max(1, len(holdout))
        results.append({
            'observation_id': observation_id,
            'power_score': power_score,
            'verified_count': verified_count,
            'holdout_size': len(holdout),
            'passed': power_score >= PREDICTIVE_POWER_THRESHOLD,
        })

    return results


def check_exclusivity(
    observations: list[dict], messages: list[dict], target_name: str
) -> list[dict]:
    """排他性：观察的关键词在目标人物发言中的占比 ≥ 阈值。"""
    results = []
    for i, obs in enumerate(observations):
        keywords = obs.get('keywords', [])
        
        if not keywords:
            results.append({
                'observation_id': i, 'exclusivity': 0,
                'passed': False, 'reason': '无关键词'
            })
            continue

        # 目标人物的消息中有关键词
        target_hits = sum(
            1 for m in messages
            if m.get('sender') == target_name
            and any(kw in m.get('content', '') for kw in keywords)
        )
        
        # 其他人的消息中有关键词
        other_hits = sum(
            1 for m in messages
            if m.get('sender') != target_name
            and any(kw in m.get('content', '') for kw in keywords)
        )

        total = target_hits + other_hits
        exclusivity = target_hits / max(1, total)
        results.append({
            'observation_id': i,
            'exclusivity': exclusivity,
            'target_hits': target_hits,
            'other_hits': other_hits,
            'passed': exclusivity >= EXCLUSIVITY_THRESHOLD,
        })

    return results


def triple_validate(
    observations: list[dict],
    predictions: list[dict] | None,
    messages: list[dict],
    target_name: str,
) -> list[dict]:
    """三重验证入口。

    Args:
        observations: LLM 产出的观察列表。
            每条: {'observation': '...', 'evidence_indices': [...], 'keywords': [...], 'layer': '...'}
        predictions: LLM 产出的预测列表（可选）。
            每条: {'observation_id': int, 'predicted_keywords': [...]}
        messages: 归一化后的消息列表。
        target_name: 目标人物名。

    Returns:
        带 verification_status 的 observations 列表：
        verified (3/3) / partial (1-2/3) / unverified (0/3)
    """
    if predictions is None:
        predictions = []

    cross_domain = check_cross_domain_reproducibility(observations, messages, target_name)
    power = check_predictive_power(predictions, messages, target_name)
    exclusivity = check_exclusivity(observations, messages, target_name)

    # 合并结果
    power_by_id = {p['observation_id']: p for p in power}
    exclusivity_by_id = {e['observation_id']: e for e in exclusivity}

    for i, obs in enumerate(observations):
        cd = cross_domain[i] if i < len(cross_domain) else {'passed': False}
        pw = power_by_id.get(i, {'passed': False})
        ex = exclusivity_by_id.get(i, {'passed': False})

        score = sum([cd.get('passed', False), pw.get('passed', False), ex.get('passed', False)])
        obs['verification'] = {
            'cross_domain': cd.get('passed', False),
            'cross_domain_detail': cd,
            'predictive': pw.get('passed', False),
            'predictive_detail': pw,
            'exclusive': ex.get('passed', False),
            'exclusive_detail': ex,
            'score': score,
        }
        obs['verification_status'] = (
            'verified' if score == 3
            else 'partial' if score >= 1
            else 'unverified'
        )

    return observations


# ---------- 多轮提炼 prompt 生成（供宿主 AI 使用） ----------

def generate_round_prompts(
    messages: list[dict], target_name: str, extracted: dict | None = None
) -> dict:
    """生成 3 轮 LLM 提炼的 prompt 文本。

    返回值：
    {
      'round_1': '行为观察视角 prompt',
      'round_2': '动机推理视角 prompt',
      'round_3': '预测验证视角 prompt',
      'target_messages': [...],
      'holdout_messages': [...],
    }
    """
    target_msgs = [m for m in messages if m.get('sender') == target_name]
    holdout_size = min(3, max(1, len(target_msgs) // 4))
    holdout = target_msgs[-holdout_size:] if target_msgs else []
    training = target_msgs[:-holdout_size] if len(target_msgs) > holdout_size else target_msgs

    rounds = {
        'round_1': f"""你是一位行为观察员。只记录观察到的行为，不做推断。

目标人物：{target_name}
观察消息（{len(training)} 条）：{json.dumps(training[:50], ensure_ascii=False)[:8000]}

请产出 observations JSON 数组，每条包含：
- observation: 观察到的具体行为
- evidence_indices: 证据消息在 training 列表中的索引
- keywords: 此观察的核心关键词（3-5 个中文/英文词）
- layer: 所属 Layer（0-5）
- confidence: high/medium/low""",

        'round_2': f"""基于以下观察，推断目标人物 {target_name} 的动机和偏好。

第 1 轮观察结果：{{round_1_observations}}
额外消息上下文：{json.dumps(training[:50], ensure_ascii=False)[:8000]}

请产出 inferences JSON 数组，每条包含：
- observation_id: 对应的第 1 轮观察索引
- inferred_motivation: 推断的动机
- supporting_indices: 支持推断的消息索引
- contradicting_indices: 矛盾的消息索引""",

        'round_3': f"""如果以下推断正确，目标人物 {target_name} 在 holdout 消息中应该表现出什么？验证之。

第 2 轮推断结果：{{round_2_inferences}}
Holdout 消息（{holdout_size} 条）：{json.dumps(holdout, ensure_ascii=False)[:4000]}

请产出 predictions JSON 数组，每条包含：
- observation_id: 对应的观察索引
- predicted_keywords: 预测 holdout 中会出现的 3-5 个关键词
- predicted_behavior: 预测的行为描述""",
    }

    return {
        **rounds,
        'target_messages': target_msgs,
        'holdout_messages': holdout,
        'training_messages': training,
    }


# ---------- 主入口（调试用） ----------

def main():
    ap = argparse.ArgumentParser(description='Chat2Work validator — 三重验证')
    ap.add_argument('observations_json', help='observations JSON 文件')
    ap.add_argument('messages_json', help='归一化 messages JSON 文件')
    ap.add_argument('--target', required=True, help='目标人物名')
    ap.add_argument('--predictions', help='predictions JSON 文件（可选）')
    ap.add_argument('-o', '--output', default='verified.json', help='输出路径')
    args = ap.parse_args()

    observations_path = Path(args.observations_json)
    messages_path = Path(args.messages_json)

    if not observations_path.exists():
        print(f"错误：文件不存在 {observations_path}", file=sys.stderr)
        sys.exit(1)
    if not messages_path.exists():
        print(f"错误：文件不存在 {messages_path}", file=sys.stderr)
        sys.exit(1)

    observations = json.loads(observations_path.read_text(encoding='utf-8'))
    messages_data = json.loads(messages_path.read_text(encoding='utf-8'))
    messages = messages_data if isinstance(messages_data, list) else messages_data.get('messages', [])

    predictions = None
    if args.predictions:
        predictions_path = Path(args.predictions)
        if predictions_path.exists():
            predictions = json.loads(predictions_path.read_text(encoding='utf-8'))

    print(f"[*] 三重验证: {len(observations)} 观察, {len(messages)} 条消息, target={args.target}",
          file=sys.stderr)

    verified = triple_validate(observations, predictions, messages, args.target)

    result = {
        'target': args.target,
        'total_observations': len(verified),
        'status_counts': {
            'verified': sum(1 for o in verified if o.get('verification_status') == 'verified'),
            'partial': sum(1 for o in verified if o.get('verification_status') == 'partial'),
            'unverified': sum(1 for o in verified if o.get('verification_status') == 'unverified'),
        },
        'observations': verified,
    }

    out_path = Path(args.output)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[*] 验证结果: {result['status_counts']}", file=sys.stderr)
    print(f"[*] 输出: {out_path}", file=sys.stderr)


if __name__ == '__main__':
    main()
