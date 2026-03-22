<p align="center">
  <h1 align="center">llm-notify</h1>
  <p align="center">
    <b>Claude Code & Codex CLI 飞书通知器</b>
  </p>
  <p align="center">
    中文文档 &nbsp;|&nbsp; <a href="./README.md">English</a>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/python-3.6+-blue?logo=python&logoColor=white" alt="Python 3.6+">
    <img src="https://img.shields.io/badge/依赖-零-brightgreen" alt="零依赖">
    <img src="https://img.shields.io/badge/Claude_Code-hook-blueviolet?logo=anthropic" alt="Claude Code">
    <img src="https://img.shields.io/badge/Codex_CLI-notify-orange?logo=openai" alt="Codex CLI">
    <img src="https://img.shields.io/github/license/xwysyy/llm-notify" alt="License">
  </p>
</p>

---

AI 编程任务动辄几分钟，不必守着终端干等——任务完成后自动收到**飞书通知**。

## 特性

- **单文件，零依赖** — 纯 Python 3 标准库，无需 pip install
- **双端支持** — 同时兼容 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 和 [Codex CLI](https://github.com/openai/codex)
- **智能过滤** — 仅在任务耗时超过设定阈值（如 60 秒）时通知，避免刷屏
- **安全签名** — 支持飞书 HMAC-SHA256 签名校验
- **即拿即用** — 整个工具在 `~/.llm-notify/` 目录内自包含，`scp` 到新服务器即可运行

## 工作原理

```
                          ┌──────────────────────────────┐
  用户发送提示词 ────────► │  UserPromptSubmit hook        │
                          │  prompt-start: 记录时间戳     │
                          └──────────────────────────────┘
                                       ...
                                  （AI 工作中）
                                       ...
                          ┌──────────────────────────────┐
  任务完成 ─────────────► │  Stop hook / notify           │
                          │  claude-stop / codex          │
                          │                               │
                          │  耗时 > min_duration ?        │
                          │    是 ──► 飞书 webhook 通知   │
                          │    否 ──► 跳过                │
                          └──────────────────────────────┘
```

## 快速开始

### 1. 安装

```bash
git clone https://github.com/xwysyy/llm-notify.git ~/.llm-notify
chmod +x ~/.llm-notify/llm-notify
```

### 2. 创建飞书 Webhook

> 需要使用飞书**电脑端**（手机端无此入口）。

1. 创建一个群聊（可以只有你自己）
2. **群设置** → **群机器人** → **添加机器人** → **自定义机器人**
3. 安全设置选择**签名校验**
4. 复制 **Webhook URL** 和 **Secret**

### 3. 初始化配置

```bash
~/.llm-notify/llm-notify init
```

按提示输入：Webhook URL、签名密钥、关键词、最短通知时长。

### 4. 验证连通性

```bash
~/.llm-notify/llm-notify test
```

检查飞书群是否收到测试消息。

### 5. 接入 Claude Code / Codex

```bash
~/.llm-notify/llm-notify install
```

会打印配置片段，按下方说明手动合并到对应配置文件中。

## 接入配置

### Claude Code

在 `~/.claude/settings.json` 的 `"hooks"` 对象中添加：

```jsonc
{
  "hooks": {
    // ... 已有的 hooks ...
    "UserPromptSubmit": [
      // ... 已有的条目 ...
      {
        "hooks": [{
          "type": "command",
          "command": "~/.llm-notify/llm-notify prompt-start",
          "timeout": 3
        }]
      }
    ],
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": "~/.llm-notify/llm-notify claude-stop",
          "timeout": 10
        }]
      }
    ]
  }
}
```

### Codex CLI

**`~/.codex/config.toml`** ：

```toml
# 顶层添加
notify = ["~/.llm-notify/llm-notify", "codex"]

# 启用 hooks 功能（用于耗时过滤）
[features]
codex_hooks = true
```

**`~/.codex/hooks.json`**（新建此文件）：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [{
          "type": "command",
          "command": "~/.llm-notify/llm-notify prompt-start",
          "timeout": 3
        }]
      }
    ]
  }
}
```

> **说明：** `notify` 负责任务完成时触发通知；`hooks.json` 负责记录开始时间以支持耗时过滤。
> 如果你的 Codex 版本不支持 `codex_hooks` 功能，通知仍然正常工作，只是无法过滤短任务。

## 配置说明

`~/.llm-notify/config.json`（由 `init` 命令生成）：

```json
{
  "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx",
  "secret": "your-secret",
  "keyword": "[AI通知]",
  "min_duration": 60
}
```

| 字段 | 必填 | 默认值 | 说明 |
|:-----|:----:|:------:|:-----|
| `webhook` | 是 | — | 飞书自定义机器人 Webhook 地址 |
| `secret` | 否 | — | 签名校验密钥 |
| `keyword` | 否 | — | 消息中不含该关键词时自动前缀（用于关键词安全校验） |
| `min_duration` | 否 | `0` | 最短通知时长（秒），任务耗时低于此值不通知。`0` = 始终通知 |

## 通知效果

```
[AI通知]
Claude Code 已完成
机器: my-server
目录: /home/user/project
耗时: 3分42秒
摘要: Refactored the authentication module, updated 5 files...
```

## 命令一览

| 子命令 | 触发方 | 说明 |
|:-------|:-------|:-----|
| `init` | 用户手动 | 交互式配置 → 生成 `config.json` |
| `test` | 用户手动 | 发送测试通知 |
| `install` | 用户手动 | 打印 Claude Code / Codex 的 hook 配置片段 |
| `prompt-start` | `UserPromptSubmit` hook | 记录任务开始时间戳 |
| `claude-stop` | Claude Code `Stop` hook | 判断耗时 & 发送通知（stdin JSON） |
| `codex` | Codex `notify` | 判断耗时 & 发送通知（argv JSON） |

## 多服务器部署

```bash
scp -r ~/.llm-notify/ user@new-server:~/.llm-notify/
ssh user@new-server '~/.llm-notify/llm-notify test'
# 然后在新服务器上配置 hooks
```

每条通知都包含**机器名**，多台服务器同时使用也能一眼看出是哪台完成的。

## 常见问题

| 现象 | 排查方法 |
|:-----|:---------|
| 收不到通知 | 运行 `llm-notify test` 验证连通性；检查 `min_duration` 是否过滤了短任务 |
| Hook 阻塞了 Claude / Codex | 理论上不会发生——所有 hook 子命令捕获全部异常并 exit 0。诊断：`echo '{}' \| llm-notify claude-stop 2>&1` |
| Codex 耗时过滤不生效 | 确认 `config.toml` 中 `[features]` 有 `codex_hooks = true`，且 `~/.codex/hooks.json` 已创建 |

## 环境要求

- Python 3.6+
- 能访问 `open.feishu.cn` 的网络环境

## 许可证

[MIT](./LICENSE)
