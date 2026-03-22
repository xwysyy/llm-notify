# llm-notify

Feishu (飞书) webhook notifier for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and [Codex CLI](https://github.com/openai/codex).

AI coding tasks can take minutes. Instead of watching a terminal, get a Feishu notification when it's done.

## Features

- Single Python 3 script, **zero dependencies** (stdlib only)
- Works with both **Claude Code** and **Codex CLI**
- Feishu signature verification (HMAC-SHA256)
- **Duration filtering**: only notify when a task takes longer than N seconds
- Self-contained in `~/.llm-notify/` — `scp` to another server and you're set

## How It Works

```
User prompt ──► UserPromptSubmit hook ──► prompt-start (record timestamp)
                        ...
  Task done ──► Stop hook / notify    ──► claude-stop / codex
                                            │
                                    elapsed > min_duration?
                                        yes ──► Feishu webhook
                                         no ──► skip
```

## Quick Start

### 1. Install

```bash
# Clone to ~/.llm-notify
git clone https://github.com/xwysyy/llm-notify.git ~/.llm-notify
chmod +x ~/.llm-notify/llm-notify
```

### 2. Create Feishu Webhook

1. Open Feishu **desktop app** (not mobile)
2. Create a group (can be just yourself)
3. Group Settings → Bots → Add Bot → **Custom Bot**
4. Security: choose **Sign Verification**, copy the **Webhook URL** and **Secret**

### 3. Configure

```bash
~/.llm-notify/llm-notify init
```

Follow the prompts to enter your Webhook URL, Secret, and minimum notification duration.

### 4. Verify

```bash
~/.llm-notify/llm-notify test
```

Check your Feishu group for the test message.

### 5. Hook into Claude Code / Codex

```bash
~/.llm-notify/llm-notify install
```

This prints the config snippets. Apply them manually as described below.

## Configuration

### config.json

Created by `llm-notify init`, lives at `~/.llm-notify/config.json`:

```json
{
  "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx",
  "secret": "your-secret-here",
  "keyword": "[AI通知]",
  "min_duration": 60
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `webhook` | Yes | Feishu bot webhook URL |
| `secret` | No | HMAC-SHA256 signing secret |
| `keyword` | No | Auto-prepended if message doesn't contain it (for keyword-based security) |
| `min_duration` | No | Minimum task duration in seconds to trigger notification (default: 0 = always notify) |

### Claude Code

Add to `~/.claude/settings.json` under `"hooks"`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.llm-notify/llm-notify prompt-start",
            "timeout": 3
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.llm-notify/llm-notify claude-stop",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

> If you already have `UserPromptSubmit` hooks, add the `prompt-start` entry as a new item in the array.

### Codex CLI

**~/.codex/config.toml** — add at top level:

```toml
notify = ["~/.llm-notify/llm-notify", "codex"]
```

**~/.codex/config.toml** — enable hooks feature:

```toml
[features]
codex_hooks = true
```

**~/.codex/hooks.json** — create this file:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.llm-notify/llm-notify prompt-start",
            "timeout": 3
          }
        ]
      }
    ]
  }
}
```

> The `notify` config handles task completion; `hooks.json` records the start time for duration filtering. If `codex_hooks` feature is unavailable in your Codex version, notifications still work — just without duration filtering.

## Notification Example

```
[AI通知]
Claude Code 已完成
机器: my-server
目录: /home/user/project
耗时: 3分42秒
摘要: Refactored the authentication module, updated 5 files...
```

## Subcommands

| Command | Triggered by | Description |
|---------|-------------|-------------|
| `init` | User | Interactive setup, writes config.json |
| `test` | User | Send a test notification |
| `install` | User | Print config snippets for Claude Code / Codex |
| `prompt-start` | UserPromptSubmit hook | Record task start timestamp |
| `claude-stop` | Claude Code Stop hook | Send notification (stdin JSON) |
| `codex` | Codex legacy notify | Send notification (argv JSON) |

## Deploy to Another Server

```bash
scp -r ~/.llm-notify/ user@new-server:~/
# Then on new-server:
~/.llm-notify/llm-notify test
# Configure hooks as above
```

If using the same Feishu group, the config.json works as-is. Machine name is included in every notification so you can tell which server finished.

## Troubleshooting

**No notification received:**
- Run `~/.llm-notify/llm-notify test` to verify webhook connectivity
- Check that `min_duration` isn't filtering out short tasks (set to `0` to always notify)
- For Claude Code: run with `claude --debug` and look for hook output
- Verify webhook URL hasn't expired (Feishu doesn't expire webhooks, but check bot status)

**Hook errors blocking Claude Code / Codex:**
- This should never happen. All hook subcommands catch every exception and exit 0
- Check stderr: `echo '{}' | ~/.llm-notify/llm-notify claude-stop 2>&1`

**Duration filtering not working for Codex:**
- Ensure `codex_hooks = true` is in `[features]` section of `~/.codex/config.toml`
- Ensure `~/.codex/hooks.json` exists with the `UserPromptSubmit` hook
- The `codex_hooks` feature may be under development in some Codex versions — notifications still work, just without duration filtering

## Requirements

- Python 3.6+
- Network access to `open.feishu.cn`

## License

MIT
