# llm-notify v2 Plan

## Goal

`llm-notify v2` changes the product from a duration-based notifier into an away-after-completion receipt.

The core rule is:

```text
Normal completion is gated by user idle state.
Events that require user intervention notify immediately.
```

This version is a clean rewrite of the notification behavior. It does not preserve the old `min_duration` model, old command names, or old config semantics.

## Scope

v2 keeps the project small:

- Single Python script.
- Python standard library only.
- Feishu custom webhook only.
- No summary API.
- No daemon.
- No database.
- No transcript or JSONL parsing as the primary path.
- No prompt, assistant response, command output, or diff content in Feishu messages.

The main data source is hook input from Claude Code and Codex. Local JSONL or transcript parsing can be considered later as fallback only.

## User Experience

Default idle window:

```text
idle_window = 300 seconds
```

When a normal task completes:

```text
if now - global_last_human_input_at >= idle_window:
    send immediately
else:
    write a pending receipt
    spawn a one-shot pending checker
```

When a pending receipt is checked:

```text
if same_session_last_human_input_at > completed_at:
    cancel the pending receipt
elif global_last_human_input_at > last_input_at_seen:
    defer to global_last_human_input_at + idle_window
else:
    send the pending receipt
```

This means:

- If the user continues the same session, the ordinary completion receipt is cancelled.
- If the user works in another session or project, the receipt is deferred, not swallowed.
- If the user stops typing for five minutes, the receipt is sent.

Events that need intervention bypass the idle gate:

- Permission request.
- Claude Code notification that requires attention.
- Stop/API failure.
- Completion with recorded tool failures.
- Prompt explicitly asks to notify when done.

## Command Surface

v2 exposes these commands:

```text
llm-notify init
llm-notify test
llm-notify install
llm-notify event
llm-notify pending-check <pending_id>
```

The old commands are removed from the public interface:

```text
prompt-start
claude-stop
codex
```

All Claude Code and Codex hooks call `llm-notify event`. The script reads hook JSON from stdin and dispatches by event name.

## Configuration

New config shape:

```json
{
  "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/...",
  "secret": "your-signing-secret",
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

`min_duration` is removed. The main trigger is `activity.idle_window`.

## State Files

v2 stores state under the script directory:

```text
state/activity.json
state/turns/<task_id>.json
state/pending/<pending_id>.json
```

`activity.json` records recent human input:

```json
{
  "global_last_human_input_at": 1781020000.0,
  "by_session": {
    "session-id": 1781020000.0
  }
}
```

`turns/<task_id>.json` records one task:

```json
{
  "task_id": "codex-session-turn",
  "tool": "codex",
  "session_id": "...",
  "turn_id": "...",
  "started_at": 1781020000.0,
  "cwd": "/root/autodl-tmp/llm-notify",
  "git_root": "/root/autodl-tmp/llm-notify",
  "git_head_at_start": "...",
  "git_status_at_start": {},
  "tool_count": 0,
  "failure_count": 0,
  "explicit_notify": false
}
```

`pending/<pending_id>.json` records delayed receipts:

```json
{
  "pending_id": "...",
  "task_id": "...",
  "tool": "codex",
  "session_id": "...",
  "completed_at": 1781020378.0,
  "last_input_at_seen": 1781020100.0,
  "due_at": 1781020400.0,
  "status": "pending",
  "attempts": 0
}
```

State writes use atomic replace. Duplicate prevention stays simple: re-read the pending file before sending, send only if status is still `pending`, then mark it `sent`.

## Hook Events

### Claude Code

First version supports:

```text
UserPromptSubmit
PostToolUse
PostToolUseFailure
Notification
StopFailure
Stop
```

Behavior:

- `UserPromptSubmit`: update activity, create or update turn, capture Git baseline, detect explicit notify request locally, do not save prompt text.
- `PostToolUse`: increment tool count, record Edit/Write file path candidates, do not save tool input or output.
- `PostToolUseFailure`: increment failure count.
- `Notification`: notify immediately for attention-needed notification types.
- `StopFailure`: notify immediately with error category only.
- `Stop`: normal completion path through idle gate and pending.

### Codex

First version supports:

```text
UserPromptSubmit
PostToolUse
PermissionRequest
Stop
```

Behavior:

- `UserPromptSubmit`: update activity, create or update turn, capture Git baseline, detect explicit notify request locally, do not save prompt text.
- `PostToolUse`: increment tool count; record failures and edit hints without saving command, output, or patch content.
- `PermissionRequest`: notify immediately.
- `Stop`: normal completion path through idle gate and pending.

Codex `notify` is not the primary path in v2. The main path is hooks.

## Changed Files

Changed files are inferred from Git status first. No diff content is read or sent.

On `UserPromptSubmit`, capture:

```bash
git rev-parse --show-toplevel
git rev-parse HEAD
git status --porcelain=v1 -z --untracked-files=all
```

On completion, capture status again and classify:

```text
new_dirty = end - start
changed_status = paths present in both with changed status
preexisting_dirty_count = paths present in both with unchanged status
cleaned_count = start - end
```

Feishu shows only `new_dirty` and `changed_status`, capped by `content.max_changed_files`.

If Git data is unavailable, file path candidates from hooks are used as a best-effort fallback.

## Feishu Message

Default normal completion message:

```text
[AI通知] Codex 任务完成
工具: Codex
机器: autodl-box
项目: llm-notify
耗时: 6分18秒
触发: 离开后补发
改动文件:
- llm-notify
- README_CN.md
备注: 任务开始前已有脏文件 1 个
执行: 工具 5 次，失败 0 次
隐私: 未发送 prompt、回复正文、命令输出、diff 内容
```

Default message excludes:

- User prompt.
- Assistant final message.
- Input messages.
- Command text.
- stdout and stderr.
- Patch and diff content.
- Full absolute cwd.
- Real hostname.

`machine_label` is used instead of the actual hostname.

## Implementation Tasks

### Task 1: Replace Config Schema

**Files:** `llm-notify`, `config.example.json`  
**Action:** Modify  
**Dependencies:** None

Define the v2 config schema. Remove `min_duration`. Set defaults for `activity.idle_window`, `content.max_changed_files`, `content.path_mode`, and `content.include_privacy_note`.

Verification:

- `python3 -m py_compile llm-notify`
- `config.example.json` contains no `min_duration`

### Task 2: Define v2 Command Surface

**Files:** `llm-notify`  
**Action:** Modify  
**Dependencies:** Task 1

Expose only:

```text
init
test
install
event
pending-check
```

Remove old public command behavior.

Verification:

- `./llm-notify` prints v2 usage
- old commands no longer appear in usage

### Task 3: Add State Helpers

**Files:** `llm-notify`  
**Action:** Modify  
**Dependencies:** Task 2

Add helpers for reading JSON, atomic JSON writes, safe state names, and state directory creation.

Verification:

- state JSON writes are valid
- `python3 -m py_compile llm-notify`

### Task 4: Parse Hook Events

**Files:** `llm-notify`  
**Action:** Modify  
**Dependencies:** Task 3

Implement parsing for tool, event name, session id, thread id, turn id, and cwd. Read prompt only for local explicit-notify detection. Do not persist prompt text.

Verification:

- Claude `UserPromptSubmit` fixture parses session and cwd
- Codex `UserPromptSubmit` fixture parses session, turn, and cwd
- state does not contain prompt text

### Task 5: Track Activity and Turns

**Files:** `llm-notify`  
**Action:** Modify  
**Dependencies:** Task 4

On `UserPromptSubmit`, update `activity.json` and create or update `turns/<task_id>.json`.

Verification:

- fixture creates `activity.json`
- fixture creates turn JSON

### Task 6: Capture Git Baseline

**Files:** `llm-notify`  
**Action:** Modify  
**Dependencies:** Task 5

On `UserPromptSubmit`, record Git root, HEAD, and porcelain status. Ignore Git errors outside repositories.

Verification:

- in a Git repo, turn JSON includes Git baseline
- outside a Git repo, event handling succeeds

### Task 7: Record Tool Counts and File Candidates

**Files:** `llm-notify`  
**Action:** Modify  
**Dependencies:** Task 5

Handle `PostToolUse` and `PostToolUseFailure`. Record counts and safe file path candidates only.

Verification:

- tool count increments
- failure count increments
- command text, output, and patch content are not persisted

### Task 8: Summarize Changed Files

**Files:** `llm-notify`  
**Action:** Modify  
**Dependencies:** Task 6, Task 7

Compare start and end Git status, then produce a capped changed-file list and counts for preexisting or cleaned changes.

Verification:

- newly dirty file is listed
- unchanged preexisting dirty file is counted but not listed as task output
- no diff content appears

### Task 9: Render Feishu Messages

**Files:** `llm-notify`  
**Action:** Modify  
**Dependencies:** Task 8

Render messages from allowlisted metadata only.

Verification:

- no prompt, assistant message, command, stdout, stderr, patch, or diff in rendered message
- real hostname is not rendered
- file list is capped

### Task 10: Implement Completion Decision

**Files:** `llm-notify`  
**Action:** Modify  
**Dependencies:** Task 5, Task 9

Handle `Stop`, `StopFailure`, `Notification`, and `PermissionRequest`.

Rules:

- explicit notify: send now
- failure count greater than zero: send now
- intervention event: send now
- normal completion and away: send now
- normal completion and active: write pending

Verification:

- active normal completion writes pending
- away normal completion sends now
- failure sends now
- permission request sends now

### Task 11: Implement Pending Check

**Files:** `llm-notify`  
**Action:** Modify  
**Dependencies:** Task 10

Implement `pending-check`, `process_pending`, and one-shot rechecker spawn.

Verification:

- pending sends after idle window
- same-session new input cancels
- other-session new input defers
- duplicate pending checks do not duplicate sends

### Task 12: Rewrite init/test/install

**Files:** `llm-notify`  
**Action:** Modify  
**Dependencies:** Task 10

`init` writes v2 config. `test` sends a privacy-safe test message. `install` prints Claude Code and Codex hook snippets for `llm-notify event`.

Verification:

- `./llm-notify init` creates v2 config
- `./llm-notify test` sends Feishu test message
- `./llm-notify install` does not mention `codex_hooks` or old subcommands

### Task 13: Update Documentation

**Files:** `README_CN.md`, `README.md`, `roadmap.md`  
**Action:** Modify  
**Dependencies:** Task 12

Document v2 behavior, config, idle window, pending, immediate intervention events, install snippets, and privacy policy.

Verification:

- README does not present `min_duration` as the main trigger
- README does not recommend `codex_hooks = true`
- README says prompt, replies, command output, and diff are not sent by default

### Task 14: Final Validation

**Files:** all modified files  
**Action:** Verify  
**Dependencies:** Task 13

Run:

```bash
python3 -m py_compile llm-notify
./llm-notify
./llm-notify install
./llm-notify test
```

Use hand-written fixtures for:

- Claude `UserPromptSubmit`
- Claude `Stop`
- Claude attention notification
- Codex `UserPromptSubmit`
- Codex `Stop`
- Codex `PermissionRequest`
- `pending-check`

Verification:

- compile passes
- command usage matches docs
- notification test succeeds
- pending can send, cancel, and defer
- no private content leaks in rendered messages

## Decision Log

- v2 is a clean rewrite.
- Old config compatibility is intentionally omitted.
- Old command compatibility is intentionally omitted.
- `min_duration` is removed.
- `idle_window` defaults to 300 seconds.
- Normal completion uses idle gate.
- Intervention events notify immediately.
- Pending uses a one-shot checker, not a daemon.
- Hook events are the main data source.
- JSONL scanning is out of v2 first implementation.
- Feishu messages use allowlisted metadata only.
- Codex uses `[features].hooks` when a feature flag is needed; `codex_hooks` is not documented for v2.

## Residual Risks

- Hook payload fields can differ across Claude Code and Codex versions. The first implementation should be tested with real local hooks after fixture tests.
- One-shot pending checker can be killed by reboot or process cleanup. Opportunistic `process_pending()` on later events is sufficient for v2.
- Git status is a worktree hint, not an audit trail. Notifications should phrase changed files as a summary, not proof of authorship.
- If Codex `Stop` and legacy `notify` are both configured by a user, duplicate completion handling is possible. v2 install should recommend hooks only.
