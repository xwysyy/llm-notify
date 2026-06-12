# llm-notify Roadmap

## v3 Current Direction

`llm-notify` is a presence-gated receipt tool for Claude Code and Codex CLI.

The core rule is:

```text
Never disturb a present user.
Tell an absent user immediately.
Never resend what the user has already seen.
```

v3 intentionally stays small:

- Single Python file.
- Python standard library only.
- Feishu custom webhook only.
- Hook input is the main data source.
- No summary API.
- No long-running daemon: a singleton watcher drains the queue and exits.
- No transcript or JSONL parsing as the primary path.
- No prompt, assistant response, command output, or diff content in Feishu messages.

## Implemented v3 Model

### Presence Gate

Presence is the freshest of three signals: the latest `UserPromptSubmit` timestamp, `/dev/pts` access times, and Windows `GetLastInputInfo` under WSL. Silence across all signals for `presence.away_threshold` seconds (default 120) counts as away. Unavailable signals degrade to the remaining ones.

### Decision Table

| Event | Present | Away |
|:------|:--------|:-----|
| Stop, prompt explicitly asked to notify | send now | send now |
| Stop, elapsed >= `min_elapsed` | queue | send now |
| Stop, elapsed < `min_elapsed` | silent | silent |
| StopFailure | queue | send now |
| Notification: `permission_prompt` / `elicitation_dialog` | queue | send now, with cooldown |
| Notification: `idle_prompt` and others | ignore | ignore |
| PostToolUseFailure | count into receipt body | count into receipt body |

### Delivery

Queued entries are sent by a singleton watcher once the user leaves, aggregated into one message. A new prompt in the session cancels its queued entries; tool activity cancels queued intervention alerts; entries expire after `notify.queue_ttl`. Every decision is appended to `state/log.jsonl`, and `llm-notify status` shows presence readings, the queue, the watcher state, and recent decisions.

### Receipt Content

Receipts contain only allowlisted metadata:

- Tool name.
- Configured machine label.
- Project name.
- Duration.
- Trigger reason.
- Changed file summary from Git status.
- Tool count and failure count.

Receipts do not include prompt text, model replies, command text, stdout, stderr, patch, or diff content. Presence detection reads timestamps and an idle counter, never input content.

## Future Ideas

### Feishu Card Format

The current webhook message uses text. A future version can render the same metadata as an interactive Feishu card. This should not change privacy policy or introduce transcript summaries.

### Optional Transcript Fallback

Transcript or JSONL parsing can be added later as best-effort fallback when hook state is missing. It should remain a fallback and only extract metadata.

### Feishu App Bot and Two-Way Control

Custom webhook is one-way. Two-way control requires a Feishu app bot, event subscription, and a local background service. This is a separate project scope, not part of the single-file notifier.

## Not Planned

- Remote terminal or streaming output.
- Web dashboard.
- Account system.
- Summary API.
- Full transcript parsing as core logic.
- Long-running daemon.
