<p align="center">
  <img src="./assets/llm-notify-banner-glass.svg" alt="llm-notify banner" />
</p>

<p align="center">
  <h1 align="center">llm-notify</h1>
  <p align="center">
    <b>One-line Feishu alerts for Claude Code & Codex CLI</b>
  </p>
  <p align="center">
    <a href="./README_CN.md">中文文档</a> &nbsp;|&nbsp; English
  </p>
</p>

---

`llm-notify` sends a one-line Feishu message when Claude Code or Codex finishes a task or gets stuck waiting for you. Each message is just the working directory name plus a state word, so the push preview on your phone already tells you everything:

```text
[AI通知] llm-notify 完成
[AI通知] data-pipeline 需确认
[AI通知] proj-a 完成 · proj-b 出错
```

Delivery is gated by presence detection: keyboard and mouse signals decide whether you are at the machine, so a finished task does not buzz you while you are watching it run, and reaches you once you are actually away.

Core rule: never disturb a present user, tell an absent user immediately, never resend what the user has already seen.

## How It Works

Presence is the freshest of three signals: the latest `UserPromptSubmit` timestamp, terminal keyboard activity from `/dev/pts` access times, and (under WSL) Windows global keyboard/mouse idle via `GetLastInputInfo`. You count as away once all signals stay silent for `presence.away_threshold` seconds (default 120). An unavailable signal degrades silently to the remaining ones.

Hooks never send directly; they only record state and enqueue. The watcher is the sole sender.

```text
UserPromptSubmit
  records the latest human input time
  cancels queued alerts for this session (you are back)
  starts a new turn

PostToolUse / PostToolUseFailure
  refreshes session activity
  clears queued intervention alerts (the session is running again)

Stop
  turns shorter than notify.min_elapsed stay silent
  otherwise a "完成" entry joins the queue

Notification (permission_prompt / elicitation_dialog) -> "需确认"
StopFailure                                           -> "出错"
  one pending alert per session, with a cooldown after each send
  idle_prompt and other notification types are ignored

watch (singleton, exits when the queue is empty)
  polls presence every 30 seconds
  while you are present: drops completions older than notify.seen_grace
    (you were at the machine, you saw the result)
  once you are away: waits notify.debounce seconds for stragglers,
    then sends everything as one single-line message
```

Three rules keep duplicates out. A completion you watched for more than `notify.seen_grace` seconds is dropped as already seen. Every turn carries a fingerprint, and a turn that was sent once is never sent again. A send that times out counts as delivered instead of being retried, so an ambiguous network hiccup can lose one alert but never double it. Every decision is appended to `state/log.jsonl` and shown by `llm-notify status`.

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

The prompt asks for the webhook, secret, keyword, and away threshold, then prints a presence self-check so you can confirm the signals work on your machine.

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
  "presence": {
    "away_threshold": 120,
    "windows_input": true
  },
  "notify": {
    "min_elapsed": 45,
    "queue_ttl": 1800,
    "intervention_cooldown": 600,
    "debounce": 60,
    "seen_grace": 180
  }
}
```

| Field | Description |
|:------|:------------|
| `webhook` | Feishu custom bot webhook URL |
| `secret` | Optional signing secret |
| `keyword` | Keyword prefix for Feishu keyword verification |
| `presence.away_threshold` | Seconds of keyboard/mouse silence before you count as away |
| `presence.windows_input` | Use Windows global input idle under WSL |
| `notify.min_elapsed` | Turns shorter than this many seconds never notify |
| `notify.queue_ttl` | Queued alerts expire unsent after this many seconds |
| `notify.intervention_cooldown` | Minimum seconds between intervention alerts per session |
| `notify.debounce` | Seconds the watcher waits after the newest entry before sending, to coalesce near-simultaneous finishes |
| `notify.seen_grace` | A completion you stayed present past this many seconds is dropped as already seen |

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

## Message Format

The directory basename of the session's cwd, a space, and one of three state words: `完成` (task finished), `需确认` (waiting for a permission or MCP confirmation), `出错` (the turn failed). Multiple pending items are joined with `·` into one line; identical items collapse into one.

```text
[AI通知] llm-notify 完成
[AI通知] llm-notify 需确认
[AI通知] llm-notify 出错
[AI通知] llm-notify 完成 · data-pipeline 需确认
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

The only session data that ever leaves the machine is the directory basename and a state word. Messages contain no prompt text, no model replies, no command text, no output, no diff, no absolute paths, and no hostname. Presence detection reads timestamps and an idle counter, never input content.

## Troubleshooting

| Symptom | Check |
|:--------|:------|
| No alert arrived | Run `llm-notify status`: check the away verdict, queue contents, and recent decisions |
| Alert arrived later than expected | The watcher waits for `away_threshold` seconds of silence, then `notify.debounce` more to coalesce; polls run every 30 seconds |
| A completion never arrived | If you stayed at the machine past `notify.seen_grace` seconds, it was dropped as already seen (`cancelled/seen` in the log) |
| Short tasks never notify | Turns under `notify.min_elapsed` seconds are silent by design |
| Codex hook missing | Run `/hooks` review/trust and confirm hooks are enabled |

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
