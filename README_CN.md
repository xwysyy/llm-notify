<p align="center">
  <img src="./assets/llm-notify-banner-glass.svg" alt="llm-notify banner" />
</p>

<p align="center">
  <h1 align="center">llm-notify</h1>
  <p align="center">
    <b>Claude Code & Codex CLI 单行飞书提醒</b>
  </p>
  <p align="center">
    中文文档 &nbsp;|&nbsp; <a href="./README.md">English</a>
  </p>
</p>

---

`llm-notify` 在 Claude Code 或 Codex 任务结束、或卡在等你确认时发送飞书提醒。每条消息只有一行：工作目录名加一个状态词，手机推送预览本身就是全部内容：

```text
[AI通知] llm-notify 完成
[AI通知] data-pipeline 需确认
[AI通知] proj-a 完成 · proj-b 出错
```

是否送达由在场检测决定：用键盘鼠标信号判断你是否在电脑前，你盯着任务跑完时不会被打扰，真正离开后消息立刻送到。

核心规则：在场永不打扰，离开立即知道，看过的永不补发。

唯一的例外是未回复提醒：Claude Code 的模型缓存在最后一次活动约一小时后过期，过期后下一次回复要按全价重新处理整段上下文。因此 Claude 会话停下后，默认在 25、35、45 和 55 分钟各提醒一次"还没回复"，帮你赶在缓存过期前回到会话。回复、关闭会话或 claude 进程退出都会自动取消提醒；这类提醒不看在场状态，人在电脑前也照发，因为它面向的正是忙着别的事忘了回的你。

```text
[AI通知] llm-notify 25分钟未回复
```

## 工作原理

在场状态取三个信号中最新的一个：最近一次 `UserPromptSubmit` 的时间、`/dev/pts` 终端键盘活动时间，以及 WSL 下通过 `GetLastInputInfo` 读取的 Windows 全局键鼠空闲。所有信号静默超过 `presence.away_threshold` 秒（默认 120）即视为离开。某个信号不可用时自动退化到其余信号。

hook 只记录状态和入队，从不直接发送；watcher 是唯一发送点。

```text
UserPromptSubmit
  记录最近人工输入时间
  取消该会话排队中的提醒（你回来了）
  开启新 turn

PostToolUse / PostToolUseFailure
  刷新会话活动时间
  清除排队中的待确认提醒（会话又跑起来了）

Stop
  耗时低于 notify.min_elapsed 的 turn 保持静默
  否则一条「完成」进入队列
  Claude 会话另排 notify.reply_reminders 各档「未回复」提醒

Notification（permission_prompt / elicitation_dialog）-> 「需确认」
StopFailure                                          -> 「出错」
  每会话同时只挂一条，发送后有冷却
  idle_prompt 等其他通知类型一律忽略
  Claude 会话同样刷新「未回复」提醒（卡住等确认也在烧缓存）

SessionEnd（仅 Claude）
  标记会话已关闭，取消该会话所有排队条目

watch（单例，队列空了自动退出）
  每 30 秒检测一次在场状态
  到点的「未回复」提醒无视在场判定直接发出，
    发出前先确认会话没回复、没关闭、claude 进程还活着
  你在场时：完成条目排队超过 notify.seen_grace 秒即丢弃
    （你一直在机器前，结果已经看过了）
  你离开后：先等 notify.debounce 秒收拢陆续完成的任务，
    再把所有待发内容合并成一行发出
```

三条规则挡住重复提醒。完成后你继续在场超过 `notify.seen_grace` 秒的条目按已看过丢弃；每个 turn 带指纹，发过一次的永不再发；发送超时按已送达处理而不重试，网络抖动最多丢一条，绝不重复推送。每个决策都追加到 `state/log.jsonl`，可用 `llm-notify status` 查看。

## 快速开始

### 1. 安装

```bash
git clone https://github.com/xwysyy/llm-notify.git ~/.llm-notify
chmod +x ~/.llm-notify/llm-notify
```

### 2. 创建飞书 Webhook

需要使用飞书电脑端。

1. 创建一个群聊，可以只有你自己。
2. 群设置 -> 群机器人 -> 添加机器人 -> 自定义机器人。
3. 安全设置选择签名校验。
4. 复制 Webhook URL 和 Secret。

### 3. 初始化配置

```bash
~/.llm-notify/llm-notify init
```

按提示输入 Webhook URL、Secret、关键词、离开阈值和未回复提醒分钟数，最后会打印一次在场信号自检，确认各信号在你机器上有效。未回复提醒默认填写 `25,35,45,55`，输入 `none` 可关闭。

### 4. 验证连通性

```bash
~/.llm-notify/llm-notify test
```

### 5. 接入 Claude Code / Codex

```bash
~/.llm-notify/llm-notify install
```

命令会打印 Claude Code 与 Codex 的 hooks 配置片段。

## 配置

`~/.llm-notify/config.json`：

```json
{
  "webhook": "https://open.feishu.cn/open-apis/bot/.../xxxxxxxx",
  "secret": "your-secret",
  "keyword": "[AI通知]",
  "presence": {
    "away_threshold": 120,
    "windows_input": true
  },
  "notify": {
    "min_elapsed": 45,
    "queue_ttl": 1800,
    "intervention_cooldown": 600,
    "debounce": 60,
    "seen_grace": 180,
    "cache_ttl": 3600,
    "reply_reminders": [1500, 2100, 2700, 3300]
  }
}
```

| 字段 | 说明 |
|:-----|:-----|
| `webhook` | 飞书自定义机器人 Webhook 地址 |
| `secret` | 签名校验密钥，可为空 |
| `keyword` | 飞书关键词安全校验用前缀 |
| `presence.away_threshold` | 键鼠静默多少秒视为离开 |
| `presence.windows_input` | WSL 下是否使用 Windows 全局键鼠空闲信号 |
| `notify.min_elapsed` | 耗时低于该秒数的 turn 不通知 |
| `notify.queue_ttl` | 排队提醒超过该秒数未送出则作废 |
| `notify.intervention_cooldown` | 同一会话两次待确认提醒的最小间隔秒数 |
| `notify.debounce` | 离开后 watcher 先等待该秒数收拢陆续完成的任务再发送 |
| `notify.seen_grace` | 完成后你继续在场超过该秒数，该条按已看过丢弃 |
| `notify.cache_ttl` | 模型缓存有效期秒数，超过后未发出的未回复提醒作废 |
| `notify.reply_reminders` | Claude 会话停下后多少秒未回复时提醒，可配多档，置空关闭该功能 |

## Hook 配置

### Claude Code

在 `~/.claude/settings.json` 的 `hooks` 中添加 `llm-notify event claude`。推荐事件：

```text
UserPromptSubmit
PostToolUse
PostToolUseFailure
Notification
StopFailure
Stop
SessionEnd
```

`llm-notify install` 会打印完整 JSON 片段。`SessionEnd` 供未回复提醒识别会话已手动关闭（`/exit`、Ctrl+D、`/clear` 等），不配置则只能靠进程存活检测兜底。

### Codex CLI

在 `~/.codex/hooks.json` 中添加 `llm-notify event codex`。推荐事件：

```text
UserPromptSubmit
PostToolUse
Stop
```

Codex hooks 通常默认启用。如果你显式关闭过 hooks，可在 `~/.codex/config.toml` 设置：

```toml
[features]
hooks = true
```

Codex 中需要运行 `/hooks` review/trust 这些命令 hook。

## 消息格式

会话 cwd 的目录名，加空格，加状态词：`完成`（任务结束）、`需确认`（等待权限或 MCP 确认）、`出错`（该 turn 失败），以及未回复提醒的 `25分钟未回复`（分钟数随配置档位）。多个待发条目用 `·` 合并为一行，内容相同的条目只保留一个。

```text
[AI通知] llm-notify 完成
[AI通知] llm-notify 需确认
[AI通知] llm-notify 出错
[AI通知] llm-notify 25分钟未回复
[AI通知] llm-notify 完成 · data-pipeline 需确认
```

## 命令

| 子命令 | 说明 |
|:-------|:-----|
| `init` | 交互式生成配置，附带在场信号自检 |
| `test` | 发送飞书连通性测试 |
| `install` | 打印 Claude Code / Codex hooks 配置片段 |
| `status` | 查看在场信号读数、判定结果、队列、watcher 状态与最近决策 |
| `event` | hook 统一入口，从 stdin 读取 JSON |
| `watch` | 内部命令，单例队列 watcher，自动拉起 |

## 隐私策略

离开这台机器的会话数据只有目录名和一个状态词。消息不含 prompt、模型回复、命令文本、输出、diff、绝对路径和 hostname。在场检测只读时间戳和空闲秒数，不读取任何输入内容。

## 常见问题

| 现象 | 排查方法 |
|:-----|:---------|
| 没收到提醒 | 运行 `llm-notify status`，查看在场判定、队列内容和最近决策 |
| 提醒比预期晚 | 需要键鼠静默满 `away_threshold` 秒，再等 `notify.debounce` 秒收拢；watcher 每 30 秒轮询一次 |
| 某次完成没有提醒 | 完成后你在机器前停留超过 `notify.seen_grace` 秒，该条按已看过丢弃（日志中 `cancelled/seen`） |
| 短任务从不通知 | 耗时低于 `notify.min_elapsed` 秒的 turn 按设计静默 |
| 会话关了还收到未回复提醒 | 直接关终端不触发 `SessionEnd`；提醒发出前会检查 claude 进程是否存活，日志中 `cancelled/session_gone` 表示已自动取消，若仍误报请确认 SessionEnd hook 已配置 |
| 不想要未回复提醒 | `notify.reply_reminders` 置为 `[]` |
| Codex hook 未触发 | 运行 `/hooks` review/trust，并确认 hooks 未被禁用 |

## 开发

```bash
python3 tests/test_behavior.py
```

行为测试通过 `event` 和 `watch` 子命令驱动脚本，对接本地 mock 飞书服务器，不会触碰真实 webhook。

## 环境要求

- Python 3.7+
- Linux 或 WSL2。没有 `/dev/pts` 或 PowerShell 时，在场检测退化为仅用输入时间戳。
- 能访问 `open.feishu.cn`

## 许可证

[MIT](./LICENSE)
