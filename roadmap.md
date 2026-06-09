# llm-notify Roadmap

## v2 Current Direction

`llm-notify` is now an away-after-completion receipt tool for Claude Code and Codex CLI.

The core rule is:

```text
Normal completion is gated by recent human input.
Events that require intervention notify immediately.
```

v2 intentionally stays small:

- Single Python file.
- Python standard library only.
- Feishu custom webhook only.
- Hook input is the main data source.
- No summary API.
- No daemon.
- No transcript or JSONL parsing as the primary path.
- No prompt, assistant response, command output, or diff content in Feishu messages.

## Implemented v2 Model

### Activity Gate

`UserPromptSubmit` records the latest human input timestamp. Normal completion is sent only when the user has been idle for `activity.idle_window`, default 300 seconds.

If a task completes while the user is still active, `llm-notify` writes a pending receipt and starts a one-shot `pending-check` process.

Pending behavior:

```text
same session continues -> cancel
other session receives input -> defer
no input until idle window -> send
```

### Immediate Intervention Events

These events bypass the idle gate:

- Permission request.
- Claude Code notification that needs attention.
- Stop/API failure.
- Completion with recorded tool failures.
- Prompt explicitly asks to notify when done.

### Receipt Content

Receipts contain only allowlisted metadata:

- Tool name.
- Configured machine label.
- Project name.
- Duration.
- Trigger reason.
- Changed file summary from Git status.
- Tool count and failure count.

Receipts do not include prompt text, model replies, command text, stdout, stderr, patch, or diff content.

## Future Ideas

### Feishu Card Format

The current webhook message uses text. A future version can render the same metadata as an interactive Feishu card. This should not change privacy policy or introduce transcript summaries.

### Optional Transcript Fallback

Transcript or JSONL parsing can be added later as best-effort fallback when hook state is missing. It should remain a fallback and only extract metadata.

### Feishu App Bot and Two-Way Control

Custom webhook is one-way. Two-way control requires a Feishu app bot, event subscription, and a local background service. This is a separate project scope, not part of the single-file notifier.

## Not Planned for v2

- Remote terminal or streaming output.
- Web dashboard.
- Account system.
- Summary API.
- Full transcript parsing as core logic.
- Long-running daemon.
