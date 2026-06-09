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

`llm-notify` sends a Feishu receipt when Claude Code or Codex finishes a task. Normal completion uses the latest human input time to decide whether you are likely away.

Core rule: normal completion is gated by user idle state; failures, explicit notify requests, and user-input waiting events notify immediately.

## Features

- **Away receipts**: normal completion can notify once 300 seconds pass with no human input.
- **Pending delivery**: completion while you are still active is delayed; continuing the same session cancels it, stopping input sends it later.
- **Immediate required alerts**: StopFailure, Claude idle prompts, explicit notify requests, and failed tasks bypass the idle gate.
- **Privacy-first content**: no prompt, assistant response, command text, command output, or diff is sent by default.
- **Single file, zero dependencies**: Python 3 standard library and Feishu custom webhook.

## How It Works

```text
UserPromptSubmit
  records latest human input time
  records task state and Git baseline

PostToolUse / PostToolUseFailure
  records tool count, failure count, and safe file path candidates

Stop
  normal completion path
  sends immediately if the user is away
  writes pending and spawns one-shot pending-check if the user is active

pending-check
  cancels if the same session continues
  defers if another session receives input
  sends when idle_window expires with no new input
```

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
  "activity": {
    "idle_window": 300
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
| `activity.idle_window` | Idle seconds required to treat the user as away |
| `content.max_changed_files` | Maximum changed files to show |
| `content.path_mode` | `project` shows project name and relative paths |
| `content.include_privacy_note` | Whether to include the privacy note |

Normal completion is controlled by `idle_window` and pending state.

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

`UserPromptSubmit` records the latest human input, `Stop` handles normal completion receipts, and `PostToolUse` records tool counts, failure counts, and file path candidates. Permission approval events stay silent.

Codex hooks are usually enabled by default. If hooks were explicitly disabled, set:

```toml
[features]
hooks = true
```

Run `/hooks` in Codex to review and trust the command hooks.

## Notification Example

```text
[AI通知] Codex 任务完成
工具: Codex
机器: autodl-box
项目: llm-notify
耗时: 6分18秒
触发: 离开后补发
改动文件:
- llm-notify
- README.md
备注: 任务开始前已有脏文件 1 个
执行: 工具 5 次，失败 0 次
隐私: 未发送 prompt、回复正文、命令输出、diff 内容
```

## Commands

| Command | Description |
|:--------|:------------|
| `init` | Create config interactively |
| `test` | Send a Feishu connectivity test |
| `install` | Print Claude Code and Codex hook snippets |
| `event` | Hook entrypoint, reads JSON from stdin |
| `pending-check <pending_id>` | One-shot pending delivery check |

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

Receipts only use allowlisted metadata: tool, machine label, project name, duration, trigger reason, relative changed file paths, tool count, and failure count.

## Troubleshooting

| Symptom | Check |
|:--------|:------|
| No normal completion receipt | The task may still be inside `idle_window`; pending sends when the away window expires |
| Codex hook missing | Run `/hooks` review/trust and confirm hooks are enabled |
| No summary appears | Messages use metadata only |
| Changed files look incomplete | Git status is a worktree hint, not an audit trail; non-Git directories are best-effort |

## Requirements

- Python 3.6+
- Network access to `open.feishu.cn`

## License

[MIT](./LICENSE)
