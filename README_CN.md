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

`llm-notify` 在 Claude Code 或 Codex 任务结束后发送飞书回执。普通完成根据最近一次人工输入判断你是否已经离开。

核心规则：普通完成看用户是否离开；失败、显式通知请求和等待用户输入的事件立即通知。

## 特性

- **离开后回执**：默认最后一次输入 300 秒后视为离开，任务完成才通知。
- **pending 补发**：你还在输入时普通完成先挂起；继续同一会话则取消，停止输入后补发。
- **必要事件立即通知**：StopFailure、Claude idle 提醒、显式通知请求和失败任务绕过 idle gate。
- **隐私优先**：默认不发送 prompt、模型回复、命令内容、命令输出、diff。
- **单文件零依赖**：纯 Python 3 标准库，使用飞书自定义机器人 webhook。

## 工作原理

```text
UserPromptSubmit
  记录最近人工输入时间
  记录任务状态和 Git baseline

PostToolUse / PostToolUseFailure
  只记录工具次数、失败次数、文件路径候选

Stop
  普通完成入口
  如果用户已离开，立即发飞书
  如果用户仍活跃，写 pending 并派生一次性 pending-check

pending-check
  同一 session 继续输入则取消
  其他 session 输入则顺延
  没有新输入直到 idle_window 到期则补发
```

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

按提示输入 Webhook URL、Secret、关键词、机器标签和 idle window。

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

| 字段 | 说明 |
|:-----|:-----|
| `webhook` | 飞书自定义机器人 Webhook 地址 |
| `secret` | 签名校验密钥，可为空 |
| `keyword` | 飞书关键词安全校验用前缀 |
| `machine_label` | 通知里的机器标签，不使用真实 hostname |
| `activity.idle_window` | 最近一次人工输入后多少秒视为离开，默认 300 |
| `content.max_changed_files` | 通知最多展示多少个改动文件 |
| `content.path_mode` | 使用 `project` 时显示项目名和相对路径 |
| `content.include_privacy_note` | 是否显示隐私说明 |

普通完成由 `idle_window` 和 pending 状态决定。配置中的 `min_duration` 不参与普通完成通知判断。

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

`UserPromptSubmit` 记录最近人工输入，`Stop` 处理普通完成回执，`PostToolUse` 记录工具次数、失败次数和文件路径候选。权限审批事件保持静默。

Codex hooks 通常默认启用。如果你显式关闭过 hooks，可在 `~/.codex/config.toml` 设置：

```toml
[features]
hooks = true
```

Codex 中需要运行 `/hooks` review/trust 这些命令 hook。

## 通知示例

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

## 命令

| 子命令 | 说明 |
|:-------|:-----|
| `init` | 交互式生成配置 |
| `test` | 发送飞书连通性测试 |
| `install` | 打印 Claude Code / Codex hooks 配置片段 |
| `event` | hook 统一入口，从 stdin 读取 JSON |
| `pending-check <pending_id>` | 一次性 pending 补发检查 |

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

通知只使用 allowlist 元数据：工具、机器标签、项目名、耗时、触发原因、改动文件相对路径、工具次数、失败次数。

## 常见问题

| 现象 | 排查方法 |
|:-----|:---------|
| 收不到普通完成通知 | 检查是否仍在 `idle_window` 内；pending 会在离开窗口后补发 |
| Codex hook 未触发 | 运行 `/hooks` review/trust，并确认 hooks 未被禁用 |
| 通知里没有摘要 | 默认不发送模型回复，避免泄露会话内容 |
| 改动文件不完整 | Git status 是工作区提示，不是严格审计；非 Git 目录只做 best-effort |

## 环境要求

- Python 3.6+
- 能访问 `open.feishu.cn`

## 许可证

[MIT](./LICENSE)
