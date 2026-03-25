# llm-notify Roadmap

## 现状

单文件、零依赖的飞书 webhook 通知器。通过 Claude Code 的 Stop hook 和 Codex 的 notify，在任务结束时发送纯文本消息（机器/目录/耗时/200 字摘要）。

核心问题：
- 只知道"完成了"，不知道"完成得怎么样"
- 无法从飞书下达任务指令（webhook 是单向的）

## Phase 0: 结果卡片（当前架构内，不加依赖）

**目标**：从"完成提醒"升级为"结果回执"

**做法**：
- `send_feishu` 的 `msg_type` 从 `text` 改为 `interactive`（飞书消息卡片），自定义机器人 webhook 本身就支持发卡片
- Stop hook 中读取 `transcript_path`（Claude Code 会话记录），解析 JSON 提取：
  - 改动文件列表（从 Edit/Write 工具调用中提取）
  - 执行的命令及 exit code（从 Bash 工具调用中提取）
  - 测试/lint 结果
  - 模型最终总结
- Codex 端从 `~/.codex/sessions/` 按 thread-id 读取 session 数据，做类似解析
- 卡片示意：

```
┌──────────────────────────────────────────┐
│ ✅ Claude Code 已完成                      │
│                                          │
│ 机器: lab-server                          │
│ 目录: ~/projects/api-server               │
│ 耗时: 3分42秒                             │
│                                          │
│ 改动文件: auth.py, token_service.py,      │
│          test_auth.py                     │
│                                          │
│ 执行命令:                                 │
│   pytest        ✅ exit 0                │
│   ruff check    ⚠️ exit 1 (2 warnings)   │
│                                          │
│ 摘要: 重构了 auth 模块，拆分了             │
│ token_service，补了过期续签逻辑            │
└──────────────────────────────────────────┘
```

**可选**：利用 Claude Code Stop hook 的 `decision: "block"` 能力做验收关卡——transcript 中没跑过测试或最后一条命令失败时，阻止结束并喂回 reason，让模型继续修。

**改动量**：仅改 `llm-notify` 一个文件，约 50-80 行。保持单文件、零依赖。

## Phase 1: 轻量模型总结

**目标**：用便宜的小模型对 transcript 做结构化摘要，替代人肉解析

**做法**：
- 在 stop/notify 阶段，将 transcript 关键片段发给轻量模型（DeepSeek / GPT-4o-mini / Gemini Flash 等）
- Prompt 要求输出固定格式：状态、改动摘要、风险点、下一步建议
- 模型返回的结构化 JSON 直接渲染成飞书卡片

**注意事项**：
- Hook 有 timeout 限制（当前 10 秒），API 调用可能来不及
- 两种解法：(1) 加大 hook timeout (2) hook 只落盘 transcript 路径，后台异步调模型再推卡片
- 需要在 config.json 中新增 `summary_api` 字段（endpoint、api_key、model）
- Transcript 可能很长，需要截断或只提取工具调用部分

**改动量**：新增约 100 行 API 调用 + prompt 逻辑。可能需要拆出异步推送机制。

## Phase 2: 飞书应用机器人 + 双向控制

**目标**：从飞书下达任务指令，形成"发任务 → 看回执 → 继续追单"的闭环

**为什么不能继续用自定义机器人**：
- 自定义机器人 webhook 是单向推送，发出的卡片只支持 URL 跳转，不支持按钮回调到服务端
- 无法接收用户消息

**做法**：
- 创建飞书自建应用，获取 app_id / app_secret
- 用飞书 WebSocket 长连接接收事件（不需要公网 URL）
- 本地新增一个常驻 daemon 进程（`llm-notifyd` 或独立模块）

**架构**：

```
飞书应用机器人 (单聊/菜单/卡片回调)
        ↕ WebSocket 长连接
本地 daemon (任务队列 + session 映射)
        ↕
Claude (claude -p / --continue) / Codex (app-server)
```

**支持的命令**（固定 verb，不做自然语言解析）：

```
run <project> <task>         — 新建任务
status                       — 查看当前任务列表
continue <task_id> <指令>    — 继续追问
retry <task_id>              — 重试
stop <task_id>               — 停止任务
```

**交互设计**：
- 群里继续用 Phase 0 的结果卡片做通知（保持现有链路不动）
- 单聊里用应用机器人做控制入口
- 卡片按钮支持回调：「继续追问」「重试」「查看日志」
- 卡片回调 3 秒内先回"已接收"，真正执行放后台，完成后推新卡片

**任务状态**：

```
queued → running → verifying → done / failed / needs_input
```

**存储**：JSON 文件队列即可（`jobs/<task_id>.json`），不需要 SQLite

**适配器差异**：
- Claude: 先做 one-shot（`claude -p "..." --output-format json`），后做 session steering（`--continue`）
- Codex: 可直接接 `codex app-server`（支持 thread/start、turn/steer、审批请求等完整控制面）

**改动量**：这是一个独立模块/项目，不应塞进现有的单文件通知器中。

## 不做的事情

- **不做远程终端 / 实时流式输出** — 定位是异步任务收发箱，不是 remote desktop
- **不做移动端 / Web 面板** — 飞书就是 UI
- **不做账号系统 / 多用户** — 个人工具，不需要
- **不强行统一 Claude 和 Codex 的适配层** — 两者 API 差异大，分开处理更简单

## 参考

- 飞书自定义机器人发卡片: https://open.feishu.cn/document/feishu-cards/quick-start/send-message-cards-with-custom-bot
- 飞书应用机器人概述: https://open.feishu.cn/document/client-docs/bot-v3/bot-overview
- 飞书事件订阅（长连接）: https://open.feishu.cn/document/event-subscription-guide/callback-subscription/callback-overview
- 飞书卡片交互回调: https://open.feishu.cn/document/feishu-cards/card-callback-communication
- 飞书机器人自定义菜单: https://open.feishu.cn/document/client-docs/bot-v3/bot-customized-menu
- Claude Code Hooks: https://docs.anthropic.com/en/docs/claude-code/hooks
- Codex app-server: https://developers.openai.com/codex/app-server/
- Happy (重量级参考): https://github.com/slopus/happy
