# Chat Agent Capability Manifest

**Version:** c10_v1  
**Date:** 2026-06-18  
**Phase:** C10 — Agent Evaluation + Capability Manifest  
**Status:** Production-Ready (RC)

---

## 1. Overview

The TradingAgents Chat Copilot is a multi-layer financial research assistant built on a rule-based orchestration pipeline. It combines read-only data tools, skill-based analysis, a controlled planner for compound tasks, action tools with confirmation guards, session memory, and a safety firewall.

The system is intentionally **non-LLM-in-the-loop** for intent classification — all routing decisions are deterministic regex-based rules, making behavior auditable and reproducible without API cost.

---

## 2. Architecture Summary

```
User Message
    │
    ▼
[TradingForbiddenWordsGuard]   ─── blocks 买入/卖出/持有/目标价
    │
    ▼
[RuleBasedPlanner]             ─── detects compound multi-step tasks
    │ compound?
    ├─YES─► [PlannerExecutor]  ─── executes ordered PlanSteps sequentially
    │                                each step routes to tool/skill dispatch
    │ NO
    ▼
[SkillRegistry.select_skill]   ─── matches domain Skills (priority routing)
    │ skill matched?
    ├─YES─► [Skill.run()]      ─── multi-tool financial analysis narrative
    │
    │ NO
    ▼
[Intent Matchers]              ─── regex-based tool routing
    │
    ▼
[ToolRegistry.call()]          ─── executes registered read-only tools
    │
    ▼
[Action Tool Flow]             ─── write operations require confirmation
    │
    ▼
[_write_memory_from_result]    ─── fire-and-forget session memory update
    │
    ▼
OrchestratorResult + _DISCLAIMER
```

---

## 3. Tools Layer (C4)

**Registry:** `ToolRegistry` — 9 registered tools  
**Location:** `backend/app/agents/chat_tools/`

| Tool Name | Description | Market Support |
|-----------|-------------|----------------|
| `resolve_stock_tool` | Resolve ticker to market/symbol | CN, HK, US |
| `get_quote_tool` | Real-time quote (price, change, volume) | CN, HK, US |
| `get_kline_summary_tool` | K-line summary (1M/3M/6M range stats) | CN, HK, US |
| `get_latest_news_tool` | Recent news headlines (up to 10) | CN |
| `get_recent_reports_tool` | User's recent analysis reports | All |
| `get_report_detail_tool` | Full report content by ID | All |
| `get_watchlist_tool` | User's watchlist items | All |
| `get_industry_hot_tool` | Industry heat scores + change stats | CN |
| `get_industry_stocks_tool` | Hot stocks by industry | CN |

**Audit fields (C8):** Every `ToolResult` carries `duration_ms`, `started_at`, `permission_level`.

---

## 4. Action Tools Layer (C5)

**Location:** `backend/app/agents/chat_tools/action_tools.py`  
**Confirmation:** `ConfirmationManager` tracks lifecycle (pending → confirmed/cancelled)

| Action | Trigger Pattern | Guard |
|--------|----------------|-------|
| `add_to_watchlist` | "加入自选 {symbol}" | SavePoint race guard |
| `create_analysis_run` | "生成报告 {symbol}" | Duplicate check |
| `create_compare_selection` | "对比 {A} 和 {B}" | 2–5 symbols enforced |

All write operations require explicit user confirmation via `/chat/{session}/confirm`.

---

## 5. Skills Layer (C6, C9)

**Registry:** `SkillRegistry` — 6 registered skills  
**Location:** `backend/app/agents/chat_skills/`  
**Specs:** `backend/app/agents/chat_skills/specs/*.json` (c9_v1)

| Skill | Trigger | Required Tools | Permission |
|-------|---------|----------------|------------|
| `stock_anomaly` | 为什么涨/跌/异动 + 股票信号 | resolve, quote, kline, news | read_only |
| `risk_first` | 风险 + 股票信号 | resolve, kline, news | read_only |
| `news_catalyst` | 新闻/消息 + 股票信号 | resolve, news, quote | read_only |
| `watchlist_review` | 自选股 + 巡检/研究 | watchlist, quote | read_only |
| `industry_hotspot` | 行业 + 热点/板块 | industry_hot | read_only |
| `report_explanation` | 报告 + 解释/结论 | recent_reports | read_only |

**Skill availability gate (C9):** Skills disabled in spec JSON or whose required tools are missing from ToolRegistry are automatically excluded from selection. Runtime toggle via `SkillRegistry.set_skill_enabled()`.

---

## 6. Planner Layer (C7)

**Components:** `RuleBasedPlanner` + `PlannerExecutor`  
**Location:** `backend/app/agents/chat_planner/`

| Compound Intent | Example | Steps |
|----------------|---------|-------|
| `anomaly_then_risk` | "为什么涨…重点看风险" | anomaly_skill → risk_skill |
| `report_then_risk` | "解释报告并告诉我最大风险" | report_skill → risk_skill |
| `watchlist_scan` | "自选股里有没有波动大的" | watchlist_view → kline_summary |
| `industry_then_stocks` | "哪些行业热？每个挑几个" | industry_hot → stock_lookup |
| `research_then_action` | "分析688146，如果可以加自选" | anomaly_skill → add_watchlist |
| `compare_then_report` | "比较A和B，然后生成报告" | compare → report_gen |

**Safety:** MAX_STEPS = 5. Disabled/unavailable skills return `status="failed"` without crash.

---

## 7. Memory Layer (C8)

**Location:** `backend/app/agents/chat_memory.py`  
**Storage:** `session_metadata["memory_v1"]` JSONB (no new migration)

| Memory Type | Capacity | TTL |
|-------------|----------|-----|
| `recent_symbols` | 10 items (FIFO evict) | Session |
| `recent_queries` | 20 items (FIFO evict) | Session |
| `flagged_topics` | Unlimited | Session |
| `session_start` | Timestamp | Session |

**Fire-and-forget writes:** `session_id=None` → immediate return. All writes wrapped in try/except to prevent memory errors from blocking response delivery.

---

## 8. Audit Layer (C8)

Every tool call injects:
- `duration_ms` — integer, call latency
- `started_at` — ISO 8601 UTC timestamp
- `permission_level` — "read_only" | "research_action" | "write_action"

`OrchestratorResult.metadata` carries aggregated audit data including `tools_used`, `safety_flags`, `skill_spec_version`.

---

## 9. Safety Layer

**Financial trading guard:**
- Pattern: `买入|卖出|持有|建仓|减仓|清仓|目标价|止损|止盈`
- Trigger: Returns `OrchestratorResult` with `safety=True` flag, refuses request
- Coverage: Checked before any tool routing in `process_message()`

**Skill-level safety rules (per spec):**
- `no_trading_advice` — Skills must not recommend buy/sell
- `must_include_disclaimer` — All answers append `_DISCLAIMER`

**Injection guard (C8 `chat_safety.py`):**
- Detects prompt injection patterns in tool outputs
- Tags external data with `[EXTERNAL DATA]` marker
- Forbidden phrases blocked at `sanitize_output()` level

**Disclaimer:** All `OrchestratorResult.answer` values end with `_仅供研究参考，不构成投资建议。_`

---

## 10. API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/chat/sessions` | ✓ | Create chat session |
| GET | `/chat/sessions` | ✓ | List user sessions |
| POST | `/chat/{session_id}/messages` | ✓ | Send message |
| POST | `/chat/{session_id}/confirm` | ✓ | Confirm pending action |
| GET | `/chat/skills` | ✓ | List available skills (C9) |
| GET | `/chat/{session_id}/memory` | ✓ | Get session memory (C8) |
| DELETE | `/chat/{session_id}/memory` | ✓ | Clear session memory (C8) |

---

## 11. Known Limitations

1. **Intent classification is rule-based** — Novel phrasings not matching existing regex patterns fall through to `_handle_default()`.
2. **No LLM synthesis** — Answers are template-assembled from tool data, not LLM-generated prose.
3. **CN market focus** — News, industry, and kline tools optimized for A-shares; HK/US have reduced coverage.
4. **Memory is session-scoped** — No cross-session memory persistence.
5. **Planner MAX_STEPS = 5** — Plans longer than 5 steps are truncated.
6. **No streaming** — Chat messages return synchronously (SSE is analysis-only).
7. **Skill availability requires ToolRegistry** — Skills checked against registered tools at startup; dynamic tool addition not supported at runtime.

---

## 12. Capability Counts

| Layer | Count |
|-------|-------|
| Read-only tools | 9 |
| Action tools | 3 |
| Skills | 6 |
| Compound planner intents | 6 |
| Safety patterns | 9 (trading) + injection guard |
| API endpoints | 7 |
| Locales supported | 6 (zh-CN, zh-TW, en-US, ja-JP, ko-KR, es-ES) |
| Test coverage (C4–C10) | 317+ passing |

---

## 13. Phase History

| Phase | Description |
|-------|-------------|
| C1 | PRD + Architecture Design |
| C2 | Frontend Chat MVP (mock) |
| C3 | Chat API MVP + DB migrations |
| C4 | Tool Registry — 9 read-only tools |
| C5 | Action Tools + ConfirmationManager |
| C6 | Financial Skills Layer (6 skills) |
| C7 | Controlled Planner (6 compound intents) |
| C8 | Memory + Audit Hardening |
| C9 | OpenClaw-style Skill Registry (SkillSpec JSON) |
| C10 | Agent Evaluation + Capability Manifest |
