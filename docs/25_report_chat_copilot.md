# Phase 6J — 问财报 Chat Copilot

## Overview

Phase 6J adds a **financial report Q&A copilot** to the Company Tab. Users can ask natural-language questions about a specific stock's annual reports, and the system retrieves relevant filing excerpts via RAG, answers using DeepSeek LLM, and enforces full compliance review before returning results.

---

## Architecture

```
User question (POST /api/v1/stock/{code}/report-chat)
        │
        ▼
ReportChatCopilotAgent.chat()
  ├── 1. classify_question() → allowed / rejected (fast, no LLM, no RAG)
  ├── 2. expand_query()      → append domain keywords for better recall
  ├── 3. ReportRagService.query(ts_code, expanded_query, db, ...)
  │        ├── vector search (pgvector cosine similarity)
  │        └── keyword fallback (ILIKE)
  ├── 4. Build LLM prompt (inject chunks as JSON context)
  ├── 5. DeepSeek call (flash model, temperature=0.3)
  ├── 6. FundamentalReviewAgent.review() (Phase 6I reuse)
  │        ├── _canonicalize_source_chunks (chunk_id whitelist)
  │        ├── _check_and_remove_page_citations
  │        ├── _check_and_rewrite_coverage_claims
  │        ├── _check_citation_consistency
  │        └── banned phrase detection (investment advice)
  └── 7. Return structured result
```

---

## API

### `POST /api/v1/stock/{code}/report-chat`

**Path param `code`:** Stock code in any format — `600519`, `600519.SH`, `000001.SZ`, `688981.SH`, `838030.BJ`.
Only CN market is supported; HK/US return HTTP 200 with `partial=True`.

**Request body:**
```json
{
  "question": "公司的现金流质量怎么样？",
  "report_types": ["annual"],
  "years": [2025, 2024],
  "top_k": 6
}
```

| Field | Default | Constraints |
|-------|---------|-------------|
| `question` | required | 1–500 chars |
| `report_types` | null (all) | e.g. `["annual", "semi"]` |
| `years` | null (all) | list of ints |
| `top_k` | 6 | 1–10 (capped at 10) |

**Response (HTTP 200 always):**
```json
{
  "answer": "根据已接入的公开财务数据…",
  "source_chunks": [
    {
      "chunk_id": 42,
      "report_type": "annual",
      "report_year": 2023,
      "period": "2023-12-31",
      "section_title": "管理层讨论与分析",
      "content": "…",
      "score": 0.87,
      "citation": "根据管理层讨论章节…",
      "pdf_url": null
    }
  ],
  "review_audit": {
    "source_chunks_checked": true,
    "invalid_chunk_ids_removed": [],
    "metadata_canonicalized": false,
    "page_citation_removed": false,
    "coverage_claim_rewritten": false,
    "citation_consistency_rewritten": false,
    "investment_advice_blocked": false,
    "mild_phrases_rewritten": []
  },
  "rag_status": "local",
  "confidence": "high",
  "evidence_used": ["管理层讨论章节，现金流量表"],
  "data_limitations": [],
  "disclaimer": "本内容基于已接入的公开财报片段，仅供参考，不构成投资建议。",
  "errors": [],
  "partial": false
}
```

**Response headers:** `X-Data-Disclaimer: For informational purposes only. Not investment advice.`

---

## Question Classification

**Allowed (financial/operational questions):**
- 主营业务是什么？
- 现金流怎么样？
- 盈利能力如何？
- 年报里提到了哪些风险？
- 分红政策是什么？
- 管理层讨论了什么？
- 收入结构如何？

**Rejected immediately (no LLM, no RAG call):**
- Any question containing: `买入, 卖出, 加仓, 减仓, 目标价, 价格目标, 保证收益, 必然上涨, 明天涨, 明天跌, 内幕, 操纵, 庄家`
- Returns `review_audit.investment_advice_blocked = true`

**Rejection message:**
> "非常抱歉，您的问题涉及投资建议、目标价格或其他不适合在本平台回答的内容。本系统仅提供基于公开财报的客观信息查询，不提供买卖建议、目标价或收益承诺。"

---

## RAG Query Expansion

| Question keyword | Appended expansion |
|------------------|--------------------|
| 现金流/cash flow | 经营活动现金流 现金流量 净额 |
| 风险/risk | 风险因素 市场风险 经营风险 |
| 主营/主业/business | 主营业务 产品 收入构成 |
| 分红/dividend | 利润分配 分红 股利 |
| 盈利/profit/利润 | 毛利率 净利率 利润 盈利能力 |

---

## Review Agent Reuse (Phase 6I)

All Phase 6I checks are applied to chat responses:

| Check | Behavior |
|-------|----------|
| chunk_id not in allowed list | Remove chunk |
| LLM modified metadata | Override from rag_context |
| "第N页" in answer | Remove page citation |
| "完整覆盖所有财报" | Rewrite |
| Citation signal without data | Rewrite |
| Investment advice phrases | Reject entire response |

The `review_audit` dict is returned in every response.

---

## Frontend: `ReportChatPanel.vue`

**Location:** Company Tab → below 年报文件 section

**Features:**
- Textarea input with Enter-to-send
- 5 suggestion chips (localized in 6 languages)
- Loading state with spinner
- Answer text display (plain text, no v-html)
- Confidence badge (high/medium/low)
- RAG status badge (local/mock/keyword_only/unavailable)
- "✓ 引用已通过系统校验" teal badge when `review_audit.source_chunks_checked`
- Source chunk list (expand/collapse)
- Citation quote display
- PDF link (rel="noopener noreferrer", target="_blank")
- Investment advice rejection notice (styled red)
- No-index notice (styled blue)
- Disclaimer footer (always shown)
- 6-language i18n (rcp_* keys)

**Security:**
- No `v-html` anywhere
- All content uses `{{ }}` text interpolation
- PDF URLs rendered as `<a>` links with `rel="noopener noreferrer"`
- `local_path` never shown to user

---

## Graceful Degradation Paths

| Scenario | Behavior |
|----------|----------|
| db=None (no DB connection) | RAG skipped, rag_status="unavailable", partial=True |
| No indexed chunks for this stock | Empty source_chunks, data_limitations note |
| Vector provider unavailable | Keyword fallback, rag_status="keyword_only" |
| LLM unavailable | Graceful error message, partial=True |
| HK/US market | HTTP 200 + partial=True + localized error |
| Question >500 chars | Truncated to 500 before processing |
| top_k >10 | Capped to 10 |
| All source_chunks invalid | source_chunks=[], answer degraded |
| Investment advice question | Fast reject (no LLM/RAG), audit flag set |

---

## Security & Compliance

| Property | Implementation |
|----------|---------------|
| No cross-stock data leakage | RAG query always filters by ts_code |
| No investment advice | Keyword rejection + Review Agent banned phrase detection |
| No fabricated page references | _check_and_remove_page_citations |
| No coverage exaggeration | _check_and_rewrite_coverage_claims |
| No invented chunk metadata | _canonicalize_source_chunks (metadata from rag_context, never LLM) |
| No XSS | No v-html in any component |
| No prompt/path leakage | api returns only structured data fields |

---

## Files Changed

### New
- `app/agent/report_chat_copilot_agent.py`
- `app/agent/prompts/report_chat_system.md`
- `app/routers/report_chat.py`
- `frontend/src/components/fundamentals/ReportChatPanel.vue`
- `tests/fundamental/test_phase6j_report_chat_copilot.py`
- `docs/25_report_chat_copilot.md`

### Modified
- `app/main.py` — registers `report_chat_router`
- `frontend/src/components/CompanyFundamentalsPanel.vue` — adds `ReportChatPanel` section
- `frontend/src/locales/zh-CN.js`, `en-US.js`, `zh-TW.js`, `ja-JP.js`, `ko-KR.js`, `es-ES.js` — 33 `rcp_*` keys each

---

## Tests

22 tests in `tests/fundamental/test_phase6j_report_chat_copilot.py` — 22/22 PASS.

Full suite: 469/469 PASS.

---

## Known Limitations

- Chat is stateless (no conversation history per session)
- Only CN market supported
- Answers depend entirely on indexed report chunks; stocks without indexed PDFs return degraded responses
- DeepSeek flash model used (not pro) to reduce latency; may be less thorough on complex multi-fact questions
- No answer caching in Phase 6J (planned for Phase 6K)
