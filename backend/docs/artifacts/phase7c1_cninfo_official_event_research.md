# Phase 7C1 — CNINFO Official Event Research for AI Chat

## 1. 交付结论

状态：`CNINFO_OFFICIAL_EVENT_RESEARCH_CANDIDATE_READY`

本阶段新增一个确定性、只读、fail-closed 的官方事件研究路径。该路径只读取已持久化且 `source=cninfo` 的官方报告/公告元数据，不执行发现、下载、刷新或外部 Provider 请求；缺少完整官方证据时返回真实 `partial` 或 `unavailable`。

## 2. 实现范围

### 2.1 官方事件投影服务

新增 `backend/app/services/official_company_event_service.py`：

- 仅按已解析的 CN 股票代码读取持久化 CNINFO 记录。
- 只展示同时具备标题、披露日期和 CNINFO 白名单 URL 的记录。
- 每项公开事件输出：`title`、`published_at`、`source=CNINFO`、`source_url`、`event_type`、`symbol`、`company_name`、`as_of`、`coverage`、`quality`。
- 不返回数据库 ID、内部解析状态、本地路径或内部表名。
- `as_of` 使用已持久化记录的最新摄取时间；无法取得时保持 `null/unavailable`。
- 不调用 CNINFO live query；不调用任何新闻/行情 Provider。

事件分类采用确定性标题规则，支持：

1. 财报/业绩
2. 分红
3. 回购
4. 股东增减持
5. 并购重组
6. 治理与管理层
7. 业务进展
8. 监管/诉讼/风险
9. 其它官方披露

### 2.2 Agent 路由

在 Chat Orchestrator 的安全检查之后、memory/entity/skill/tool 调用之前增加来源治理门：

- 明确包含公告、官方披露、分红、回购、增减持等词 → `official_company_events`。
- 明确询问财报/年报/季报“披露/重点/官方” → `official_report_analysis`。
- 普通财报分析问题仍进入既有 ReportExplanationSkill / Report RAG 路径，避免破坏既有 citation 与 numeric validation。
- 行业新闻、市场热点新闻、主题产业链/供应链/直接受益问题 → `unavailable` + `NO_APPROVED_INDUSTRY_NEWS_SOURCE`。

来源治理门在任何新闻工具之前返回，因此上述拒绝路径不会触发 AKShare、东方财富、新浪或腾讯，也不会要求用户提供一只股票。

### 2.3 回答结构

官方事件回答固定按以下顺序生成，不调用 LLM 补全事实：

1. 结论摘要
2. 近期官方事件
3. 事件可能影响与已知事实
4. 数据范围与局限
5. 来源

每项事件逐项展示公告标题、发布日期、事件类型和官方来源链接。影响部分仅确认“官方已披露”这一事实，不从公告标题推断确定性市场影响，并统一附带“不构成投资建议”。

## 3. 履约状态规则

| 条件 | fulfillment | reason_code | 行为 |
|---|---|---|---|
| 有完整可见 CNINFO 记录，无不完整记录 | `fulfilled` | `null` | 展示官方事件 |
| 有完整记录，但持久化覆盖中存在缺日期/URL/标题记录 | `partial` | `INCOMPLETE_PERSISTED_CNINFO_COVERAGE` | 只展示完整记录并说明覆盖局限 |
| 没有完整记录 | `unavailable` | `NO_PERSISTED_CNINFO_EVENTS` | 不展示、不编造 |
| 公司无法解析 | `unavailable` | `COMPANY_NOT_RESOLVED` / `AMBIGUOUS_COMPANY` | 不猜测公司 |
| 行业/市场/主题新闻 | `unavailable` | `NO_APPROVED_INDUSTRY_NEWS_SOURCE` | 不触发工具或 Provider |

## 4. Report RAG 边界

`official_report_analysis` 的确定性路径负责公开展示官方报告事件元数据。若用户要求正文重点，本路径明确说明：只有既有 Report RAG 具备可引用证据时，才由原有报告分析链路提供正文分析；不得用标题代替正文结论。

本阶段没有修改：

- Report RAG 检索、答案生成或索引；
- citation claim boundary；
- numeric pipeline / numeric validation；
- LLM Prompt；
- Tushare Gateway 或 Provider 权限；
- Docker、依赖、migration、前端。

## 5. 验收结果

### 5.1 Phase 7C1 专项测试

命令：

```text
backend/.venv/bin/pytest -q backend/tests/test_phase7c1_cninfo_official_event_research.py
```

结果：`17 passed`。

覆盖：

- 有完整 CNINFO 事件 → `fulfilled`；
- 显式财报披露问题 → `official_report_analysis` + 真实 `partial`；
- 无记录 → `unavailable`，无编造；
- 三类未批准新闻问题 → `NO_APPROVED_INDUSTRY_NEWS_SOURCE`；
- 未批准问题在实体/Provider 路径之前结束；
- 不完整记录过滤、数据库 ID 隐藏；
- 九类事件分类。
- 指定事件类型没有匹配时，不使用无关官方报告替代。

### 5.2 Report RAG、citation、numeric 回归

执行：

```text
backend/.venv/bin/pytest -q \
  backend/tests/fundamental/test_phase6td_report_rag_answer.py \
  backend/tests/fundamental/test_phase6td_report_rag_retriever.py \
  backend/tests/test_phase6w_r3_3i2_3_citation_claim_boundary.py \
  backend/tests/test_phase6w_r1_2_numeric_pipeline.py \
  backend/tests/test_phase6w_r1_p0c_report_query_routing.py
```

结果：`50 passed`，仅有既有 `datetime.utcnow()` deprecation warnings。

### 5.3 既有 Chat/Report 路由回归

执行：

```text
backend/.venv/bin/pytest -q \
  backend/tests/test_c4_orchestrator.py \
  backend/tests/test_c7_orchestrator_integration.py \
  backend/tests/test_c2510_report_ux.py \
  backend/tests/test_c259_report_detail_fix.py
```

结果：`46 passed`，仅有既有 AsyncMock/runtime warnings。

总计：`113 passed`（原 112 项相关回归全部通过，新增 1 项事件类型真实性测试）。

## 6. 已知覆盖限制

- 当前持久化模型主要覆盖官方定期报告；如果历史上未将分红、回购、股东变动等普通公告持久化，本路径会如实返回 `unavailable`，不会 live 抓取补齐。
- 本阶段没有 migration，因此不新增公告专用字段或表。
- 本阶段没有修改 LLM Prompt。正文“重点”仍依赖既有 Report RAG 的索引和证据可用性；事件元数据路径不会从标题生成正文结论。
- 本地仓库数据库文件为空，本轮使用隔离测试数据验证运行契约，没有访问外部或生产数据库。

## 7. 变更文件

- `backend/app/services/official_company_event_service.py`
- `backend/app/agents/chat_orchestrator.py`
- `backend/tests/test_phase7c1_cninfo_official_event_research.py`
- `backend/docs/artifacts/phase7c1_cninfo_official_event_research.md`
- `backend/docs/artifacts/phase7c1_cninfo_event_runtime_trace.json`
- `HKNA/update_report/update_128.md`
