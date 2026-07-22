# WeChatDataAnalysis MCP 配置指南

> 配置好 MCP 后，chat2work 可以直接从本机微信读取数据，不需要手动导出聊天记录。

---

## 一、你需要什么

| 项目 | 说明 | 获取方式 |
|------|------|---------|
| **WeChatDataAnalysis** 桌面应用 | 微信数据解密和分析工具 | 官网下载 |
| **MCP Token** | 用于鉴权的一串字符 | 在 WeChatDataAnalysis 设置中生成 |
| **本机微信已登录** | 数据来源 | 正常登录微信桌面版 |

---

## 二、下载和安装 WeChatDataAnalysis

### 1. 下载

访问官方网站下载最新版：

- **官网**：https://github.com/LifeArchiveProject/WeChatDataAnalysis
- **GitHub**：https://github.com/LifeArchiveProject/WeChatDataAnalysis

> 选择对应系统的安装包（Windows / macOS），下载后安装。

### 2. 首次使用

1. 打开 WeChatDataAnalysis
2. 按照引导完成微信数据解密（需要微信桌面版已登录）
3. 等待数据索引构建完成（首次可能需要几分钟到几十分钟，取决于消息量）

---

## 三、开启 MCP 服务并获取 Token

### 步骤

1. 打开 WeChatDataAnalysis
2. 进入 **设置 → MCP**（或 **设置 → 开发者 → MCP 服务**）
3. 开启 **MCP 服务** 开关
4. 点击 **生成 Token**（或 **重置 Token**）
5. 复制生成的 Token（类似 `gJm0RMUaRqfhsjUlqE7y7crYklJPwdYYJqUWReTuvmE`）

> 默认 MCP 地址：`http://127.0.0.1:10392/mcp`
> 如果端口被占用，可以在设置中修改。

---

## 四、在 chat2work 中配置 Token

有三种配置方式，任选一种即可：

### 方式一：保存到配置文件（推荐，一次配置永久生效）

```bash
cd chat2work

# 保存配置到用户目录（全局生效）
python scripts/mcp_fetcher.py --save-config \
  --mcp-url "http://127.0.0.1:10392/mcp" \
  --token "你的Token"
```

配置文件位置：
- **Windows**：`%APPDATA%\chat2work\mcp_config.json`
- **macOS / Linux**：`~/.chat2work/mcp_config.json`

如果只想在当前项目生效：
```bash
python scripts/mcp_fetcher.py --save-config --config-scope local --token "你的Token"
```

### 方式二：环境变量

```bash
# Windows (PowerShell)
$env:CHAT2WORK_MCP_TOKEN = "你的Token"
$env:CHAT2WORK_MCP_URL = "http://127.0.0.1:10392/mcp"

# macOS / Linux
export CHAT2WORK_MCP_TOKEN="你的Token"
export CHAT2WORK_MCP_URL="http://127.0.0.1:10392/mcp"
```

### 方式三：每次命令行传参

```bash
python scripts/mcp_fetcher.py --list --token "你的Token"
```

---

## 五、验证配置是否成功

配置好后，运行检测命令：

```bash
python scripts/mcp_fetcher.py --check
```

**成功时的输出：**

```
============================================================
  WeChatDataAnalysis MCP 状态检测
============================================================

  ✅ MCP 服务可达
     地址: http://127.0.0.1:10392/mcp

  ✅ 微信数据库就绪 (source: realtime)
  ✅ 发现 2 个微信账号
     默认账号: wxid_xxx
       [1] wxid_xxx（默认）
       [2] wxid_xxx_428b
  🛠️  可用工具: 52 个
  📸 朋友圈数据: 可用

============================================================
  🎉 一切就绪！可以开始使用 MCP 自动采集了
============================================================
```

**失败时的常见原因：**

| 现象 | 可能原因 | 解决方法 |
|------|---------|---------|
| MCP 服务不可达 | WeChatDataAnalysis 没启动 | 启动应用 |
| MCP 服务不可达 | MCP 开关没打开 | 设置 → MCP → 开启 |
| MCP 服务不可达 | Token 错误 | 重新生成 Token |
| MCP 服务不可达 | 端口不对 | 检查设置中的端口号 |
| 数据库未就绪 | 数据还在解密/索引中 | 等待完成，或在应用中检查状态 |

---

## 六、配置完成后能做什么

### 1. 直接浏览微信会话

```bash
# 列出最近会话
python scripts/mcp_fetcher.py --list

# 搜索某个人/某个群
python scripts/mcp_fetcher.py --search "张老师"
```

### 2. 一键拉取消息 → 直接用于 chat2work

```bash
# 按群名拉取最近 200 条消息
python scripts/mcp_fetcher.py --name "课程设计群" --limit 200 -o messages.json

# 然后直接走 chat2work 流程
python scripts/router.py messages.json --mode course
# ...（LLM 处理后）...
python scripts/builder.py llm_output.json --mode course
```

### 3. 蒸馏某个人物

```bash
# 从某个群里拉取消息，蒸馏某个人
python scripts/mcp_fetcher.py --name "工作群" --limit 500 -o messages.json
python scripts/router.py messages.json --mode distill --target "王总"
# ...（LLM 处理后）...
python scripts/builder.py llm_output.json --mode distill
```

### 4. 可用的 MCP 能力总览

| 能力 | 说明 | 工具示例 |
|------|------|---------|
| **聊天消息** | 读取会话、搜索消息、获取上下文 | `list_sessions`, `get_messages`, `search_messages` |
| **联系人** | 搜索联系人、获取头像 | `resolve_contact`, `get_avatar_url` |
| **朋友圈** | 浏览时间线、搜索、获取媒体 | `list_timeline`, `search_moments` |
| **媒体资源** | 获取图片/语音/视频 URL | `get_chat_image_url`, `get_chat_voice_url` |
| **统计分析** | 年度报告、消息统计、支付记录 | `get_wrapped_card`, `get_daily_message_counts` |
| **公众号** | 公众号消息、支付记录 | `biz.get_messages`, `biz.get_pay_records` |

> 共 52 个工具，覆盖 8 个功能包。详见 SKILL.md 的 MCP 工具清单。

---

## 七、常见问题

### Q: Token 会过期吗？
A: 一般不会，只要你不重置 Token 就一直有效。如果 Token 泄露了，在设置里点"重置 Token"即可。

### Q: 关闭 WeChatDataAnalysis 后还能用吗？
A: 不能。MCP 服务是 WeChatDataAnalysis 的一部分，应用关闭后服务也会停止。需要保持应用在后台运行。

### Q: 安全吗？数据会上传吗？
A: MCP 服务运行在本机（127.0.0.1），所有数据都在本地，不会上传到任何服务器。Token 只是本机鉴权用的。

### Q: 可以同时配置多个微信账号吗？
A: 可以。WeChatDataAnalysis 支持多账号，MCP 会自动列出所有可用账号，默认使用第一个。可以用 `--account` 参数指定。

### Q: 消息数据是实时的吗？
A: 默认 `source=auto`，会优先从实时微信 WCDB 读取（微信桌面版登录时可用），数据是最新的。如果微信没登录，会回退到已解密的快照数据。

---

## 八、配置优先级

如果同时配置了多处，按以下优先级生效（高优先级覆盖低优先级）：

1. **命令行参数** `--token` / `--mcp-url`（最高）
2. **环境变量** `CHAT2WORK_MCP_TOKEN` / `CHAT2WORK_MCP_URL`
3. **用户目录配置文件** `~/.chat2work/mcp_config.json`
4. **工作目录配置文件** `./.chat2work/mcp_config.json`（最低）

---

## 下一步

配置完成后，回到 [README.md](README.md) 查看完整使用流程，或直接运行：

```bash
python scripts/mcp_fetcher.py --list
```
