<p align="center">
  <img src="./assets/llm-notify-banner-glass.svg" alt="llm-notify banner" />
</p>

<p align="center">
  <h1 align="center">llm-notify</h1>
  <p align="center">
    <b>Claude Code & Codex CLI 飞书任务回执</b>
  </p>
  <p align="center">
    中文文档 &nbsp;|&nbsp; <a href="./README.md">English</a>
  </p>
</p>

---

`llm-notify` 在 Claude Code 或 Codex 任务结束、或卡在等你确认时发送飞书回执。是否送达由在场检测决定：用键盘鼠标信号判断你是否在电脑前，你盯着任务跑完时不会被打扰，真正离开后消息立刻送到。

核心规则：在场永不打扰，离开立即知道，看过的永不补发。

## 工作原理

在场状态取三个信号中最新的一个：最近一次 `UserPromptSubmit` 的时间、`/dev/pts` 终端键盘活动时间，以及 WSL 下通过 `GetLastInputInfo` 读取的 Windows 全局键鼠空闲。所有信号静默超过 `presence.away_threshold` 秒（默认 120）即视为离开。某个信号不可用时自动退化到其余信号。

```text
UserPromptSubmit
  记录最近人工输入时间
  开启新 turn 并记录 Git baseline
  取消该会话排队中的回执（你回来了）

PostToolUse / PostToolUseFailure
  累计工具次数与失败次数，收集安全的文件路径候选
  清除排队中的干预提醒（会话又跑起来了）

Stop
  离开    立即发送完成回执
  在场    回执进入队列交给 watcher
  耗时低于 notify.min_elapsed 的 turn 保持静默

Notification（permission_prompt / elicitation_dialog）与 StopFailure
  离开    立即发送干预提醒，带冷却
  在场    进入队列；会话后续有工具活动则取消
  idle_prompt 等其他通知类型一律忽略

watch（单例，队列空了自动退出）
  每 30 秒检测一次在场状态
  会话已继续的条目取消，超时条目作废
  检测到你离开后，把所有待发内容合并成一条消息发出
```

你在场时入队的回执由 watcher 在你离开后送达，多个任务先后完成会聚合为一条消息。回到某个会话继续对话会取消它排队中的回执，超过 `notify.queue_ttl` 未送出的条目自动作废。工具调用失败只写进回执正文，不再单独触发通知。每个决策都追加到 `state/log.jsonl`，可用 `llm-notify status` 查看。

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

按提示输入 Webhook URL、Secret、关键词、机器标签和离开阈值，最后会打印一次在场信号自检，确认各信号在你机器上有效。

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
  "machine_label": "autodl-box",
  "presence": {
    "away_threshold": 120,
    "windows_input": true
  },
  "notify": {
    "min_elapsed": 45,
    "queue_ttl": 1800,
    "intervention_cooldown": 600
  },
  "content": {
    "max_changed_files": 10,
    "path_mode": "project",
    "include_privacy_note": true
  }
}
```

| 字段 | 说明 |
|:-----|:-----|
| `webhook` | 飞书自定义机器人 Webhook 地址 |
| `secret` | 签名校验密钥，可为空 |
| `keyword` | 飞书关键词安全校验用前缀 |
| `machine_label` | 通知里的机器标签，不使用真实 hostname |
| `presence.away_threshold` | 键鼠静默多少秒视为离开 |
| `presence.windows_input` | WSL 下是否使用 Windows 全局键鼠空闲信号 |
| `notify.min_elapsed` | 耗时低于该秒数的 turn 不通知 |
| `notify.queue_ttl` | 排队回执超过该秒数未送出则作废 |
| `notify.intervention_cooldown` | 同一会话两次干预提醒的最小间隔秒数 |
| `content.max_changed_files` | 通知最多展示多少个改动文件 |
| `content.path_mode` | 使用 `project` 时显示项目名和相对路径 |
| `content.include_privacy_note` | 是否显示隐私说明 |

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
```

`llm-notify install` 会打印完整 JSON 片段。

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

## 通知示例

单条回执：

```text
[AI通知] Claude Code 任务完成
工具: Claude Code
机器: autodl-box
项目: llm-notify
耗时: 6分18秒
触发: 离开时完成
改动文件:
- llm-notify
- README_CN.md
执行: 工具 5 次，失败 0 次
隐私: 未发送 prompt、回复正文、命令输出、diff 内容
```

离开前有多个任务先后完成时，watcher 聚合为一条：

```text
[AI通知] 离开期间 2 项更新
机器: autodl-box
1. Claude Code 任务完成 · llm-notify · 9分30秒 · 改动 3 个文件
2. Codex 需要处理 · data-pipeline · 权限确认
隐私: 未发送 prompt、回复正文、命令输出、diff 内容
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

默认不会发送：

- 用户 prompt。
- 模型最终回复。
- Codex input messages。
- 命令文本。
- stdout / stderr。
- patch / diff。
- 完整绝对路径。
- 真实 hostname。

通知只使用 allowlist 元数据：工具、机器标签、项目名、耗时、触发原因、改动文件相对路径、工具次数、失败次数。在场检测只读时间戳和空闲秒数，不读取任何输入内容。

## 常见问题

| 现象 | 排查方法 |
|:-----|:---------|
| 没收到回执 | 运行 `llm-notify status`，查看在场判定、队列内容和最近决策 |
| 回执比预期晚 | watcher 每 30 秒轮询一次，且需要键鼠静默满 `away_threshold` 秒 |
| 短任务从不通知 | 耗时低于 `notify.min_elapsed` 秒的 turn 按设计静默 |
| Codex hook 未触发 | 运行 `/hooks` review/trust，并确认 hooks 未被禁用 |
| 改动文件不完整 | Git status 是工作区提示，不是严格审计；脏文件或未跟踪文件超过 5000 个的工作区会标记为不可判定 |

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
