# TradingAgents — OpenClaw-inspired 金融智能 Agents 后续优化计划

> 版本：Phase C12 完成  
> 日期：2026-06-21  
> 面向读者：导师 / 技术评审  
> 定位：技术架构说明 + 后续阶段规划  
> C9 状态：✅ OpenClaw-style Skill Registry — 6 SkillSpec JSON files, spec_loader, GET /chat/skills API, enabled/available gate  
> C10 状态：✅ Agent Evaluation + Capability Manifest — 30 golden tasks (30/30 PASS), evaluate_chat_agent.py  
> C11-a 状态：✅ Advisor Demo Package — advisor_demo_package.md, advisor_qa.md, README Mermaid, demo Route A-D  
> C11-b 状态：✅ RAG + Review Agents + Internal Agent Workflow + Chat UX — 447/447 tests PASS, build ✓  
> C11-c 状态：✅ E2E Acceptance + UX Hardening — scope key 修复 / ChatReasoningSteps / 硬超时 error card — 489/489 PASS  
> C12 状态：✅ UX Refactor + Real-time Agent Thinking — 即时研究步骤 / 2列布局 / 5快捷问句+换一换 / 59 tests — 548/548 PASS  
> C13-a 状态：✅ Chat Agent SSE Streaming — /messages/stream / fetch+ReadableStream / event_callback / fallback / 56 tests — 604/604 PASS  
> C13-b 状态：✅ Real-time Tool/RAG/Skill Event Streaming — safe_emit + ToolRegistry + RAG + 6 Skills + PlannerExecutor + Phase 5 dedup / 44 tests — 754/754 PASS

---

## 1. 当前系统基础

TradingAgents 目前已完成以下核心能力：

### 研究工作台（M1–M51）

| 功能 | 技术实现 | 状态 |
|------|---------|------|
| A股/港股股票研究页 | FastAPI + Vue 3 + Supabase PostgreSQL | ✅ |
| 多 Agent 分析报告 | LangGraph 并行 Fan-out + LLM Synthesis | ✅ |
| 4 维分析面（技术/基本面/同行/新闻） | 各自独立 Agent，LangGraph 协调 | ✅ |
| 报告结论先行结构 | Prompt 工程优化 + extractSummary | ✅ |
| 行业热度（申万L1 5166只股票） | AkShare + 离线热度评分 | ✅ |
| 自选股/报告/对比/历史 | CRUD + 用户隔离 | ✅ |
| 6 语言 UI + 6 语言报告 | 自定义 i18n + output_language Agent透传 | ✅ |
| Redis Run Registry + SSE 实时流 | LangGraph 灰度 + 断线重连 | ✅ |

### Chat Copilot（C1–C4）

| 能力 | 技术实现 | 状态 |
|------|---------|------|
| Chat 前端 UI | Vue 3 + ChatCopilotView | ✅ |
| Session/Message 持久化 | chat_sessions + chat_messages DB 表 | ✅ |
| Tool Registry（9 只只读工具） | BaseTool ABC + ToolRegistry + ToolResult | ✅ |
| 股票识别/行情/K线/新闻工具 | 复用 stock_data_service / news_data_service | ✅ |
| 行业热度/自选股/报告只读工具 | 复用现有 Service + DB 直查 | ✅ |
| 规则意图路由 | 正则匹配，9 类意图 | ✅ |
| Mock 写操作确认流程 | Confirmation dict + 前端确认卡片 | ✅ mock |

---

## 2. 为什么适合基于 OpenClaw 思想继续开发

OpenClaw 类 Agentic AI 系统的核心架构思想是：**将 AI 能力组织为可调用的工具（Tools）、可复用的技能（Skills）、有状态的记忆（Memory）、可规划的任务（Planner）和可审计的动作（Action + Audit）**。

TradingAgents 目前的基础与这一架构高度契合：

1. **工具层已就绪**：现有 9 个只读工具已遵循 `BaseTool → ToolRegistry → ToolResult` 架构，可以直接扩展。

2. **数据层完整**：行情、K线、新闻、行业、报告、自选股数据服务均为异步 Service，已经是工具友好的接口形式。

3. **多 Agent 报告引擎**：现有 LangGraph 分析引擎本身就是 Agent 系统，可作为 Chat Copilot 的长任务 Skill。

4. **确认机制雏形**：Mock confirmation 流程已定义了写操作确认的前后端交互模式，C5 只需接入真实执行。

5. **金融合规边界清晰**：禁止投资建议、外部内容不可信、用户数据隔离等原则已在工具层实施，可扩展到 Skills 和 Planner。

---

## 3. TradingAgents 与 OpenClaw 架构映射

| OpenClaw 架构组件 | TradingAgents 对应设计 | 当前状态 |
|---|---|---|
| **Chat Channel** | `/chat` ChatCopilotView — 自然语言入口 | ✅ C2 完成 |
| **Tool Registry** | `chat_tools/` — 9 只只读金融工具 | ✅ C4 完成 |
| **Skills** | `chat_skills/` — 6 类金融研究技能（见第 4 节） | ✅ C6 完成 |
| **Memory** | 短期记忆（session）+ 结构化记忆（DB）+ 任务状态 | C8 实现 |
| **Planner** | 多步骤研究任务拆解（RuleBasedPlanner + PlannerExecutor，6 复合任务类型） | ✅ C7 完成 |
| **Action** | 确认后真实执行（加自选/生成报告/创建对比） | C5 实现 |
| **Permissions** | `read_only` / `write_user_data` / `long_running` / `sensitive` | ✅ C4 定义 |
| **Confirmation** | 写操作和长耗时任务必须用户确认 | C5 持久化 |
| **Audit Trail** | tool_events + chat_messages metadata + 来源说明 | ✅ 部分实现 |
| **Safety Guardrails** | 金融合规 + 禁用投资建议 + Prompt Injection 防护 | ✅ 基础实现 |

### 特殊说明：网站工作台的角色

现有的股票研究工作台（8 个页面）**不会被 Chat 替代**，而是成为 Agent 的两个基础层：

1. **工具基座**：行情页、报告页、行业页、自选股页提供 Agent 工具的数据来源和执行端点。
2. **结果落地层**：Agent 执行结果（报告、自选股、对比组合）最终沉淀到对应页面，用户可在页面中深度查看。

```
[自然语言输入] → Chat Copilot Agent → [调用工具/技能] → [工作台页面作为结果展示]
      ↑                                                          ↓
   用户对话                                              报告/自选/行业/对比
```

---

## 4. 第一批金融 Skills（C6 实现）

Skills 层是系统智能化的核心：将常见投研模式沉淀为可复用技能，而非每次重新 Prompt。

| Skill | 解决的研究任务 | 核心工具链 |
|-------|-------------|-----------|
| **Stock Anomaly Skill** | 为什么这只股票涨这么多/异动原因 | resolve → quote → kline → news |
| **Risk-first Research Skill** | 帮我重点看风险/最大风险是什么 | resolve → kline → report → news |
| **News Catalyst Skill** | 最近新闻有什么实质影响/订单兑现了吗 | resolve → news → quote（印证） |
| **Watchlist Review Skill** | 帮我巡检自选股/哪些值得关注 | watchlist → quote → kline（异动股）|
| **Industry Hotspot Skill** | 今天哪些行业值得研究/热门股是哪些 | industry_hot → industry_stocks |
| **Report Explanation Skill** | 解释最近报告/最重要的风险是什么 | recent_reports → report_detail → quote |

> 完整 Skills 规范见 [`docs/chat_agent_skills.md`](chat_agent_skills.md)

---

## 5. 后续三阶段规划

### Phase C5 — Action Tools + ConfirmationManager 真实执行

**目标：** 将 mock confirmation 升级为真实写操作执行。

| 实现项目 | 说明 |
|---------|------|
| `add_to_watchlist_tool` | 确认后调用现有 `POST /watchlist` 接口 |
| `create_analysis_run_tool` | 确认后调用 `POST /analysis/runs` + SSE 进度推流 |
| `create_compare_selection_tool` | 确认后生成 `/compare?stocks=` 跳转链接 |
| ConfirmationManager 持久化 | pending_action 写入 chat_messages.confirmation（已有字段）|
| Action Audit | 每次执行写入 tool_events + 时间戳 |

**技术要点：**
- 写操作工具不封装为 Skill（保持无副作用原则），由 Orchestrator 直接以 Action 形式调用
- confirmation 超时（5分钟）自动取消
- 为 C6 Skills 预留接口：Orchestrator → SkillRegistry.run() 替代当前 handler 函数

**新增依赖：** 无  
**新增 Migration：** 无（复用 C3 confirmation 字段）

---

### Phase C6 — Financial Skills Layer ✅ 完成（2026-06-18）

**目标：** 将多个工具调用组织为结构化、可复用的金融研究技能。

| 实现项目 | 说明 | 状态 |
|---------|------|------|
| `BaseSkill` ABC + `SkillResult` | `base.py` 定义，含 SkillContext 注入 | ✅ |
| `SkillRegistry` | `registry.py`，priority 排序，`run()` 异常兜底 | ✅ |
| 6 个 Financial Skills | 详见 chat_agent_skills.md 第 6 节 | ✅ |
| Orchestrator 4 层分发 | Safety → Action → SkillRegistry → C4 fallback | ✅ |
| metadata 审计记录 | skill_name/source/tools_used/safety_flags 写入 msg_metadata | ✅ |
| 前端输出兼容 | SkillResult → OrchestratorResult，cards/tool_events 格式不变 | ✅ |

**已实现 Skills 清单：**
- `ReportExplanationSkill`（priority=10）：解释最近报告结论/风险
- `WatchlistReviewSkill`（priority=20）：巡检自选股，最多 5 只轻量摘要
- `IndustryHotspotSkill`（priority=30）：行业热度排行 + 研究线索
- `RiskFirstSkill`（priority=35）：风险优先研究，区分技术/新闻/数据缺口风险
- `StockAnomalySkill`（priority=40）：异动分析，4 工具链（resolve/quote/kline/news）
- `NewsCatalystSkill`（priority=45）：新闻催化分析，区分已发生事实/市场预期/未兑现风险

**测试：** 72/72 PASS（C4: 11 + C5: 22 + C6: 34/34）

**新增文件：**
```
backend/app/agents/chat_skills/
├── __init__.py
├── base.py
├── registry.py
├── stock_anomaly_skill.py
├── risk_first_skill.py
├── news_catalyst_skill.py
├── watchlist_review_skill.py
├── industry_hotspot_skill.py
└── report_explanation_skill.py
```

---

### Phase C7 — Controlled Planner ✅ 完成（2026-06-18）

**目标：** 支持多步骤研究任务拆解，遇到写操作自动挂起等待确认。纯规则实现，无 LLM，响应快、行为可预期。

| 实现项目 | 说明 | 状态 |
|---------|------|------|
| `chat_planner/base.py` | PlanStep / PlannerResult / ExecutionResult dataclasses | ✅ |
| `RuleBasedPlanner` | 正则规则检测复合意图，6 种 intent_type | ✅ |
| `PlannerExecutor` | 顺序执行 Steps，action step 只创建 confirmation | ✅ |
| Orchestrator 6 层分发 | Safety → Action → **Planner** → SkillRegistry → C4 → Default | ✅ |
| 复合任务类型 | 6 种：anomaly_then_risk / report_then_risk / watchlist_scan / industry_then_stocks / research_then_action / compare_then_report | ✅ |
| 安全合规 | 禁止词语剥离，_DISCLAIMER 强制附加，MAX_STEPS=5 | ✅ |

**Planner 执行流：**

```
用户输入 → RuleBasedPlanner.is_compound() 检测
        → plan() → PlannerResult（intent_type + steps[]）
        → PlannerExecutor.execute()
            skill step   → SkillRegistry.select_by_name() → skill.run()
            action step  → make_confirmation() ONLY（不执行写操作）
            final_summary → _synthesize() 聚合多步结果
        → ExecutionResult（answer + confirmation + metadata）
```

**测试：** 137/137 PASS（+65 C7 tests）

**新增文件：**
```
backend/app/agents/chat_planner/
├── __init__.py
├── base.py
├── rule_based_planner.py
└── executor.py
backend/tests/
├── test_c7_rule_based_planner.py  (39 tests)
├── test_c7_planner_executor.py    (14 tests)
└── test_c7_orchestrator_integration.py  (12 tests)
```

---

### Phase C8 — Memory / Audit Hardening（规划中）

| 实现项目 | 说明 |
|---------|------|
| 短期记忆 | 最近 N 轮消息，session 内有效 |
| 结构化记忆 | 最近搜索股票/自选股快照/语言偏好，DB 持久化 |
| 任务状态记忆 | 当前 Planner 执行进度，session 内 |
| Audit Trail DB 化 | tool_events 入库，可按 session 查询 |
| Prompt Injection 防护 | 新闻/报告内容截断 + 类型标注（外部数据） |
| Memory 污染防护 | 外部内容不写入结构化记忆 |
| 用户清空记忆 | DELETE /chat/sessions/{id} + memory flush |

---

## 6. 金融合规边界（不变原则）

以下规则贯穿所有后续阶段，不因功能增强而削弱：

| 规则 | 执行位置 |
|------|---------|
| 禁止输出买入/卖出/持有/目标价 | Orchestrator answer 生成 + Skills 输出 |
| 写操作必须用户确认 | ConfirmationManager（C5 实现） |
| 外部数据（新闻/公告）不作系统指令 | Tool 层截断 + 类型标注 |
| 用户数据严格隔离 | DB where user_id，JWT 不可伪造 |
| 不接入交易系统 | 系统无 broker API，无资金相关接口 |
| 每个 answer 必须含免责声明 | `_DISCLAIMER` 常量，所有 Skill/Orchestrator 输出 |
| 不伪造数据 | 数据缺失时明确标注，不生成虚假指标 |

---

## 7. 最终目标

将 TradingAgents 建设为一个面向 **A 股 / 港股研究场景** 的 **OpenClaw-inspired 金融智能 Agents 系统**：

- **对个人投资者**：提供自然语言驱动的股票研究工具，无需记忆功能入口，直接说出研究目标。
- **对金融学生**：提供可解释的研究过程（tool_events 可查、结论有依据、区分事实与预期）。
- **对初级投研人员**：提高研究效率，自动完成信息聚合、异动归因、风险梳理、报告生成等任务。
- **对技术评审**：展示完整的 Agentic AI 工程实践：工具注册、技能沉淀、任务规划、确认执行、审计追踪。

**系统不做的事情（永久边界）：**
- 不提供买入/卖出/持有建议
- 不预测股价或目标价
- 不接入交易系统
- 不替代专业投资顾问
- 不对投资结果负责

---

*文档更新频率：每个 C 阶段完成后同步更新。*  
*技术实现进度见：[`docs/chat_agent_build_plan.md`](chat_agent_build_plan.md)*  
*Skills 完整规范见：[`docs/chat_agent_skills.md`](chat_agent_skills.md)*
