#!/usr/bin/env python3
"""
Chat2Work builder — 把 LLM 产出的 JSON 目录树实体化为真实文件/目录。

支持两种产物：
  1. course-maker: 接收 dir_tree JSON，渲染 templates/course-workspace/ 下的模板，
     创建完整工作目录树，生成 _provenance/msg-to-file.json 溯源映射。
  2. person-distiller: 接收 SOUL.md 内容，直接写成单个 .md 文件。

用法：
  python builder.py <llm_output.json> [--target-dir .] [--mode course]

llm_output.json 结构（course-maker）：
{
  "mode": "course-maker",
  "project_name": "数字孪生WAVEGO",
  "deadline": "2026-07-25",
  "tasks": [...],
  "refs": [...],
  "dir_tree": { "name": "...", "type": "dir", "children": [...] },
  "messages_file": "messages.json"  # 用于 provenance
}

llm_output.json 结构（person-distiller，v2.0 6 层结构）：
{
  "mode": "person-distiller",
  "target_name": "张老师",
  "target_actual_name": "张老师",
  "source_file": "messages.json",
  "message_count": 20,
  "time_range_start": "2026-07-13T13:58:18",
  "time_range_end": "2026-07-17T15:32:53",
  "speech_style": "...",
  "catchphrases": ["..."],
  "expression_habits": "...",
  "qa_pattern": "...",
  "evaluation_focus": "...",
  "knowledge_domains": [{"name": "...", "topics": [...], "references": [...], "example": "..."}],
  "recommended_resources": [{"name": "...", "url": "...", "reason": "..."}],
  "tech_preference": "...",
  "problem_solving_path": "...",
  "review_focus": ["..."],
  "suitable_questions": ["..."],
  "unsuitable_questions": ["..."]
}
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, date
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader, ChainableUndefined
    HAS_JINJA = True
except ImportError:
    HAS_JINJA = False

try:
    from validator import triple_validate
    HAS_VALIDATOR = True
except ImportError:
    HAS_VALIDATOR = False


# ---------- 模板渲染 ----------

def render_template(template_name: str, context: dict, templates_dir: Path) -> str:
    """用 jinja2 渲染模板，无 jinja2 时做简单占位符替换。"""
    if HAS_JINJA:
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            undefined=ChainableUndefined,
            keep_trailing_newline=True,
        )
        # 自动转义关闭（我们要写 markdown）
        env.autoescape = False
        tmpl = env.get_template(template_name)
        return tmpl.render(**context)
    else:
        # 退化：简单 {{ var }} 替换
        tmpl_path = templates_dir / template_name
        text = tmpl_path.read_text(encoding='utf-8')
        for k, v in context.items():
            text = text.replace('{{ ' + k + ' }}', str(v))
            text = text.replace('{{' + k + '}}', str(v))
        return text


# ---------- provenance 溯源 ----------

# 匹配 LLM 输出里的 "msg#N" 引用（N 是消息在 messages.json 数组里的下标）
MSG_REF_PATTERN = re.compile(r'^msg#(\d+)$')


def parse_msg_ref(ref) -> int | None:
    """把 'msg#4' 解析成下标 4；非法返回 None。"""
    if not isinstance(ref, str):
        return None
    m = MSG_REF_PATTERN.match(ref.strip())
    return int(m.group(1)) if m else None


def collect_refs(obj) -> list[str]:
    """递归收集 LLM 输出里所有 src_msgs / src_msg 字段的值（保留出现位置不可行，这里只要值）。"""
    refs = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ('src_msgs', 'src_msg') and v:
                refs.extend(v if isinstance(v, list) else [v])
            else:
                refs.extend(collect_refs(v))
    elif isinstance(obj, list):
        for item in obj:
            refs.extend(collect_refs(item))
    return refs


def build_provenance(llm_output: dict, messages: list[dict]) -> dict:
    """建立 msg#N ↔ 真实消息的双向映射。

    返回:
      by_ref:  {"msg#N": {真实消息详情}}，供任务书/链接库的 [src:msg#N] 标签反查
      by_msg:  {真实source_msg_id: {消息详情 + landed_in:[引用它的任务/链接]}}
    """
    # 真实 id → 它被哪些人类可读的条目引用
    landed_in: dict[str, list[str]] = {}

    # 扫描 tasks：task.name 引用了哪些 msg#N
    for task in llm_output.get('tasks', []):
        task_name = task.get('name', '?')
        for ref in task.get('src_msgs', []) or []:
            idx = parse_msg_ref(ref)
            if idx is None or idx >= len(messages):
                continue
            real_id = messages[idx].get('source_msg_id') or f'idx#{idx}'
            landed_in.setdefault(real_id, []).append(f'任务:{task_name}')

    # 扫描 refs：链接标题引用了哪个 msg#N
    for ref_item in llm_output.get('refs', []):
        title = ref_item.get('title') or ref_item.get('url', '?')
        idx = parse_msg_ref(ref_item.get('src_msg'))
        if idx is None or idx >= len(messages):
            continue
        real_id = messages[idx].get('source_msg_id') or f'idx#{idx}'
        landed_in.setdefault(real_id, []).append(f'链接:{title}')

    by_ref = {}
    by_msg = {}
    for idx, msg in enumerate(messages):
        real_id = msg.get('source_msg_id') or f'idx#{idx}'
        detail = {
            'sender': msg.get('sender'),
            'sender_id': msg.get('sender_id'),
            'time': msg.get('time'),
            'msg_type': msg.get('msg_type'),
            'content_preview': (msg.get('content') or '')[:120],
        }
        by_ref[f'msg#{idx}'] = detail
        combined = dict(detail)
        combined['landed_in'] = landed_in.get(real_id, [])
        by_msg[real_id] = combined

    return {'by_ref': by_ref, 'by_msg': by_msg}


# ---------- course-maker 实体化 ----------

def build_course_workspace(llm_output: dict, target_dir: Path, skill_dir: Path) -> Path:
    """根据 LLM 输出构建课程设计工作目录。"""
    project_name = llm_output.get('project_name', '未命名课程设计')
    deadline_str = llm_output.get('deadline', '') or ''
    deadline_uncertain = bool(llm_output.get('deadline_uncertain'))
    deadline_note = llm_output.get('deadline_note', '')
    tasks = llm_output.get('tasks', [])
    refs = llm_output.get('refs', [])
    grading = llm_output.get('grading', [])
    messages_file = llm_output.get('messages_file')
    raw_assets = llm_output.get('raw_assets', []) or []
    raw_assets_meta = llm_output.get('raw_assets_meta', []) or []

    extracted_file = llm_output.get('extracted_file')
    extracted = {}
    if extracted_file and Path(extracted_file).exists():
        try:
            extracted = json.loads(Path(extracted_file).read_text(encoding='utf-8'))
            print(f"  [+] 载入 extracted: "
                  f"{len(extracted.get('links', []))} 链接", file=sys.stderr)
        except Exception as e:
            print(f"  [!] extracted 载入失败: {e}", file=sys.stderr)

    # 链接主表:以 extracted.links 为准(规则保证不丢),refs 只贡献语义字段
    merged_links = []
    # 按(url,msg_index)匹配 LLM 标注,防止同一 URL 被多次发时覆盖错误
    ref_by_index: dict[int, dict] = {}
    for r in refs:
        idx = parse_msg_ref(r.get('src_msg')) if r.get('url') else None
        if idx is not None:
            ref_by_index[idx] = r
    for link in extracted.get('links', []):
        url = link.get('url')
        idx = link.get('msg_index')
        ref = ref_by_index.get(idx, {}) if idx is not None else {}
        # 精确 msg 匹配失败时fallback到url匹配
        if not ref and url:
            for r in refs:
                if r.get('url') == url:
                    ref = r
                    break
        merged_links.append({
            'url': url,
            'title': ref.get('title', ''),
            'sender': link.get('sender') or ref.get('sender', ''),
            'time': link.get('time') or ref.get('time', ''),
            'why': ref.get('why', '[未标注]'),
            'extract_code': link.get('extract_code'),
            'src_msg': f"msg#{idx}" if idx is not None else (ref.get('src_msg', '')),
        })
    # extracted 缺失时退回 refs(v1 行为,不破坏)
    if not merged_links:
        merged_links = refs

    # 安全清理项目名（去掉路径分隔符等）
    safe_name = ''.join(c for c in project_name if c not in '/\\:*?"<>|').strip()
    project_dir = target_dir / f'课程设计-{safe_name}'

    if project_dir.exists():
        # 不覆盖，加后缀
        project_dir = target_dir / f'课程设计-{safe_name}-{datetime.now().strftime("%H%M%S")}'

    project_dir.mkdir(parents=True, exist_ok=True)
    print(f"[*] 创建项目目录: {project_dir}", file=sys.stderr)

    # 创建子目录
    subdirs = ['01_任务说明', '02_参考资料', '02_参考资料/原始资料包',
               '03_我的实现', '04_提交', '_provenance', '_debug']
    for sd in subdirs:
        (project_dir / sd).mkdir(parents=True, exist_ok=True)

    # 计算倒计时
    days_left = None
    if deadline_str:
        try:
            deadline_date = datetime.fromisoformat(deadline_str).date()
            days_left = (deadline_date - date.today()).days
        except ValueError:
            pass

    # 准备模板上下文
    context = {
        'project_name': project_name,
        'deadline': deadline_str,
        'deadline_uncertain': deadline_uncertain,
        'deadline_note': deadline_note,
        'days_left': days_left,
        'tasks': tasks,
        'refs': merged_links,
        'grading': grading,
        'submission': llm_output.get('submission'),
        'raw_assets_meta': raw_assets_meta,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'total_messages': llm_output.get('total_messages', 0),
    }

    templates_dir = skill_dir / 'templates' / 'course-workspace'
    provenance_map = {}  # msg_id -> file_path

    # 渲染并写入每个模板文件
    template_files = [
        ('00_README.md.tmpl', '00_README.md'),
        ('00_文件信息整理.md.tmpl', '00_文件信息整理.md'),
        ('00_进度看板.md.tmpl', '00_进度看板.md'),
        ('01_任务说明/实验任务书.md.tmpl', '01_任务说明/实验任务书.md'),
        ('01_任务说明/评分标准.md.tmpl', '01_任务说明/评分标准.md'),
        ('02_参考资料/链接库.md.tmpl', '02_参考资料/链接库.md'),
        ('02_参考资料/设计参考资料大全.md.tmpl', '02_参考资料/设计参考资料大全.md'),
    ]

    for tmpl_name, out_name in template_files:
        try:
            content = render_template(tmpl_name, context, templates_dir)
            out_path = project_dir / out_name
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding='utf-8')
            print(f"  [+] {out_name}", file=sys.stderr)
        except Exception as e:
            print(f"  [!] 渲染失败 {tmpl_name}: {e}", file=sys.stderr)
            # 兜底：写一个占位文件
            (project_dir / out_name).write_text(
                f'# {out_name}\n\n模板渲染失败: {e}\n\n请检查 LLM 输出字段。\n',
                encoding='utf-8'
            )

    # 构建 provenance 双向映射（msg#N ↔ 真实消息）
    prov_dir = project_dir / '_provenance'
    prov_dir.mkdir(parents=True, exist_ok=True)
    if messages_file and Path(messages_file).exists():
        try:
            msgs_data = json.loads(Path(messages_file).read_text(encoding='utf-8'))
            messages = msgs_data.get('messages', [])
            provenance = build_provenance(llm_output, messages)
            # by_ref: 任务书/链接库里的 [src:msg#N] 标签反查这里
            (prov_dir / 'by-ref.json').write_text(
                json.dumps(provenance['by_ref'], ensure_ascii=False, indent=2),
                encoding='utf-8')
            # by_msg: 每条真实消息落地到哪些任务/链接
            (prov_dir / 'by-msg.json').write_text(
                json.dumps(provenance['by_msg'], ensure_ascii=False, indent=2),
                encoding='utf-8')
            referenced = sum(1 for v in provenance['by_msg'].values() if v['landed_in'])
            print(f"  [+] _provenance/ ({len(provenance['by_msg'])} 条消息, {referenced} 条被任务/链接引用)",
                  file=sys.stderr)
        except Exception as e:
            print(f"  [!] provenance 构建失败: {e}", file=sys.stderr)
    else:
        # 无 messages_file，退化写一个旧式 msg-to-file.json 占位
        (prov_dir / 'msg-to-file.json').write_text(
            json.dumps(provenance_map, ensure_ascii=False, indent=2),
            encoding='utf-8')
        print(f"  [!] 未提供 messages_file，provenance 溯源不可用", file=sys.stderr)

    # 如果有原始资料包路径，复制过来
    # raw_assets 兼容两种形式：
    #   - 字符串路径: ["path/to/网络实习.pdf", ...]
    #   - 对象:       [{"path": "...", "filename": "网络实习.pdf", "src_msg": "msg#5"}, ...]
    if raw_assets:
        assets_dir = project_dir / '02_参考资料' / '原始资料包'
        for asset in raw_assets:
            if isinstance(asset, dict):
                path_str = asset.get('path') or asset.get('src') or asset.get('filename', '')
                rename_to = asset.get('rename') or asset.get('save_as')
            else:
                path_str = str(asset)
                rename_to = None
            if not path_str:
                continue
            src = Path(path_str)
            if src.exists() and src.is_file():
                dst_name = rename_to or src.name
                shutil.copy2(src, assets_dir / dst_name)
                print(f"  [+] 复制资料: {dst_name}", file=sys.stderr)
            else:
                print(f"  [!] 资料不存在，跳过: {src}", file=sys.stderr)

    return project_dir


# ---------- person-distiller 实体化 ----------

def _merge_historical_corrections(new_corrections: list, archive_dir: Path) -> list:
    """从归档目录的历史 SOUL.md 中提取 corrections 并合并到新列表。"""
    if not archive_dir.exists():
        return new_corrections
    historical = []
    for archived_md in sorted(archive_dir.glob('*.md'), reverse=True):
        try:
            text = archived_md.read_text(encoding='utf-8')
            in_section = False
            for line in text.split('\n'):
                if '### Correction 修正记录' in line:
                    in_section = True
                    continue
                if in_section:
                    if line.strip().startswith('---'):
                        break
                    if line.startswith('- **用户反馈**'):
                        user_said = line.split('"')[1] if '"' in line else line
                        historical.append({
                            'user_said': user_said,
                            'prev_belief': '',
                            'corrected_to': '',
                            'source': '历史归档',
                            'corrected_at': '',
                        })
        except Exception:
            continue
    return historical + new_corrections


def build_persona(llm_output: dict, target_dir: Path, skill_dir: Path = None,
                  scenario: str = 'A', archive_previous: bool = True) -> Path:
    """用 jinja2 渲染 6 层 SOUL.md.tmpl（v2.0），写成 so-{name}.md。

    Args:
        llm_output: LLM 蒸馏输出的结构化 JSON（6 层字段）。
        target_dir: 产物落地目录。
        skill_dir: chat2work skill 根目录（找 templates/）。
        scenario: 'A'=蒸馏活人, 'D'=蒸馏自己（影响某些字段的默认填充）。
        archive_previous: 旧版本是否归档到 so-{name}.archive/。
    """
    target_name = llm_output.get('target_name', 'unknown')

    if skill_dir is None:
        skill_dir = Path(__file__).parent.parent

    safe_name = ''.join(c for c in target_name if c not in '/\\:*?"<>|').strip()
    out_path = target_dir / f'so-{safe_name}.md'

    # 旧版本归档（colleague-skill 的版本回滚特性）
    if archive_previous and out_path.exists():
        archive_dir = target_dir / f'so-{safe_name}.archive'
        archive_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        archive_path = archive_dir / f'so-{safe_name}.{timestamp}.md'
        shutil.move(str(out_path), str(archive_path))
        print(f"[*] 旧版本已归档: {archive_path}", file=sys.stderr)

    # 合并 historical corrections
    corrections = llm_output.get('corrections', [])
    if archive_previous:
        corrections = _merge_historical_corrections(
            corrections, target_dir / f'so-{safe_name}.archive'
        )

    # 准备 6 层模板上下文
    context = {
        # Layer 0 — 价值观底色
        'core_values': llm_output.get('core_values', []),
        'hard_rules': llm_output.get('hard_rules', []),
        'red_lines': llm_output.get('red_lines', []),
        # Layer 1 — 基础身份
        'target_name': target_name,
        'target_actual_name': llm_output.get('target_actual_name', target_name),
        'role': llm_output.get('role', ''),
        'mbti': llm_output.get('mbti', ''),
        'tech_stack': llm_output.get('tech_stack', []),
        'background_summary': llm_output.get('background_summary', ''),
        'known_resources': llm_output.get('known_resources', []),
        # Layer 2 — 表达风格
        'speech_style': llm_output.get('speech_style', ''),
        'catchphrases': llm_output.get('catchphrases', []),
        'tone_switches': llm_output.get('tone_switches', {}),
        'emoji_habits': llm_output.get('emoji_habits', ''),
        'length_tendency': llm_output.get('length_tendency', ''),
        # Layer 3 — 决策逻辑
        'tech_preference': llm_output.get('tech_preference', ''),
        'problem_solving_path': llm_output.get('problem_solving_path', ''),
        'evaluation_focus': llm_output.get('evaluation_focus', []),
        'push_or_pause': llm_output.get('push_or_pause', {}),
        # Layer 4 — 人际网络
        'audience_specific': llm_output.get('audience_specific', []),
        # Layer 5 — 红线与避坑 + Correction
        'avoid_topics': llm_output.get('avoid_topics', []),
        'corrections': corrections,
        # 辅助信息
        'knowledge_domains': llm_output.get('knowledge_domains', []),
        'recommended_resources': llm_output.get('recommended_resources', []),
        'review_focus': llm_output.get('review_focus', []),
        'qa_pattern': llm_output.get('qa_pattern', ''),
        'evaluation_focus_text': llm_output.get('evaluation_focus', []),
        'suitable_questions': llm_output.get('suitable_questions', []),
        'unsuitable_questions': llm_output.get('unsuitable_questions', []),
        'expression_habits': llm_output.get('expression_habits', ''),
        # 溯源
        'source_file': llm_output.get('source_file', ''),
        'message_count': llm_output.get('message_count', 0),
        'time_range_start': llm_output.get('time_range_start', ''),
        'time_range_end': llm_output.get('time_range_end', ''),
        'generated_at': datetime.now().strftime('%Y-%m-%d'),
        'scenario': scenario,
        # 蒸馏版本
        'distill_version': '2.0',
    }

    templates_dir = skill_dir / 'templates' / 'persona'
    if not (templates_dir / 'SOUL.md.tmpl').exists():
        raise FileNotFoundError(f"SOUL.md.tmpl 模板不存在: {templates_dir / 'SOUL.md.tmpl'}")

    soul_content = render_template('SOUL.md.tmpl', context, templates_dir)

    out_path.write_text(soul_content, encoding='utf-8')
    print(f"[*] 人物画像已生成 (v2.0 6层): {out_path}", file=sys.stderr)
    print(f"[*] 安装方式: 把此文件放到 ~/.workbuddy/experts/ 或 Claude Code 的 skills 目录", file=sys.stderr)
    return out_path


# ---------- 主入口 ----------

def main():
    ap = argparse.ArgumentParser(description='Chat2Work builder — 目录实体化')
    ap.add_argument('llm_output', help='LLM 产出的 JSON 文件')
    ap.add_argument('--target-dir', default='.', help='产物落地目录（默认当前目录）')
    ap.add_argument('--mode', choices=['course', 'distill'], help='覆盖 JSON 里的 mode')
    ap.add_argument('--skill-dir', help='chat2work skill 根目录（找 templates/）')
    ap.add_argument('--extracted-file', help='extractor 输出的 extracted.json 路径')
    ap.add_argument('--scenario', choices=['A', 'D'], default='A',
                    help='蒸馏场景：A=蒸馏活人（默认），D=蒸馏自己（支持 --self-mode 补充本人字段）')
    ap.add_argument('--archive-previous', action='store_true', default=True,
                    help='旧版本归档到 so-{name}.archive/')
    ap.add_argument('--no-archive', action='store_false', dest='archive_previous',
                    help='不归档旧版本')
    ap.add_argument('--messages-file', help='messages.json 路径（用于 validator 三重验证）')
    args = ap.parse_args()

    path = Path(args.llm_output)
    if not path.exists():
        print(f"错误：文件不存在 {path}", file=sys.stderr)
        sys.exit(1)

    llm_output = json.loads(path.read_text(encoding='utf-8'))
    if args.extracted_file:
        llm_output['extracted_file'] = args.extracted_file
    mode = args.mode or ('distill' if llm_output.get('mode') == 'person-distiller' else 'course')
    target_dir = Path(args.target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # 推断 skill 目录（向上找 templates/）
    skill_dir = Path(args.skill_dir) if args.skill_dir else Path(__file__).parent.parent

    print(f"[*] 模式: {mode}, 目标目录: {target_dir}", file=sys.stderr)

    if mode == 'course':
        project_dir = build_course_workspace(llm_output, target_dir, skill_dir)
        print(f"\n搞定啦~ 工作目录已生成: {project_dir}", file=sys.stderr)
        print(f"原聊天记录文件你自己看着删哦，我怕删错~", file=sys.stderr)
    elif mode == 'distill':
        # 三重验证（如果 messages_file 和 observations 可用）
        verification = None
        if args.messages_file and HAS_VALIDATOR:
            messages_path = Path(args.messages_file)
            if messages_path.exists():
                try:
                    msgs_data = json.loads(messages_path.read_text(encoding='utf-8'))
                    messages = msgs_data if isinstance(msgs_data, list) else msgs_data.get('messages', [])
                    observations = llm_output.get('observations', [])
                    predictions = llm_output.get('predictions', [])
                    if observations and messages:
                        verified = triple_validate(observations, predictions, messages,
                                                   llm_output.get('target_actual_name', llm_output.get('target_name', '')))
                        verification = {
                            'total': len(verified),
                            'verified_count': sum(1 for o in verified if o.get('verification_status') == 'verified'),
                            'partial_count': sum(1 for o in verified if o.get('verification_status') == 'partial'),
                            'unverified_count': sum(1 for o in verified if o.get('verification_status') == 'unverified'),
                        }
                        print(f"[*] 三重验证完成: {verification}", file=sys.stderr)
                except Exception as e:
                    print(f"[!] 三重验证跳过: {e}", file=sys.stderr)
        persona_path = build_persona(llm_output, target_dir, skill_dir,
                                     scenario=args.scenario,
                                     archive_previous=args.archive_previous)
        print(f"\n搞定啦~ 人物画像已生成: {persona_path}", file=sys.stderr)
        print(f"原聊天记录文件你自己看着删哦，我怕删错~", file=sys.stderr)
    else:
        print(f"错误：未知 mode '{mode}'", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
