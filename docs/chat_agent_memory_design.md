# TradingAgents Chat Copilot — 记忆设计

> 版本：Phase C8 完成  
> 日期：2026-06-18  
> 状态：✅ 实现完成；`chat_memory.py` + `chat_safety.py` + GET/POST `/memory` 端点 + ChatContextPanel 已上线

---

## 1. 记忆设计原则

1. **最小必要原则**：只记录完成当前研究任务所需的上下文，不记录无关个人信息。
2. **用户可控**：用户可随时清空 session 记忆；所有记忆写入操作对用户可见。
3. **安全隔离**：外部数据（新闻、网页内容）不写入记忆层；写入记忆前必须经过 Orchestrator 过滤。
4. **显式优先**：Agent 依赖用户明确提供的信息，不做隐式假设。
5. **时效感知**：行情类记忆有 TTL，过期后触发重新查询。

---

## 2. 记忆分层架构

```
┌──────────────────────────────────────────────────────────────┐
│                     Memory Layer                              │
├────────────────┬─────────────────────┬────────────────────────┤
│  短期记忆       │   结构化记忆          │   任务状态记忆           │
│  Short-term    │   Structured         │   Task State           │
│  (session内)   │   (DB + session内)   │   (session内)          │
├────────────────┼─────────────────────┼────────────────────────┤
│ • 消息历史      │ • 最近搜索股票        │ • 当前任务目标           │
│ • 最近 N 轮    │ • 最近报告            │ • 已调用工具列表          │
│ • 截断窗口      │ • 自选股快照          │ • 等待确认的 action      │
│                │ • 用户语言偏好        │ • 已完成动作列表          │
│                │ • 常用市场            │ • 错误状态               │
│                │ • 常用 scope          │                        │
└────────────────┴─────────────────────┴────────────────────────┘
```

---

## 3. 短期记忆（Short-term Memory）

**存储内容：** 当前 session 内的完整消息历史（用户消息 + Agent 消息 + 工具调用记录）。

**生命周期：** session 结束时清空（MVP 不跨 session 持久化）。

**结构：**
```json
{
  "session_id": "sess_abc123",
  "messages": [
    {
      "role": "user",
      "content": "帮我分析 688146",
      "ts": "2026-06-12T10:30:00+08:00"
    },
    {
      "role": "assistant",
      "content": "我找到了中船特气（CN/688146），正在查询行情...",
      "tool_calls": [
        {
          "tool_name": "resolve_stock_tool",
          "params": { "query": "688146" },
          "result": { "found": true, "market": "CN", "symbol": "688146", "name": "中船特气" }
        },
        {
          "tool_name": "get_quote_tool",
          "params": { "market": "CN", "symbol": "688146" },
          "result": { "price": 330.5, "change_pct": 12.3 }
        }
      ],
      "ts": "2026-06-12T10:30:05+08:00"
    }
  ]
}
```

**Token 窗口管理：**
- 保留最近 20 轮对话（约 8000 tokens）
- 超出窗口时：保留第一轮（系统 prompt）+ 最近 15 轮，中间部分摘要化
- 工具调用结果：保留结构化摘要（不保留完整 Markdown 报告，仅保留 summary_snippet）

---

## 4. 结构化记忆（Structured Memory）

结构化记忆是对用户现有数据的快照视图，在每次 session 启动时从 DB 加载，在工具调用后局部更新。

### 4.1 最近搜索股票

**来源：** 用户在 session 内通过 `resolve_stock_tool` 查询过的股票。

**结构：**
```json
{
  "recent_stocks": [
    { "market": "CN", "symbol": "688146", "name": "中船特气", "last_queried_at": "2026-06-12T10:30:00+08:00" },
    { "market": "CN", "symbol": "600519", "name": "贵州茅台", "last_queried_at": "2026-06-12T09:15:00+08:00" }
  ]
}
```

**用途：** 用户说"那只股票"时可以从最近查询记录中消歧义。

**容量：** 最近 10 只，超出后移除最旧的。

---

### 4.2 最近报告

**来源：** `get_recent_reports_tool` 查询结果（session 内刷新），不在 session 启动时预加载（避免冷启动查询量）。

**结构：**
```json
{
  "recent_reports": [
    {
      "id": "rpt_xyz",
      "market": "CN",
      "symbol": "688146",
      "stock_name": "中船特气",
      "scope": "comprehensive",
      "created_at": "2026-06-11T15:30:00+08:00",
      "summary_snippet": "综合判断：分歧。技术面偏强..."
    }
  ]
}
```

**用途：** 用户说"解释上次的报告"时可快速定位。

**容量：** 最近 5 份报告快照（仅 summary_snippet，不缓存完整 Markdown）。

---

### 4.3 自选股快照

**来源：** session 启动时从 `GET /watchlist/` 加载（轻量版，不含行情数据）。在 `add_to_watchlist_tool` / `remove_from_watchlist_tool` 调用后局部更新。

**结构：**
```json
{
  "watchlist_snapshot": {
    "loaded_at": "2026-06-12T10:00:00+08:00",
    "items": [
      { "id": "wl_001", "market": "CN", "symbol": "688146", "name": "中船特气" },
      { "id": "wl_002", "market": "CN", "symbol": "600519", "name": "贵州茅台" }
    ]
  }
}
```

**用途：**
- `add_to_watchlist_tool` 前检查是否已存在（避免重复添加）
- 用户说"我的自选股"时快速列出（无需重新查询）
- `remove_from_watchlist_tool` 时提供 `watchlist_item_id`

**TTL：** session 内最多 30 分钟不刷新；超时或用户主动说"刷新自选股"时重新加载。

---

### 4.4 用户语言偏好

**来源：** 从前端 `i18n.js` 的 `language` 设置读取（通过 JWT 携带或 session 初始化时传入）。

**结构：**
```json
{
  "ui_language": "zh-CN",
  "report_output_language": "zh-CN"
}
```

**用途：**
- `create_analysis_run_tool` 自动填充 `output_language` 参数
- Agent 回复语言选择（默认与 ui_language 一致）

**更新：** 用户通过 `update_report_language_tool` 修改；或用户说"用英文生成"时在本次调用中临时覆盖。

---

### 4.5 常用市场

**来源：** 从 `recent_stocks` 统计推断（最近 3 次查询中出现最多的 market）。

**结构：**
```json
{
  "preferred_market": "CN"
}
```

**用途：** 用户输入代码但未指定市场时的默认值（如"分析 600519"→ 默认 CN）。

**注意：** 仅为辅助推断，不能确定时仍需用户确认。

---

### 4.6 常用 analysis_scope

**来源：** 从 `recent_reports` 中统计推断。

**结构：**
```json
{
  "preferred_scope": "comprehensive"
}
```

**用途：** 用户说"分析一下 688146"时（未指定范围），Planner 使用此默认值，并在确认弹窗中告知用户。

---

## 5. 任务状态记忆（Task State Memory）

**存储内容：** 当前 Planner 任务的执行状态。用于多步骤任务的中断恢复（如用户确认后继续执行）。

**生命周期：** 任务完成或用户取消后清空。每个 session 只允许一个活跃任务（避免状态混乱）。

**结构：**
```json
{
  "current_task": {
    "task_id": "task_abc",
    "goal": "为 CN/688146 生成 comprehensive 报告，完成后加入自选股",
    "plan": [
      { "step": 1, "tool": "resolve_stock_tool", "status": "completed", "result": { "name": "中船特气" } },
      { "step": 2, "tool": "create_analysis_run_tool", "status": "pending_confirmation", "params": { "scope": "comprehensive" } },
      { "step": 3, "tool": "add_to_watchlist_tool", "status": "not_started" }
    ],
    "pending_action": {
      "action_id": "act_xyz",
      "tool_name": "create_analysis_run_tool",
      "params_summary": "生成 中船特气 comprehensive 报告",
      "created_at": "2026-06-12T10:30:00+08:00",
      "expires_at": "2026-06-12T10:35:00+08:00"
    },
    "error_state": null,
    "created_at": "2026-06-12T10:29:55+08:00"
  }
}
```

**字段说明：**

| 字段 | 含义 |
|------|------|
| `goal` | 用户原始研究目标（自然语言） |
| `plan` | Planner 生成的 tool_call 序列 |
| `pending_action` | 等待用户确认的写操作（有 TTL） |
| `error_state` | 当前任务的错误信息（如工具失败原因） |

---

## 6. 不做的记忆（MVP 范围外）

| 功能 | 不做原因 |
|------|---------|
| 长期向量记忆（Embedding DB） | 需要 Pinecone / Chroma 等新依赖，复杂度过高 |
| 跨 session 消息历史持久化 | 需要新 DB 表（C6 阶段才考虑部分持久化） |
| 跨设备个人知识库 | 超出 MVP 范围 |
| 未经用户确认的敏感偏好记录 | 安全要求 |
| 交易行为记忆（持仓、买入价） | 永久不做（不支持真实交易） |
| 新闻原文 / 网页内容写入记忆 | 安全要求（prompt injection 防护） |
| 用户情绪 / 风险偏好分析 | 需要用户明确授权，MVP 不做 |

---

## 7. 安全注意事项

### 7.1 记忆污染防护

**问题：** 如果 Agent 将新闻内容或 LLM 回复中的虚假信息写入记忆，后续对话可能基于错误前提推理。

**防护措施：**
- 新闻内容（`get_latest_news_tool` 结果）**不写入任何记忆层**，仅在当前对话轮次使用
- 工具返回的外部网页内容**不写入记忆**
- 只将**结构化数据**（market、symbol、name、report_id 等）写入记忆，不写入 LLM 生成的自由文本

### 7.2 用户可清空记忆

**操作：**
- 用户说"清空对话"/"重新开始"→ 清空短期记忆 + 任务状态记忆（保留结构化记忆）
- 用户说"清空我的研究记录"→ 清空全部 session 内记忆
- 前端提供"新建对话"按钮 → 创建新 session（旧 session 数据保留但不加载）

### 7.3 写入用户资产前必须确认

任何将数据写入 DB 的操作（自选股、报告）必须经过 ConfirmationManager，记忆层不能绕过确认流程直接写入 DB。

### 7.4 记忆访问权限

- 记忆严格绑定 `session_id` + `user_id`
- 不同用户的 session 记忆完全隔离
- Agent 不能通过 session 上下文访问其他用户的数据

### 7.5 记忆过期策略

| 记忆类型 | TTL |
|---------|-----|
| 短期记忆（消息历史） | session 结束后清空 |
| 自选股快照 | session 内 30 分钟，超时重新加载 |
| 行情数据 | 不缓存（每次调用工具实时获取） |
| 任务状态 | 任务完成/取消后立即清空 |
| pending_action | 5 分钟超时自动失效 |

---

## 8. 记忆序列化格式

记忆以 Python dict 形式存储在 Orchestrator 实例中（MVP 阶段不持久化到 Redis）。

C6 阶段再考虑使用 Redis 持久化 session 记忆，支持服务重启恢复。

**内存估算（单 session）：**
- 短期记忆（20轮消息）：约 20KB
- 结构化记忆（完整字段）：约 5KB
- 任务状态记忆：约 3KB
- **合计：约 28KB / session**（可接受）
