<p align="center">
  <img src="./assets/llm-notify-banner-glass.svg" alt="llm-notify banner" />
</p>

<p align="center">
  <h1 align="center">llm-notify</h1>
  <p align="center">
    <b>Feishu task receipts for Claude Code & Codex CLI</b>
  </p>
  <p align="center">
    <a href="./README_CN.md">中文文档</a> &nbsp;|&nbsp; English
  </p>
</p>

---

`llm-notify` sends a Feishu receipt when Claude Code or Codex finishes a task or gets stuck waiting for you. Delivery is gated by presence detection: keyboard and mouse signals decide whether you are at the machine, so a finished task does not buzz you while you are watching it run, and reaches you once you are actually away.

Core rule: never disturb a present user, tell an absent user immediately, never resend what the user has already seen.

## How It Works

Presence is the freshest of three signals: the latest `UserPromptSubmit` timestamp, terminal keyboard activity from `/dev/pts` access times, and (under WSL) Windows global keyboard/mouse idle via `GetLastInputInfo`. You count as away once all signals stay silent for `presence.away_threshold` seconds (default 120). An unavailable signal degrades silently to the remaining ones.

```text
UserPromptSubmit
  records the latest human input time
  starts a new turn with a Git baseline
  cancels queued receipts for this session (you are back)

PostToolUse / PostToolUseFailure
  counts tool calls and failures, collects safe file path candidates
  clears queued intervention alerts (the session is running again)

Stop
  away    sends the completion receipt immediately
  present queues the receipt for the watcher
  turns shorter than notify.min_elapsed stay silent

Notification (permission_prompt / elicitation_dialog) and StopFailure
  away    sends an intervention alert immediately, with a cooldown
  present queues it; later tool activity in the session cancels it
  idle_prompt and other notification types are ignored

watch (singleton, exits when the queue is empty)
  polls presence every 30 seconds
  cancels entries whose session has continued, drops expired entries
  once you are away, sends everything in one aggregated message
```

Receipts queued while you are present are delivered by the watcher after you leave, aggregated into a single message when several tasks finished. Returning to a session cancels its queued receipts, and entries older than `notify.queue_ttl` expire unsent. Tool failures are reported inside the receipt body instead of triggering a notification by themselves. Every decision is appended to `state/log.jsonl` and shown by `llm-notify status`.

## Quick Start

### 1. Install

```bash
git clone https://github.com/xwysyy/llm-notify.git ~/.llm-notify
chmod +x ~/.llm-notify/llm-notify
```

### 2. Create a Feishu Webhook

Use the Feishu desktop app.

1. Create a group chat.
2. Open group settings -> bots -> add bot -> custom bot.
3. Enable signature verification.
4. Copy the Webhook URL and Secret.

### 3. Initialize Config

```bash
~/.llm-notify/llm-notify init
```

The prompt asks for the webhook, secret, keyword, machine label, and away threshold, then prints a presence self-check so you can confirm the signals work on your machine.

### 4. Test Connectivity

```bash
~/.llm-notify/llm-notify test
```

### 5. Install Hooks

```bash
~/.llm-notify/llm-notify install
```

The command prints Claude Code and Codex hook snippets.

## Configuration

`~/.llm-notify/config.json`:

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

| Field | Description |
|:------|:------------|
| `webhook` | Feishu custom bot webhook URL |
| `secret` | Optional signing secret |
| `keyword` | Keyword prefix for Feishu keyword verification |
| `machine_label` | Label shown in receipts instead of the real hostname |
| `presence.away_threshold` | Seconds of keyboard/mouse silence before you count as away |
| `presence.windows_input` | Use Windows global input idle under WSL |
| `notify.min_elapsed` | Turns shorter than this many seconds never notify |
| `notify.queue_ttl` | Queued receipts expire unsent after this many seconds |
| `notify.intervention_cooldown` | Minimum seconds between intervention alerts per session |
| `content.max_changed_files` | Maximum changed files to show |
| `content.path_mode` | `project` shows project name and relative paths |
| `content.include_privacy_note` | Whether to include the privacy note |

## Hook Setup

### Claude Code

Add `llm-notify event claude` to these events in `~/.claude/settings.json`:

```text
UserPromptSubmit
PostToolUse
PostToolUseFailure
Notification
StopFailure
Stop
```

Run `llm-notify install` for the full JSON snippet.

### Codex CLI

Add `llm-notify event codex` to these events in `~/.codex/hooks.json`:

```text
UserPromptSubmit
PostToolUse
Stop
```

Codex hooks are usually enabled by default. If hooks were explicitly disabled, set:

```toml
[features]
hooks = true
```

Run `/hooks` in Codex to review and trust the command hooks.

## Notification Examples

A single receipt:

```text
[AI通知] Claude Code 任务完成
工具: Claude Code
机器: autodl-box
项目: llm-notify
耗时: 6分18秒
触发: 离开时完成
改动文件:
- llm-notify
- README.md
执行: 工具 5 次，失败 0 次
隐私: 未发送 prompt、回复正文、命令输出、diff 内容
```

Several tasks finished before you left, aggregated by the watcher:

```text
[AI通知] 离开期间 2 项更新
机器: autodl-box
1. Claude Code 任务完成 · llm-notify · 9分30秒 · 改动 3 个文件
2. Codex 需要处理 · data-pipeline · 权限确认
隐私: 未发送 prompt、回复正文、命令输出、diff 内容
```

## Commands

| Command | Description |
|:--------|:------------|
| `init` | Create config interactively, with a presence self-check |
| `test` | Send a Feishu connectivity test |
| `install` | Print Claude Code and Codex hook snippets |
| `status` | Show presence readings, away verdict, queue, watcher state, recent decisions |
| `event` | Hook entrypoint, reads JSON from stdin |
| `watch` | Internal singleton queue watcher, spawned automatically |

## Privacy

Feishu messages use metadata only and exclude:

- User prompt.
- Assistant final response.
- Codex input messages.
- Command text.
- stdout / stderr.
- patch / diff.
- Full absolute cwd.
- Real hostname.

Receipts only use allowlisted metadata: tool, machine label, project name, duration, trigger reason, relative changed file paths, tool count, and failure count. Presence detection reads timestamps and an idle counter, never input content.

## Troubleshooting

| Symptom | Check |
|:--------|:------|
| No receipt arrived | Run `llm-notify status`: check the away verdict, queue contents, and recent decisions |
| Receipt arrived later than expected | The watcher polls every 30 seconds and waits for `away_threshold` seconds of silence |
| Short tasks never notify | Turns under `notify.min_elapsed` seconds are silent by design |
| Codex hook missing | Run `/hooks` review/trust and confirm hooks are enabled |
| Changed files look incomplete | Git status is a worktree hint, not an audit trail; worktrees with more than 5000 dirty or untracked files are reported as undeterminable |

## Development

```bash
python3 tests/test_behavior.py
```

The behavior tests drive the script through `event` and `watch` against a local mock Feishu server; no real webhook is touched.

## Requirements

- Python 3.7+
- Linux or WSL2. Without `/dev/pts` or PowerShell, presence falls back to prompt timestamps.
- Network access to `open.feishu.cn`

## License

[MIT](./LICENSE)
