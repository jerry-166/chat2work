#!/usr/bin/env python3
"""
WeChatDataAnalysis MCP → chat2work messages.json 连接器

功能：
  1. 通过 MCP 直接从本机微信 WCDB 拉取聊天消息（不需要手动导出）
  2. 转换成 chat2work parser 产出的统一 Message 格式
  3. 保存为 messages.json，可直接喂给 router.py / builder.py

配置文件（优先级从高到低）：
  1. 命令行参数 --mcp-url / --token
  2. 环境变量 CHAT2WORK_MCP_URL / CHAT2WORK_MCP_TOKEN
  3. 用户目录配置文件 ~/.chat2work/mcp_config.json
  4. 工作目录配置文件 .chat2work/mcp_config.json

配置文件格式：
  {
    "mcp_url": "http://127.0.0.1:10392/mcp",
    "mcp_token": "你的token",
    "default_account": "wxid_xxx"
  }

用法：
  # 检测 MCP 是否可用（首次配置后先跑这个）
  python mcp_fetcher.py --check

  # 列出最近会话
  python mcp_fetcher.py --list

  # 搜索会话（模糊匹配）
  python mcp_fetcher.py --search "张老师"

  # 拉取某个会话的最近 N 条消息，保存为 messages.json
  python mcp_fetcher.py --session "57429214263@chatroom" --limit 100 -o messages.json

  # 用名字拉取（自动 resolve）
  python mcp_fetcher.py --name "腾讯游戏学院" --limit 200 -o messages.json

  # 保存配置到用户目录（下次不用再传 token）
  python mcp_fetcher.py --save-config --mcp-url "http://127.0.0.1:10392/mcp" --token "你的token"

依赖：只需要 Python 标准库
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError


# ============================================================
# 配置管理
# ============================================================

DEFAULT_MCP_URL = "http://127.0.0.1:10392/mcp"


def get_config_dir() -> Path:
    """获取用户配置目录（跨平台）。"""
    # Windows: %APPDATA%\chat2work 或 %USERPROFILE%\.chat2work
    # macOS/Linux: ~/.chat2work
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "chat2work"
    return Path.home() / ".chat2work"


def load_config() -> dict:
    """
    加载 MCP 配置，优先级从高到低：
    1. 环境变量
    2. 用户目录配置文件 ~/.chat2work/mcp_config.json
    3. 工作目录配置文件 ./.chat2work/mcp_config.json
    """
    config = {
        "mcp_url": DEFAULT_MCP_URL,
        "mcp_token": "",
        "default_account": "",
    }

    # 先读工作目录配置（低优先级）
    local_config = Path.cwd() / ".chat2work" / "mcp_config.json"
    if local_config.exists():
        try:
            data = json.loads(local_config.read_text(encoding="utf-8"))
            config.update({k: v for k, v in data.items() if v})
        except Exception:
            pass

    # 再读用户目录配置（中优先级）
    user_config = get_config_dir() / "mcp_config.json"
    if user_config.exists():
        try:
            data = json.loads(user_config.read_text(encoding="utf-8"))
            config.update({k: v for k, v in data.items() if v})
        except Exception:
            pass

    # 最后读环境变量（高优先级）
    env_url = os.environ.get("CHAT2WORK_MCP_URL")
    if env_url:
        config["mcp_url"] = env_url
    env_token = os.environ.get("CHAT2WORK_MCP_TOKEN")
    if env_token:
        config["mcp_token"] = env_token
    env_account = os.environ.get("CHAT2WORK_MCP_ACCOUNT")
    if env_account:
        config["default_account"] = env_account

    return config


def save_config(mcp_url: str, mcp_token: str, default_account: str = "",
                 scope: str = "user") -> Path:
    """
    保存配置到文件。

    Args:
        scope: "user" 保存到用户目录（推荐，全局生效）
               "local" 保存到当前工作目录（仅当前项目生效）
    """
    if scope == "local":
        config_dir = Path.cwd() / ".chat2work"
    else:
        config_dir = get_config_dir()

    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "mcp_config.json"

    data = {
        "mcp_url": mcp_url,
        "mcp_token": mcp_token,
        "default_account": default_account,
    }
    config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return config_path


# ============================================================
# MCP 客户端
# ============================================================

class WeChatMCP:
    """WeChatDataAnalysis MCP 极简客户端。"""

    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token
        self._req_id = 0

    def call(self, method: str, params: dict = None) -> dict:
        """调用 MCP 工具，返回 structuredContent。"""
        self._req_id += 1
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": "tools/call",
            "params": {
                "name": method,
                "arguments": params or {},
            },
        }).encode("utf-8")

        req = Request(
            self.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
            method="POST",
        )

        try:
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except URLError as e:
            raise RuntimeError(f"MCP 连接失败: {e}") from e

        if "error" in data:
            raise RuntimeError(f"MCP 错误: {data['error']}")

        result = data.get("result", {})
        # 优先读 structuredContent
        sc = result.get("structuredContent")
        if sc is not None:
            return sc

        # 退化：读 content[0].text
        content = result.get("content", [])
        if content and isinstance(content, list):
            text = content[0].get("text", "")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw_text": text}

        return result

    def check_status(self) -> dict:
        """检测 MCP 连接状态和数据可用性，返回详细状态。"""
        result = {
            "mcp_reachable": False,
            "mcp_url": self.url,
            "error": None,
            "db_ready": False,
            "accounts": [],
            "default_account": "",
            "tool_count": 0,
            "has_moments": False,
            "source": "",
        }

        try:
            status = self.call("wechat.core.get_status")
            result["mcp_reachable"] = True
            result["db_ready"] = status.get("dbReady", False)
            result["accounts"] = status.get("accounts", [])
            result["default_account"] = status.get("defaultAccount", "")
            result["tool_count"] = status.get("toolCount", 0)
            result["source"] = status.get("defaultSource", "")

            # 检查朋友圈数据
            if result["default_account"]:
                try:
                    acc_info = self.call("wechat.core.get_account_info",
                                         {"account": result["default_account"]})
                    result["has_moments"] = acc_info.get("hasSnsDb", False)
                except Exception:
                    pass

        except Exception as e:
            result["error"] = str(e)

        return result


# ============================================================
# MCP 消息 → chat2work Message 格式转换
# ============================================================

def mcp_msg_to_chat2work(msg: dict) -> dict:
    """
    将 MCP 返回的单条消息转换成 chat2work 的 Message 格式。

    MCP 消息字段示例：
      - senderDisplayName: 发送者显示名
      - senderUsername: wxid
      - createTime: unix 时间戳
      - renderType: text / link / image / file / quote / emoji / system ...
      - content: 消息内容
      - id / localId / serverId: 各种 ID
      - url / title / from / imageMd5 / objectId ...: 不同类型的附加字段

    chat2work Message 字段：
      - sender, sender_id, time, content, msg_type, meta, source_msg_id
    """
    sender = (msg.get("senderDisplayName") or msg.get("senderNickname")
              or msg.get("senderUsername") or "未知")
    sender_id = msg.get("senderUsername") or msg.get("wxid")

    # 时间戳 → ISO 8601
    create_time = msg.get("createTime")
    if create_time:
        try:
            ts = int(create_time)
            time_str = datetime.fromtimestamp(ts).isoformat()
        except (ValueError, TypeError, OSError):
            time_str = str(create_time)
    else:
        time_str = datetime.now().isoformat()

    # 消息类型映射
    render_type = msg.get("renderType", "text")
    content = msg.get("content", "") or ""

    # meta 附加信息
    meta = {}
    msg_type = render_type if render_type else "text"

    # 链接类
    if render_type == "link":
        meta["primary_url"] = msg.get("url", "")
        meta["title"] = msg.get("title", "")
        meta["source_platform"] = msg.get("from", "")
        meta["link_type"] = msg.get("linkType", "")

    # 文件类
    elif render_type == "file":
        meta["filename"] = msg.get("title", "")
        meta["object_id"] = msg.get("objectId", "")
        meta["file_size"] = msg.get("fileSize", "")
        meta["file_md5"] = msg.get("fileMd5", "")

    # 图片类
    elif render_type == "image":
        meta["image_md5"] = msg.get("imageMd5", "")
        meta["thumb_url"] = msg.get("thumbUrl", "")
        meta["image_url"] = msg.get("imageUrl", "")

    # 引用类
    elif render_type == "quote":
        meta["quote_sender"] = msg.get("fromUsername") or msg.get("quoteUsername", "")
        meta["quote_content"] = msg.get("recordItem") or msg.get("quoteContent", "")
        meta["quote_title"] = msg.get("quoteTitle", "")
        meta["quote_server_id"] = msg.get("quoteServerId", "")

    # 表情类
    elif render_type == "emoji":
        meta["emoji_md5"] = msg.get("emojiMd5", "")
        meta["emoji_url"] = msg.get("emojiUrl", "")

    # 系统消息
    elif render_type == "system":
        msg_type = "system"

    # 语音类
    elif render_type == "voice":
        meta["voice_length"] = msg.get("voiceLength", "")

    # 视频类
    elif render_type == "video":
        meta["video_md5"] = msg.get("videoMd5", "")
        meta["video_url"] = msg.get("videoUrl", "")
        meta["video_thumb_url"] = msg.get("videoThumbUrl", "")

    # 构建 chat2work 格式的消息
    return {
        "sender": sender,
        "sender_id": sender_id,
        "time": time_str,
        "content": content,
        "msg_type": msg_type,
        "meta": meta,
        "source_msg_id": (msg.get("serverIdStr") or msg.get("id")
                          or str(msg.get("localId", ""))),
    }


def fetch_session_messages(mcp: WeChatMCP, username: str, limit: int = 50,
                           account: str = None) -> list[dict]:
    """
    拉取一个会话的消息，自动分页。

    Args:
        username: 会话 ID（wxid_xxx 或 xxx@chatroom）
        limit: 最多拉取多少条
        account: 微信账号（默认用 MCP 默认账号）
    """
    all_msgs = []
    offset = 0
    page_size = min(limit, 50)  # 单页不超过 50

    while len(all_msgs) < limit:
        params = {
            "username": username,
            "limit": min(page_size, limit - len(all_msgs)),
            "offset": offset,
        }
        if account:
            params["account"] = account

        result = mcp.call("wechat.chat.get_messages", params)
        messages = result.get("messages", [])
        if not messages:
            break

        all_msgs.extend(messages)

        # 检查是否还有更多
        if not result.get("hasMore", False):
            break

        offset += len(messages)
        # 安全上限，防止意外拉取过多
        if offset > 5000:
            print(f"  ⚠️  已达 5000 条安全上限，停止拉取", file=sys.stderr)
            break

    return all_msgs[:limit]


def resolve_session(mcp: WeChatMCP, keyword: str, account: str = None) -> str | None:
    """
    模糊搜索会话，返回最佳匹配的 username。
    找不到返回 None。

    策略：
    1. 先调 resolve_session（FTS 精确搜索）
    2. 如果没结果，回退到 list_sessions + 本地模糊匹配
    """
    params = {"query": keyword}
    if account:
        params["account"] = account

    # 策略 1：调 resolve_session
    try:
        result = mcp.call("wechat.chat.resolve_session", params)
        candidates = result.get("candidates", []) or result.get("sessions", [])
        if candidates:
            top = candidates[0]
            return top.get("username") or top.get("id")
    except Exception:
        pass  # 接口不可用或报错时，回退到策略 2

    # 策略 2：list_sessions + 本地模糊匹配
    try:
        list_params = {"limit": 200}  # 多拉一点，增加匹配概率
        if account:
            list_params["account"] = account
        result = mcp.call("wechat.chat.list_sessions", list_params)
        sessions = result.get("sessions", [])

        # 按匹配度排序：精确匹配 > 包含匹配
        keyword_lower = keyword.lower()
        scored = []
        for s in sessions:
            name = (s.get("name") or s.get("displayName") or "").lower()
            if not name:
                continue
            if name == keyword_lower:
                score = 100  # 精确匹配
            elif keyword_lower in name:
                score = 50   # 包含匹配
            else:
                score = 0
            if score > 0:
                scored.append((score, s))

        if scored:
            scored.sort(key=lambda x: -x[0])
            top = scored[0][1]
            return top.get("username") or top.get("id")
    except Exception:
        pass

    return None


# ============================================================
# 状态检测输出（人类可读）
# ============================================================

def print_status(status: dict):
    """友好地打印 MCP 检测结果。"""
    print("=" * 60)
    print("  WeChatDataAnalysis MCP 状态检测")
    print("=" * 60)
    print()

    # MCP 连接状态
    if status["mcp_reachable"]:
        print(f"  ✅ MCP 服务可达")
        print(f"     地址: {status['mcp_url']}")
    else:
        print(f"  ❌ MCP 服务不可达")
        print(f"     地址: {status['mcp_url']}")
        print(f"     错误: {status['error']}")
        print()
        print("  可能的原因:")
        print("    1. WeChatDataAnalysis 没有启动")
        print("    2. MCP 服务没有开启（设置 → MCP → 启用）")
        print("    3. Token 不正确")
        print("    4. 端口号不对（默认 10392）")
        return

    print()

    # 数据库状态
    if status["db_ready"]:
        print(f"  ✅ 微信数据库就绪 (source: {status['source']})")
    else:
        print(f"  ❌ 微信数据库未就绪")

    # 账号信息
    if status["accounts"]:
        print(f"  ✅ 发现 {len(status['accounts'])} 个微信账号")
        print(f"     默认账号: {status['default_account']}")
        for i, acc in enumerate(status["accounts"]):
            marker = "（默认）" if acc == status["default_account"] else ""
            print(f"       [{i+1}] {acc}{marker}")
    else:
        print("  ⚠️  未发现微信账号")

    # 工具数量
    print(f"  🛠️  可用工具: {status['tool_count']} 个")

    # 朋友圈
    if status["has_moments"]:
        print(f"  📸 朋友圈数据: 可用")
    else:
        print(f"  📸 朋友圈数据: 不可用")

    print()
    print("=" * 60)

    if status["mcp_reachable"] and status["db_ready"]:
        print("  🎉 一切就绪！可以开始使用 MCP 自动采集了")
    elif status["mcp_reachable"]:
        print("  ⚠️  MCP 已连接但数据库未就绪，请在 WeChatDataAnalysis 中")
        print("     完成数据解密和索引构建")
    print("=" * 60)


# ============================================================
# 主入口
# ============================================================

def main():
    # 先加载配置（用于默认值）
    cfg = load_config()

    ap = argparse.ArgumentParser(
        description="WeChat MCP → chat2work 连接器：直接从本机微信拉消息，无需手动导出",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
配置方式（优先级从高到低）：
  1. 命令行参数 --mcp-url / --token
  2. 环境变量 CHAT2WORK_MCP_URL / CHAT2WORK_MCP_TOKEN
  3. 用户目录配置文件 ~/.chat2work/mcp_config.json
  4. 工作目录配置文件 ./.chat2work/mcp_config.json

首次使用：先运行 --check 检测连接，再用 --save-config 保存配置
        """.strip(),
    )
    ap.add_argument("--mcp-url", default=cfg["mcp_url"],
                    help=f"MCP endpoint URL（默认: {DEFAULT_MCP_URL}）")
    ap.add_argument("--token", default=cfg["mcp_token"],
                    help="MCP Bearer token")
    ap.add_argument("--account", default=cfg["default_account"] or None,
                    help="微信账号 wxid（默认用 MCP 默认账号）")

    # 配置管理
    ap.add_argument("--check", action="store_true",
                    help="检测 MCP 连接状态和数据可用性")
    ap.add_argument("--save-config", action="store_true",
                    help="保存当前 MCP 配置到用户目录（下次不用再传 token）")
    ap.add_argument("--config-scope", choices=["user", "local"], default="user",
                    help="--save-config 时的保存范围: user=全局（默认）, local=当前目录")

    # 操作模式
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="列出最近会话")
    mode.add_argument("--search", metavar="KEYWORD", help="搜索会话/联系人")
    mode.add_argument("--session", metavar="USERNAME", help="按会话 ID 拉取消息")
    mode.add_argument("--name", metavar="NAME", help="按名字模糊匹配后拉取消息")

    # 参数
    ap.add_argument("--limit", type=int, default=50, help="拉取消息条数（默认 50）")
    ap.add_argument("-o", "--output", default="messages.json", help="输出 JSON 路径")
    ap.add_argument("--list-limit", type=int, default=20, help="--list 时显示多少个会话")

    args = ap.parse_args()

    # --save-config：保存配置后退出
    if args.save_config:
        if not args.token:
            print("❌ --save-config 需要提供 --token", file=sys.stderr)
            sys.exit(1)
        path = save_config(args.mcp_url, args.token, args.account or "", args.config_scope)
        print(f"✅ 配置已保存到: {path}")
        print(f"   MCP URL: {args.mcp_url}")
        print(f"   Token: {args.token[:8]}...{args.token[-4:]}")
        if args.account:
            print(f"   默认账号: {args.account}")
        return

    # 没有 token 时的友好提示
    if not args.token:
        print("❌ 未配置 MCP token", file=sys.stderr)
        print(file=sys.stderr)
        print("请先配置 token，方式有三种：", file=sys.stderr)
        print("  1. 命令行参数: --token 你的token", file=sys.stderr)
        print("  2. 环境变量: set CHAT2WORK_MCP_TOKEN=你的token", file=sys.stderr)
        print("  3. 配置文件: python mcp_fetcher.py --save-config --token 你的token", file=sys.stderr)
        print(file=sys.stderr)
        print("详细配置说明见 MCP_SETUP.md", file=sys.stderr)
        sys.exit(1)

    mcp = WeChatMCP(args.mcp_url, args.token)

    # ---- 模式 0: 状态检测 ----
    if args.check:
        status = mcp.check_status()
        print_status(status)
        if not status["mcp_reachable"] or not status["db_ready"]:
            sys.exit(1)
        return

    # ---- 模式 1: 列出最近会话 ----
    if args.list:
        params = {"limit": args.list_limit}
        if args.account:
            params["account"] = args.account
        result = mcp.call("wechat.chat.list_sessions", params)
        sessions = result.get("sessions", [])
        total = result.get("total", len(sessions))

        print(f"共 {total} 个会话，显示前 {len(sessions)} 个：\n")
        print(f"{'类型':<4} {'置顶':<4} {'未读':<4} {'会话 ID':<35} {'名称':<20} {'最后消息'}")
        print("-" * 120)

        for s in sessions:
            stype = "群聊" if s.get("isGroup") else "私聊"
            top = "📌" if s.get("isTop") else ""
            unread = s.get("unreadCount", 0)
            sid = s.get("username") or s.get("id", "")
            name = s.get("name", "")[:18]
            last = (s.get("lastMessage") or "")[:30]
            last_time = s.get("lastMessageTime", "")
            print(f"{stype:<4} {top:<4} {unread:<4} {sid:<35} {name:<20} {last}  [{last_time}]")

        return

    # ---- 模式 2: 搜索会话 ----
    if args.search:
        # MCP 接口参数名是 query
        params = {"query": args.search}
        if args.account:
            params["account"] = args.account

        print(f"搜索: {args.search}\n")

        # 搜索会话
        s_candidates = []
        try:
            s_result = mcp.call("wechat.chat.resolve_session", params)
            s_candidates = s_result.get("candidates", []) or s_result.get("sessions", [])
        except Exception as e:
            print(f"  resolve_session 失败: {e}")

        # 如果 resolve_session 没结果，回退到 list_sessions 本地过滤
        if not s_candidates:
            try:
                list_params = {"limit": 200}
                if args.account:
                    list_params["account"] = args.account
                list_result = mcp.call("wechat.chat.list_sessions", list_params)
                sessions = list_result.get("sessions", [])
                keyword_lower = args.search.lower()
                s_candidates = [
                    s for s in sessions
                    if keyword_lower in (s.get("name") or "").lower()
                ][:10]
            except Exception as e:
                print(f"  list_sessions 回退失败: {e}")

        print(f"会话匹配 ({len(s_candidates)}):")
        for i, c in enumerate(s_candidates[:10]):
            sid = c.get("username") or c.get("id", "")
            name = c.get("name") or c.get("displayName", "")
            conf = c.get("confidence", "")
            conf_str = f"  置信度: {conf}" if conf else ""
            print(f"  [{i+1}] {name}  ({sid}){conf_str}")

        # 搜索联系人
        try:
            c_result = mcp.call("wechat.contacts.resolve_contact", params)
            c_candidates = c_result.get("candidates", []) or c_result.get("contacts", [])
            print(f"\n联系人匹配 ({len(c_candidates)}):")
            for i, c in enumerate(c_candidates[:10]):
                cid = c.get("username") or c.get("id", "")
                name = c.get("name") or c.get("remark") or c.get("nickname", "")
                print(f"  [{i+1}] {name}  ({cid})")
        except Exception as e:
            print(f"\n联系人搜索失败: {e}")

        return

    # ---- 模式 3/4: 拉取消息并保存 ----
    # 至少需要一个拉取模式
    if not args.session and not args.name:
        print("请指定操作模式: --list / --search / --session / --name / --check",
              file=sys.stderr)
        sys.exit(1)

    # 确定会话 ID
    if args.session:
        username = args.session
    else:  # --name
        print(f"正在解析 '{args.name}' ...")
        username = resolve_session(mcp, args.name, args.account)
        if not username:
            print(f"❌ 找不到匹配的会话: {args.name}", file=sys.stderr)
            sys.exit(1)
        print(f"✅ 匹配到会话: {username}")

    # 拉取消息
    print(f"正在拉取消息 (limit={args.limit}) ...")
    t0 = time.time()
    raw_msgs = fetch_session_messages(mcp, username, args.limit, args.account)
    elapsed = time.time() - t0
    print(f"✅ 拉取 {len(raw_msgs)} 条消息，耗时 {elapsed:.1f}s")

    # 转换格式
    print("正在转换为 chat2work 格式 ...")
    chat2work_msgs = [mcp_msg_to_chat2work(m) for m in raw_msgs]

    # 统计
    senders = {}
    msg_types = {}
    for m in chat2work_msgs:
        senders[m["sender"]] = senders.get(m["sender"], 0) + 1
        msg_types[m["msg_type"]] = msg_types.get(m["msg_type"], 0) + 1

    # 构建输出（和 parser.py 的输出格式完全一致）
    out = {
        "source_file": f"mcp://{username}",
        "source_type": "wechat_mcp_realtime",
        "total_messages": len(chat2work_msgs),
        "senders": dict(sorted(senders.items(), key=lambda x: -x[1])),
        "msg_types": msg_types,
        "time_range": {
            "start": chat2work_msgs[0]["time"] if chat2work_msgs else None,
            "end": chat2work_msgs[-1]["time"] if chat2work_msgs else None,
        },
        "messages": chat2work_msgs,
    }

    # 写入文件
    out_path = Path(args.output)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 已保存到: {out_path.resolve()}")
    print(f"   发送者: {len(senders)} 人")
    print(f"   消息类型: {msg_types}")
    print(f"\n下一步可以运行:")
    print(f"  python scripts/router.py {args.output} --mode course")
    print(f"  python scripts/router.py {args.output} --mode distill --target '某个人名'")


if __name__ == "__main__":
    main()
