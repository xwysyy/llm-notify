# llm-notify Roadmap

## v4 Current Direction

`llm-notify` is a presence-gated one-line notifier for Claude Code and Codex CLI.

The core rule is:

```text
Never disturb a present user.
Tell an absent user immediately.
Never resend what the user has already seen.
```

One deliberate exception: reply reminders (below) bypass the presence gate,
because their audience is a present-but-busy user and the cost of a missed
reminder (a full-price cache rebuild) outweighs one extra one-line ping.

v4 intentionally stays small:

- Single Python file, standard library only.
- Feishu custom webhook only.
- Hook input is the only data source; no transcript parsing, no git calls.
  (Exception: reply reminders read `/proc` to verify the claude process is
  still alive before sending.)
- Every message is one line: directory basename plus a state word
  (`完成` / `需确认` / `出错` / `N分钟未回复`). No agent name, no duration,
  no file list.
- No long-running daemon: a singleton watcher drains the queue and exits.
  (Pending reply reminders keep it alive until they fire or cancel, at most
  `notify.cache_ttl` after the anchor.)

## Implemented v4 Model

### Presence Gate

Presence is the freshest of three signals: the latest `UserPromptSubmit` timestamp, `/dev/pts` access times, and Windows `GetLastInputInfo` under WSL. Silence across all signals for `presence.away_threshold` seconds (default 120) counts as away. Unavailable signals degrade to the remaining ones.

### Decision Table

| Event | Behavior |
|:------|:---------|
| Stop, prompt explicitly asked to notify | send now |
| Stop, elapsed >= `min_elapsed` | enqueue `完成` |
| Stop, elapsed < `min_elapsed` | silent |
| Notification: `permission_prompt` / `elicitation_dialog` | enqueue `需确认`, one per session, cooldown after send |
| Notification: `idle_prompt` and others | ignore |
| StopFailure | enqueue `出错`, same cooldown |
| PostToolUse / PostToolUseFailure | refresh activity, cancel stale `需确认` entries |
| Stop / intervention (claude only) | (re)schedule `notify.reply_reminders` tiers anchored at the event |
| SessionEnd (claude only) | mark session closed, cancel all of its queued entries |

### Delivery

Hooks never send; the singleton watcher is the sole sender. While the user is present it drops completions older than `notify.seen_grace` (the user watched the result). Once the user is away it waits `notify.debounce` seconds to coalesce stragglers, then sends all live entries as one single-line message, identical parts collapsed.

### Reply Reminders (cache expiry)

Claude Code's prompt cache expires `notify.cache_ttl` (default 3600s) after the
last model activity; replying later reprocesses the whole context at full
price. When a claude session stops or gets stuck on a confirmation, llm-notify
schedules one reminder per `notify.reply_reminders` tier (default 25, 35, 45,
and 55 minutes), anchored at that event. Codex sessions are excluded by design
(cost profile does not justify it).

A reminder is cancelled if, before it fires, the session sees a new prompt or
tool activity, a `SessionEnd` hook marks it closed (`/exit`, Ctrl+D, `/clear`,
logout, resume), or the claude process recorded at prompt time is gone. The
process check walks `/proc/<pid>` with a start-time comparison to defeat pid
reuse; it exists because SessionEnd never fires when the terminal is killed
outright. If the pid was never captured (no `/proc`, unexpected process tree),
the check degrades to "assume alive" rather than suppressing reminders.

Due reminders are the only messages sent while the user is present. Each
carries a fingerprint (`last_sent_reminder_at`) so a crash between send and
dequeue cannot double-send.

### Duplicate Suppression

- A new prompt in a session cancels its queued entries; tool activity cancels queued interventions.
- Each turn carries a fingerprint (session plus start time); a sent turn is recorded in session state and never sent again, even if a stale queue entry reappears.
- A send timeout counts as delivered and is not retried; only failures that certainly never delivered (connection errors) retry once. An ambiguous network hiccup can lose one alert but never double it.
- Entries expire unsent after `notify.queue_ttl`.

Every decision is appended to `state/log.jsonl`, and `llm-notify status` shows presence readings, the queue, the watcher state, and recent decisions.

## Not Planned

- Message bodies, task summaries, or any session content in messages.
- Feishu interactive cards: the push preview only shows title text, which the single line already fills.
- Transcript or JSONL parsing.
- Remote terminal or streaming output.
- Web dashboard, account system, summary API.
- Long-running daemon.
