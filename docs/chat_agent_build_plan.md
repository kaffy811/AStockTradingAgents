# TradingAgents Chat Copilot — 分阶段搭建计划

> 版本：Phase C10 完成  
> 日期：2026-06-18  
> 状态：C1 ✅ C2 ✅ C3 ✅ C4 ✅ C5 ✅ C6 ✅ C7 ✅ C8 ✅ C9 ✅ **C10 ✅**  
> 依赖：本文档所有阶段均以当前 RC（M51-b 已完成）为基线

---

## 阶段总览

| 阶段 | 名称 | 目标 | 预计规模 |
|------|------|------|---------|
| C1 | PRD & 架构设计 | 本文档，仅文档 | 6 个文档文件 |
| C2 | Chat UI MVP | `/chat` 页面骨架 | ~5 Vue 组件 |
| C3 | Chat API MVP | session + message 接口 | ~3 DB 表 + 5 路由 |
| C4 | Read-only Tools | 所有只读查询工具 | ~11 工具 |
| C5 | Action Tools + Confirmation | 写操作工具 + 确认流程 | ~5 工具 |
| C6 | Financial Skills Layer | SkillRegistry + 6 Skills | ~6 Skill 模块 ✅ |
| C7 | Controlled Planner | 复合多步骤研究任务编排 | ~3 Planner 模块 ✅ |
| C8 | Memory + Audit Hardening | 结构化记忆 + 安全审计 | chat_memory + chat_safety ✅ |
| C9 | OpenClaw-style Skill Registry | SkillSpec JSON 文件化 + 技能发现 API | 6 JSON specs + spec_loader ✅ |

---

## C1：PRD & 架构设计（已完成）

**目标：** 明确产品定位、技术架构、工具清单、记忆设计、安全边界，形成可执行的实施文档。

**交付物：**
- `docs/chat_agent_prd.md` ✅
- `docs/chat_agent_architecture.md` ✅
- `docs/chat_agent_tool_spec.md` ✅
- `docs/chat_agent_memory_design.md` ✅
- `docs/chat_agent_safety_policy.md` ✅
- `docs/chat_agent_build_plan.md` ✅（本文档）

**改动文件：** 仅 docs/，不改动 app/ 代码  
**Migration：** 无  
**新依赖：** 无

---

## C2：Chat UI MVP

**目标：** 搭建 `/chat` 页面骨架，包括消息列表、输入框、快捷任务 chips、工具调用状态展示（静态 mock 数据）、结果卡片占位。

本阶段不接入真实后端 Chat API（C3 才实现），使用 mock 数据验证 UI 交互。

**改动文件：**

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/views/ChatView.vue` | 新增 | 聊天主视图 |
| `frontend/src/components/chat/ChatMessageList.vue` | 新增 | 消息列表渲染 |
| `frontend/src/components/chat/ChatInputBar.vue` | 新增 | 输入框 + 发送按钮 |
| `frontend/src/components/chat/ChatQuickChips.vue` | 新增 | 快捷任务 chips |
| `frontend/src/components/chat/ToolCallBubble.vue` | 新增 | 工具调用状态气泡 |
| `frontend/src/components/chat/ResultCards/StockCard.vue` | 新增 | 股票行情卡片 |
| `frontend/src/components/chat/ResultCards/ReportCard.vue` | 新增 | 报告摘要卡片 |
| `frontend/src/components/chat/ResultCards/ConfirmActionCard.vue` | 新增 | 写操作确认卡片 |
| `frontend/src/router/index.js` | 修改 | 新增 `/chat` 路由 |
| `frontend/src/locales/zh-CN.json` | 修改 | 新增 `chat_*` 系列 i18n key |
| `frontend/src/locales/en-US.json` | 修改 | 同上 |
| `frontend/src/components/BottomTabBar.vue` | 修改 | 新增 Chat 标签 |
| `frontend/src/api/chat.js` | 新增 | Chat API 封装（C3 前使用 mock） |

**接口（C2 阶段 mock）：**  
不调用真实后端接口；`chat.js` 提供 `sendMessage()`、`createSession()`，返回 mock 响应。

**验收标准：**

| # | 验收项 |
|---|--------|
| C2-1 | 打开 `/chat` 页面不报错，显示欢迎消息 |
| C2-2 | 输入框可输入、发送触发 mock 响应 |
| C2-3 | 快捷任务 chips 点击填充输入框 |
| C2-4 | 工具调用气泡显示（mock tool_name + 状态） |
| C2-5 | StockCard 正确渲染 mock 行情数据 |
| C2-6 | ReportCard 正确渲染 mock 报告摘要 |
| C2-7 | ConfirmActionCard 显示确认/取消按钮 |
| C2-8 | BottomTabBar 新增 Chat 标签，点击跳转 /chat |
| C2-9 | 6 语言 chat_* key 无缺失 |
| C2-10 | npm run build 通过（~+10 modules） |

**风险：**
- UI 组件较多，注意保持与现有设计系统（CSS 变量、主题系统）一致
- Mock 数据结构应与 C3 真实接口 schema 保持一致，避免后续重构

**Migration：** 无  
**新依赖：** 无

---

## C3：Chat API MVP

**目标：** 实现 session 管理和消息收发接口，接入真实 LLM（直接回复，尚无工具调用），替换 C2 的 mock 数据。

**改动文件：**

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/routers/chat.py` | 新增 | Chat API 路由（7 个接口） |
| `backend/app/models/chat_session.py` | 新增 | ChatSession / ChatMessage 模型 + Schema |
| `backend/app/agents/chat_orchestrator.py` | 新增 | ChatAgentOrchestrator（C3 简化版：无工具，仅 LLM 直接回复） |
| `backend/app/routers/__init__.py` | 修改 | 注册 chat router |
| `backend/alembic/versions/chat_tables.py` | 新增 | migration：创建 chat_sessions + chat_messages 表 |
| `frontend/src/api/chat.js` | 修改 | 替换 mock 为真实 API 调用 |

**接口设计：**

```
POST   /api/v1/chat/sessions
  Request: { language: "zh-CN" }
  Response: { session_id: "sess_abc", created_at: "..." }

GET    /api/v1/chat/sessions/{session_id}
  Response: { session_id, messages: [...], created_at }

POST   /api/v1/chat/sessions/{session_id}/messages
  Request: { content: "帮我分析 688146" }
  Response: SSE stream（event: message_delta / message_done / error）

DELETE /api/v1/chat/sessions/{session_id}
  Response: 204 No Content
```

**数据库 Schema：**

```sql
-- chat_sessions
CREATE TABLE chat_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    language    VARCHAR(10) NOT NULL DEFAULT 'zh-CN',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- chat_messages
CREATE TABLE chat_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        VARCHAR(20) NOT NULL,   -- 'user' / 'assistant'
    content     TEXT NOT NULL,
    tool_calls  JSONB,                  -- 工具调用记录（C4+ 使用）
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**验收标准：**

| # | 验收项 |
|---|--------|
| C3-1 | POST /chat/sessions 返回 session_id |
| C3-2 | POST /messages 触发 LLM 回复（SSE 流式） |
| C3-3 | GET /sessions/{id} 返回历史消息 |
| C3-4 | DELETE /sessions/{id} 成功 204 |
| C3-5 | 未登录访问返回 401 |
| C3-6 | 访问他人 session 返回 404 |
| C3-7 | alembic upgrade head 成功（含新表） |
| C3-8 | python compileall 0 errors |
| C3-9 | npm run build 通过 |
| C3-10 | LLM 回复包含免责声明 |

**风险：**
- SSE 流式回复复用现有 `RealtimeAnalysisRunner` 基础设施，需验证 chat 场景下的兼容性
- LLM 不稳定时的降级策略：返回 "服务暂时不可用，请稍后重试"

**Migration：** 需要（创建 chat_sessions + chat_messages 表）  
**新依赖：** 无

---

## C4：Read-only Tool Registry ✅ 已完成（2026-06-18）

**目标：** 实现第一批 9 个只读查询工具，Orchestrator 具备规则意图识别和工具调用能力，结果以 ResultCards 形式返回前端。

**实际改动文件（与设计有差异，采用单文件-多工具模式）：**

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/agents/chat_tools/__init__.py` | 新增 | Tool Registry 包入口 |
| `backend/app/agents/chat_tools/base.py` | 新增 | BaseTool ABC |
| `backend/app/agents/chat_tools/tool_result.py` | 新增 | ToolResult 统一返回结构 |
| `backend/app/agents/chat_tools/registry.py` | 新增 | ToolRegistry（注册 + 调用 + 异常兜底）|
| `backend/app/agents/chat_tools/stock_tools.py` | 新增 | resolve/quote/kline/news 4 个工具 |
| `backend/app/agents/chat_tools/industry_tools.py` | 新增 | industry_hot / industry_stocks 2 个工具 |
| `backend/app/agents/chat_tools/watchlist_tools.py` | 新增 | get_watchlist 1 个工具 |
| `backend/app/agents/chat_tools/report_tools.py` | 新增 | recent_reports / report_detail 2 个工具 |
| `backend/app/agents/chat_orchestrator.py` | 新增 | 规则意图路由 + 真实工具调用 + mock confirm 流程 |
| `backend/app/routers/chat.py` | 修改（C3→C4）| 切换到 chat_orchestrator 真实工具 |
| `backend/app/services/chat_service.py` | 修改 | 元数据从 "mock" → "c4_real_tools" |
| `backend/tests/test_c4_orchestrator.py` | 新增 | 11 个单测，AsyncMock 隔离，全部 PASS |
| `frontend/src/components/chat/ChatResultCard.vue` | 修改 | 新增 watchlist_list / report_list 卡片渲染 |

**实现的 read-only 工具（9 个）：**

| 工具 | 复用服务 | 状态 |
|------|---------|------|
| resolve_stock_tool | IndustryClassificationService.search_stocks | ✅ |
| get_quote_tool | stock_data_service.get_quote_optional | ✅ |
| get_kline_summary_tool | stock_data_service.get_kline_for_agent | ✅ |
| get_latest_news_tool | news_data_service.get_stock_news | ✅ |
| get_industry_hot_tool | industry_hot_stock_service.get_industry_hot_summary | ✅ |
| get_industry_stocks_tool | industry_hot_stock_service.get_latest_hot_stocks | ✅ |
| get_watchlist_tool | DB direct (WatchlistItem) | ✅ |
| get_recent_reports_tool | DB direct (AnalysisReport) | ✅ |
| get_report_detail_tool | DB direct (AnalysisReport) | ✅ |

**验收结果：**

| # | 验收项 | 结果 |
|---|--------|------|
| C4-1 | 异动意图 → resolve+quote+kline+news 4 工具链 | ✅ |
| C4-2 | 新闻意图 → get_latest_news 调用 | ✅ |
| C4-3 | 行业热点意图 → get_industry_hot 调用 | ✅ |
| C4-4 | 查看自选股 → get_watchlist（已修复意图误判 bug）| ✅ |
| C4-5 | 解释最近报告 → get_recent_reports（修复了 recent_report 匹配范围）| ✅ |
| C4-6 | tool trace 显示真实 tool_name + status | ✅ |
| C4-7 | ResultCards 包含跳转链接 | ✅ |
| C4-8 | 无"买入/卖出/持有"等违规词 | ✅ |
| C4-9 | 数据源失败 graceful fallback | ✅ |
| C4-10 | 11 pytest PASS，意图路由 10/10 PASS | ✅ |
| C4-11 | python compileall 0 errors | ✅ |
| C4-12 | npm run build 通过（213 modules）| ✅ |

**Migration：** 无（复用 C3 表 d7e3a9b5c2f8 head）  
**新依赖：** 无

---

## C5：Action Tools + ConfirmationManager 真实执行

**目标：** 将 C3/C4 的 mock confirmation 流程升级为真实写操作执行，覆盖加入自选、生成报告、多股对比三个核心场景。同时为 C6 Skills 层预留 Orchestrator → SkillRegistry 接口。

**改动文件：**

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/agents/chat_tools/add_to_watchlist_tool.py` | 新增 | 确认后调用 `POST /watchlist` 真实接口 |
| `backend/app/agents/chat_tools/create_analysis_run_tool.py` | 新增 | 确认后调用 `POST /analysis/runs` + SSE 进度推流 |
| `backend/app/agents/chat_tools/create_compare_selection_tool.py` | 新增 | 确认后生成 `/compare?stocks=` 跳转链接 |
| `backend/app/agents/chat_orchestrator.py` | 修改 | process_confirm 接入真实写操作；预留 SkillRegistry.run() 接口 |
| `backend/app/routers/chat.py` | 修改 | confirmation 超时（5分钟）自动取消逻辑 |

**写操作原则：**
- 写操作工具不封装为 Skill（保持无副作用原则），由 Orchestrator 直接以 Action 形式调用
- confirmation 超时（5分钟）自动取消，复用 chat_messages.confirmation 字段（C3 已有）
- 每次执行写入 tool_events 含 confirmed_at 时间戳

**验收标准：**

| # | 验收项 |
|---|--------|
| C5-1 | "加入自选" → 触发确认卡片，确认后成功写入 watchlist DB |
| C5-2 | "加入自选" → 取消后不执行任何写操作 |
| C5-3 | "加入自选" → 5 分钟超时后自动取消 |
| C5-4 | "生成报告" → 确认后 SSE 实时进度，完成后返回报告摘要 |
| C5-5 | "对比 600519 和 000858" → 确认后返回 /compare?stocks= 跳转链接 |
| C5-6 | 重复加入自选股（已在自选）→ 友好提示，不重复写入 |
| C5-7 | 所有写操作写入 tool_events（含 confirmed_at） |
| C5-8 | python compileall 0 errors |
| C5-9 | npm run build 通过 |

**风险：**
- create_analysis_run_tool 依赖现有 analysis/runs 接口 + SSE 基础设施，需验证 chat session 下的 SSE 事件路由
- confirmation pending_action 存于 chat_messages 表，服务重启不丢失（无内存依赖）

**Migration：** 无（复用 C3 confirmation 字段）  
**新依赖：** 无

---

## C6：Financial Skills Layer

**目标：** 将多个工具调用组织为结构化、可复用的金融研究技能（Skills），沉淀常见投研模式。

**改动文件：**

```
backend/app/agents/chat_skills/
├── __init__.py           — BaseSkill + SkillResult + SkillRegistry 导出
├── base_skill.py         — BaseSkill ABC (async run → SkillResult)
├── skill_result.py       — SkillResult dataclass (sections/cards/disclaimer)
├── registry.py           — SkillRegistry (register/call/异常兜底)
├── stock_anomaly_skill.py      — resolve→quote→kline→news
├── risk_first_skill.py         — resolve→kline→report→news
├── news_catalyst_skill.py      — resolve→news→quote 印证
├── watchlist_review_skill.py   — watchlist→quote→kline 异动股
├── industry_hotspot_skill.py   — industry_hot→industry_stocks
└── report_explanation_skill.py — recent_reports→report_detail→quote
```

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/agents/chat_skills/` | 新增目录 | 上述 10 个文件 |
| `backend/app/agents/chat_orchestrator.py` | 修改 | 意图路由命中 Skill 时调用 SkillRegistry.run() |
| `frontend/src/components/chat/ChatResultCard.vue` | 修改 | SkillResult.sections 映射为结构化 answer + cards |

**设计原则：**
- Skill 内部通过注入的 ToolRegistry 调用现有工具，不重复实现数据获取
- Skill 执行记录 tool_events，前端 ChatToolTrace 可展示调用链
- 失败降级：部分工具失败时，Skill 仍输出已获取维度，标注数据缺失
- 每个 SkillResult 必须含 _DISCLAIMER 免责声明

**验收标准：**

| # | 验收项 |
|---|--------|
| C6-1 | "为什么 688146 今天涨这么多" → Stock Anomaly Skill 4工具链 |
| C6-2 | "帮我看 600519 的风险" → Risk-first Skill |
| C6-3 | "今天哪些行业值得研究" → Industry Hotspot Skill |
| C6-4 | "解释我最近的报告" → Report Explanation Skill |
| C6-5 | 巡检自选股 → Watchlist Review Skill 输出异动股列表 |
| C6-6 | 单工具失败时 Skill 降级输出（不崩溃） |
| C6-7 | tool_events 记录 Skill 调用链，前端 ChatToolTrace 展示 |
| C6-8 | python compileall 0 errors |
| C6-9 | npm run build 通过 |

> 完整 Skills 规范见 [`docs/chat_agent_skills.md`](chat_agent_skills.md)

**Migration：** 无  
**新依赖：** 无

---

## C7：Controlled Planner — 多步骤金融研究任务编排 ✅ 完成

**目标：** 支持多步骤研究任务拆解（最多 5 步），让 Agent 能自动规划复合任务，遇到写操作自动挂起等待确认。

**实现方式：** 纯规则（正则），无 LLM — 响应快、可测试、行为可预期。

**改动文件：**

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/agents/chat_planner/base.py` | 新增 | PlanStep / PlannerResult / ExecutionResult dataclasses |
| `backend/app/agents/chat_planner/rule_based_planner.py` | 新增 | RuleBasedPlanner（纯正则规则，无 LLM） |
| `backend/app/agents/chat_planner/executor.py` | 新增 | PlannerExecutor（顺序执行 Steps，安全合规输出） |
| `backend/app/agents/chat_planner/__init__.py` | 新增 | 包入口 |
| `backend/app/agents/chat_skills/registry.py` | 修改 | 新增 select_by_name() |
| `backend/app/agents/chat_orchestrator.py` | 修改 | C7 → 6 层分发，Planner 插入第 3 层 |
| `backend/tests/test_c7_rule_based_planner.py` | 新增 | 39 个 RuleBasedPlanner 测试 |
| `backend/tests/test_c7_planner_executor.py` | 新增 | 14 个 PlannerExecutor 测试 |
| `backend/tests/test_c7_orchestrator_integration.py` | 新增 | 12 个 Orchestrator 集成测试 |

**Planner 执行流（实际实现）：**

```
用户输入 → RuleBasedPlanner.is_compound() 检测复合任务
        → plan() 生成 PlannerResult（6 种 intent_type）
        → PlannerExecutor.execute() 逐步执行
            - skill step: SkillRegistry.select_by_name() → skill.run()
            - action step: make_confirmation() ONLY（不直接执行写操作）
            - final_summary: _synthesize() 聚合结果
        → 返回 ExecutionResult（answer + tool_events + cards + confirmation + metadata）
```

**6 种复合任务类型：**

| intent_type | 触发条件 | 步骤 |
|---|---|---|
| anomaly_then_risk | 异动信号 + 风险信号 | anomaly_skill → risk_skill → summary |
| report_then_risk | 报告信号 + 风险信号 | report_skill → risk_skill → summary |
| watchlist_scan | 自选 + 巡检信号 | watchlist_review → summary |
| industry_then_stocks | 行业 + 个股信号 | industry_hotspot → summary |
| research_then_action | 研究 + 加自选信号 | [skill] → summary → add_watchlist(confirm) |
| compare_then_report | 对比 + 报告生成 | create_compare(confirm) + clarification |

**验收结果（65/65 PASS）：**

| # | 验收项 | 结果 |
|---|--------|------|
| C7-1 | anomaly_then_risk 生成 3 步计划（anomaly/risk/summary） | ✅ |
| C7-2 | action step 只生成 confirmation，不执行写操作 | ✅ |
| C7-3 | confirmation status=pending，type=add_watchlist | ✅ |
| C7-4 | MAX_STEPS=5 强制截断 | ✅ |
| C7-5 | 单步失败不崩溃，step.status="failed"，继续执行 | ✅ |
| C7-6 | metadata.planner_used=True, plan_intent_type 字段 | ✅ |
| C7-7 | 禁止词语（买入/卖出/必涨）从 answer 中剥离 | ✅ |
| C7-8 | _DISCLAIMER 出现在所有 Planner answer 中 | ✅ |
| C7-9 | 安全守卫在 Planner 之前拦截 | ✅ |
| C7-10 | python compileall 0 errors，137/137 tests pass | ✅ |

**Migration：** 无  
**新依赖：** 无

---

## C8：Memory + Audit Hardening

**目标：** 实现结构化记忆层（跨轮次上下文感知）+ Audit Trail DB 持久化 + Prompt Injection 防护强化。

**改动文件：**

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/agents/chat_memory.py` | 新增 | Memory Layer（短期/结构化/任务状态 3 层） |
| `backend/app/models/chat_audit.py` | 新增 | ChatAuditLog DB 模型 |
| `backend/alembic/versions/chat_audit_table.py` | 新增 | migration：创建 chat_audit_logs 表 |
| `backend/app/agents/chat_orchestrator.py` | 修改 | 接入 Memory Layer；Prompt Injection 防护强化 |

**记忆持久化策略：**

| 记忆类型 | 存储方式 | 说明 |
|---------|---------|------|
| 短期记忆（消息历史） | 内存（session 内有效） | 最近 N 轮消息 |
| 结构化记忆（最近搜索股票/语言偏好） | chat_sessions.metadata JSONB | DB 持久化 |
| 任务状态记忆（Planner 进度） | 内存（session 内有效） | 不跨 session |
| 自选股快照 | 内存（TTL=30分钟，按需加载） | 从 DB 加载 |

**安全强化：**
- 新闻/报告内容截断 + 外部数据类型标注（防 Prompt Injection）
- 外部内容不写入结构化记忆（Memory 污染防护）
- 用户清空记忆：`DELETE /chat/sessions/{id}` + memory flush

**验收标准：**

| # | 验收项 |
|---|--------|
| C8-1 | "那只股票" → 从 recent_stocks 消歧义 |
| C8-2 | "用英文生成报告" → 后续报告默认 en-US（session 内持久） |
| C8-3 | session 重新加载时，metadata 语言偏好被恢复 |
| C8-4 | 新闻 prompt injection 尝试不触发写操作 |
| C8-5 | 所有工具调用写入 chat_audit_logs（session 可查） |
| C8-6 | 用户清空 session → memory flush 验证 |
| C8-7 | alembic upgrade head 成功 |
| C8-8 | python compileall 0 errors |
| C8-9 | npm run build 通过 |

**风险：**
- 内存存储在多 worker 环境下不共享（参考 M40-b AnalysisRunRegistry 解决方案）
- C8 MVP 接受单 worker 约束，多 worker 支持延至后续版本（可复用 Redis）

**Migration：** 需要（chat_audit_logs 表 + chat_sessions.metadata 字段）  
**新依赖：** 无

---

## C9：OpenClaw-style Skill Registry

**目标：** 将 C6 Skills 升级为完整的 OpenClaw-style Skill Registry，支持技能规格文件、依赖工具声明、安全约束声明、动态启用/禁用，为后续扩展新技能提供标准化框架。

**改动文件：**

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/agents/chat_skills/skill_spec.py` | 新增 | SkillSpec dataclass（name/required_tools/permissions/safety_constraints） |
| `backend/app/agents/chat_skills/registry.py` | 修改 | 支持 spec 注册、enable/disable、spec 查询 |
| `backend/app/routers/chat.py` | 修改 | 新增 `GET /chat/skills` 接口（返回已注册技能列表） |
| `frontend/src/components/chat/ChatCopilotView.vue` | 修改 | 技能发现面板（展示可用技能及触发示例） |

**SkillSpec 结构：**
```python
@dataclass
class SkillSpec:
    name: str                     # skill 唯一标识
    display_name: str             # 用户可见名称
    intent_examples: list[str]    # 触发示例（前端展示）
    required_tools: list[str]     # 必须可用的工具名
    optional_tools: list[str]     # 可选工具名
    permissions: list[str]        # read_only / write_user_data / long_running
    safety_constraints: list[str] # 禁止事项说明
    enabled: bool = True
```

**验收标准：**

| # | 验收项 |
|---|--------|
| C9-1 | `GET /chat/skills` 返回所有已注册技能及触发示例 |
| C9-2 | 前端展示技能发现面板（首次使用引导） |
| C9-3 | 禁用某 Skill → Orchestrator 路由时跳过该 Skill |
| C9-4 | 新增第 7 个 Skill 只需创建文件 + 注册，无需修改 Orchestrator |
| C9-5 | python compileall 0 errors |
| C9-6 | npm run build 通过 |

**Migration：** 无  
**新依赖：** 无

---

## 技术风险汇总

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 意图路由准确率（规则 vs LLM） | 错误调用工具或 Skill | 规则优先 + Skill 兜底；提供"我不理解"fallback |
| AkShare 数据源延迟 | 工具调用超时，对话卡顿 | 每个工具设置 10s 超时；超时返回友好错误 |
| create_analysis_run SSE 路由 | chat session 下的 SSE 事件路由冲突 | 复用 AnalysisRunRegistry 基础设施（M40-b） |
| 多 worker 内存记忆不共享 | C7/C8 单 worker 约束 | MVP 接受，C9 后可用 Redis 持久化（参考 M40-b） |
| Skill 工具链部分失败 | 研究结论不完整 | 降级输出已获取维度，明确标注数据缺失 |
| Memory 污染（外部内容写入记忆） | 安全风险 | 外部内容不写入结构化记忆（C8 强化） |
| DB 连接池压力 | 消息频繁写 chat_messages | 消息写入可改为异步（fire-and-forget），不阻塞响应 |

---

## 阶段总结

| 阶段 | 核心交付 | OpenClaw 层级 |
|------|---------|--------------|
| C2 | Chat UI（6 组件，mock 场景） | Chat Channel |
| C3 | Chat API + DB（session/message 持久化）| Chat Channel |
| C4 | Tool Registry（9 只只读工具）✅ | Tools 工具层 |
| C5 | Action Tools + ConfirmationManager 真实执行 | Action 执行层 |
| C6 | Financial Skills Layer（6 只技能） | Skills 技能层 |
| C7 | Planner + 多步骤任务编排 | Planner 任务规划 |
| C8 | Memory + Audit Hardening | Memory 记忆层 + Audit 审计层 |
| C9 | OpenClaw-style Skill Registry（可扩展框架） | 全层整合 |
| C10 | Agent Evaluation + Capability Manifest（能力验收体系） | 全层验收 |

> 完整架构演进见：[`docs/openclaw_inspired_roadmap.md`](openclaw_inspired_roadmap.md)  
> Skills 完整规范见：[`docs/chat_agent_skills.md`](chat_agent_skills.md)
