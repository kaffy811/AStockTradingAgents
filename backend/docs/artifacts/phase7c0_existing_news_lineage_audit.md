# Phase 7C0 — Existing News Provider Lineage Audit

## 1. 审计结论

审计日期：2026-09-01（America/New_York）。本轮仅静态读取仓库代码、已安装依赖源码、本地脱敏配置定义、持久化模型与本地文件；未启动服务，未执行 Provider 请求，未读取 Token/Cookie/数据库连接串或用户数据。

最终治理结论：`EXISTING_NEWS_SOURCE_APPROVAL_REQUIRED`。

- 项目现有“股票新闻”的真实链路是 `AkShare stock_news_em` → 东方财富网页搜索 JSONP 接口，真实上游 host 为 `search-api-web.eastmoney.com`，原文链接由适配器拼为 `finance.eastmoney.com`。这是公开网页搜索/抓取封装，不是仓库内可证明的官方或授权新闻 API，应定级 `research_only`。
- 个股新闻、行业新闻、主题新闻、市场关键词新闻虽然有不同工具名，但都复用同一个关键词搜索接口；行业/主题工具不是独立行业新闻源，也没有行业分类、供应链或受益关系证据。
- 新闻结果只有短 TTL Redis/进程内缓存，不是可审计的持久化系统快照；cache miss 会调用 live Provider。新闻记录没有唯一标识、`as_of`、来源条款状态，且部分链路不保留 URL。
- CNINFO 公告/定期报告链路指向官方域名、保留公告标识/披露日期/来源 URL，并可写入 `report_documents`，按任务规则定级 `approved`。它是官方公告/报告源，不是通用新闻源。
- Tushare 的 `forecast`/`express` 是已封装的付费/权限型供应商数据，合同状态在仓库中不可证，定级 `owner_review_required`；Tushare `news` 没有实现链路，按本轮既定状态保持 `permission_denied`，定级 `disabled`，不购买、不接入。
- Finnhub 未发现实际新闻调用链；Sina/Tencent 只发现行情/基本面适配器，没有新闻调用链，均不可冒充新闻来源。

## 2. 检索范围与证据方法

已检索：`news`、`stock_news`、`company_news`、`industry_news`、`market_news`、`announcement`、`hot_stock`、`eastmoney`、`akshare`、`sina`、`tencent`、`cninfo`、`finnhub`、`tushare`。检索覆盖 `backend/app`、`backend/tests`、`backend/scripts`、`backend/docs`、`backend/data`、`backend/artifacts`、`frontend/src`、`docs`、`HKNA`，并排除依赖缓存、字节码和前端 `node_modules`。

本地 `backend/data/tradingagents.db` 为 0 字节空文件，因此不存在可由该文件证明的新闻或公告数据行。代码定义了 PostgreSQL 持久化表，但本轮没有连接外部数据库。

## 3. 实际调用链

### 3.1 个股新闻 REST API

| 字段 | 证据结论 |
|---|---|
| 用户入口/API endpoint | `GET /api/v1/stocks/{market}/{symbol}/news`，Bearer 鉴权 |
| route/controller | `get_stock_news` |
| service | `NewsDataService.get_stock_news` |
| provider adapter | `EastmoneyNewsProvider.get_stock_news` → `ak.stock_news_em` |
| 真实上游 host/provider | 东方财富网页搜索 `search-api-web.eastmoney.com`；文章 URL 为 `finance.eastmoney.com` |
| 是否需要 symbol | 是；CN 六位代码，HK 补零到五位后作为关键词 |
| 是否支持行业/主题 | 不支持。这里只是 symbol 关键词搜索；HK 还明确可能弱相关 |
| 是否有持久化 snapshot | 否。Redis TTL 600 秒 + 进程内 TTL/stale；cache miss 触发 live Provider |
| 字段 | title、summary、source、url、publish_time、type、symbols；无唯一 ID、as_of、terms_status |
| 异常与 fallback | Provider 异常时先返回进程内 stale；无 stale 返回 HTTP 200 空列表。无其他批准 Provider fallback |
| 来源等级 | `research_only`；不得作为最终用户新闻事实 |
| 文件:行号 | `backend/app/routers/stocks.py:410-452`; `backend/app/services/news_data_service.py:166-260`; `backend/app/data/providers/news_provider.py:90-153`; `backend/.venv/lib/python3.12/site-packages/akshare/news/news_stock.py:15-118` |

注意：路由文档称“最近 10 条”，已安装 AKShare docstring 称“最近 100 条”，但实际请求 `pageSize=10`，所以运行行为是最多 10 条。依赖实现还包含静态网页请求头状态，本文不披露其值；这进一步说明它是网页适配而非稳定授权 API。

### 3.2 新闻分析 API 与股票 News Agent

| 字段 | 证据结论 |
|---|---|
| 用户入口/API endpoint | `POST /api/v1/analysis/news`；Chat `POST /api/v1/chat/sessions/{session_id}/messages` |
| route/controller | `news_analysis` / `send_chat_message` → orchestrator |
| service/agent | `NewsAnalystAgent`；`GetLatestNewsTool`；`NewsAgent` |
| provider adapter/上游 | 完全复用 3.1 的 `NewsDataService` → AKShare → 东方财富 |
| 是否需要 symbol | 是；缺失时 NewsAgent 失败并要求 symbol/market |
| 是否支持行业/主题 | 否；不得把此链路用于行业新闻 |
| 是否有持久化 snapshot | 新闻本身无持久化；Chat 消息/工具轨迹持久化不等于来源快照 |
| 字段 | Tool 保留 title、summary、source、publish_time、url；NewsAgent 添加 `verified=false`，但错误地预设 `source_level=authoritative_media`，不能视为来源批准证据 |
| 异常与 fallback | 服务异常变为空快照/partial；LLM 未配置为 503；没有批准新闻源 fallback |
| 来源等级 | `research_only`，当前 Agent 生产事实输出必须禁用 |
| 文件:行号 | `backend/app/routers/analysis.py:909-949`; `backend/app/agents/news_analyst.py:43-94,122-201,244-284`; `backend/app/agents/chat_tools/stock_tools.py:213-255`; `backend/app/agents/orchestrator/news_agent.py:45-127`; `backend/app/routers/chat.py:159-213` |

### 3.3 行业新闻关键词工具

| 字段 | 证据结论 |
|---|---|
| 用户入口/API endpoint | Chat 消息；无独立 REST 新闻 endpoint |
| route/controller | Chat/Financial Agent 在“无 symbol 且 need_news”时路由 |
| service | `GetIndustryNewsTool.run` |
| provider adapter | 工具内直接 `ak.stock_news_em(symbol=keyword)`，绕过统一 NewsDataService |
| 真实上游 host/provider | 同一东方财富网页搜索接口 |
| 是否需要 symbol | 否；需要 keyword |
| 是否支持行业/主题 | 仅支持字符串关键词检索，不是行业分类源；不证明文章与行业的实质关系 |
| 是否有持久化 snapshot | 否；每次执行 live 请求，无缓存 |
| 字段 | title、snippet、publish_time、source、url；无 symbol/industry match basis、唯一 ID、as_of、terms_status |
| 异常与 fallback | 缺关键词或抓取异常返回 ToolResult failed；空结果返回成功空列表；无批准源 fallback |
| 来源等级 | `research_only`。因当前没有 approved 行业新闻源，AI 生产路径应返回 `unavailable` |
| 文件:行号 | `backend/app/agents/chat_tools/industry_tools.py:159-240`; `backend/app/agents/financial_agent.py:663-704`; `backend/app/agents/chat_orchestrator.py:95-114` |

### 3.4 通用实时新闻/主题/市场关键词工具

| 字段 | 证据结论 |
|---|---|
| 用户入口/API endpoint | Chat 消息；无独立 REST endpoint |
| route/controller | Financial Agent no-symbol realtime routing |
| service | `SearchRealtimeNewsTool`; `UniversalMarketSearchTool(mode=news)` |
| provider adapter | 两者都直接调用 `ak.stock_news_em(symbol=keyword)` |
| 真实上游 host/provider | 同一东方财富网页搜索接口 |
| 是否需要 symbol | 否；news 模式要求 keyword |
| 是否支持行业/主题/市场 | 只支持任意关键词命中，未提供分类、实体关系或市场范围校验 |
| 是否有持久化 snapshot | 否；每次 live 请求，无缓存 |
| 字段 | SearchRealtimeNews 有 URL；Universal news 丢弃 URL；二者均无 ID、as_of、terms_status、匹配依据 |
| 异常与 fallback | 异常返回 failed；Universal 非法 mode 会默认 news，可能扩大误路由风险；无批准源 fallback |
| 来源等级 | `research_only`；Universal news 因丢 URL 和缺质量字段，在生产事实输出层按 `disabled` 处理 |
| 文件:行号 | `backend/app/agents/chat_tools/realtime_search_tools.py:34-106,111-202`; `backend/app/agents/financial_agent.py:706-799`; `backend/app/agents/chat_orchestrator.py:95-114` |

`concept`、`industry_rank`、`fund_flow`、`hot_stocks` 是行情/热度工具，不是新闻源。其东方财富/AKShare 数据只能作为研究线索，不能被转述为新闻事实；行业热门股另有 `industry_hot_stock_snapshot` 持久化表，但该表保存排名和行情因子，不保存新闻。

### 3.5 CNINFO 官方公告/定期报告

| 字段 | 证据结论 |
|---|---|
| 用户入口/API endpoint | `POST /api/v1/stocks/{market}/{code}/reports/discover`; `/discover/latest`; `GET .../fundamentals/modules/report_documents` |
| route/controller | report discovery/fundamentals routers |
| service | `report_discovery_agent` → `report_document_service` |
| provider adapter | `cninfo_provider.search_announcements*` / report discovery tool |
| 真实上游 host/provider | CNINFO 官方 `www.cninfo.com.cn`; PDF 白名单 `static.cninfo.com.cn` |
| 是否需要 symbol | 是；当前报告发现只支持 CN |
| 是否支持行业/主题 | 否；官方公司公告/定期报告 |
| 是否有持久化 snapshot | 是；高置信候选可 upsert 到 `report_documents`，保存来源、披露日、文件 hash/状态等 |
| 字段 | title、announcement_date/disclosure_date、source/source_url/pdf_url、symbol/ts_code、announcementId（上游）、DB id、created_at；无明确 terms_status/as_of 字段 |
| 异常与 fallback | timeout/connect/http/failed 均结构化为空结果；历史类目空时可回退 CNINFO fulltext；不枚举 PDF ID；报告年份可向前回退 |
| 来源等级 | `approved`，只限官方公告/报告事实；不自动扩展为媒体新闻事实 |
| 文件:行号 | `backend/app/datasource/cninfo_provider.py:32-58,270-349,373-455,458-539`; `backend/app/routers/report_discovery.py:64-130,133-229`; `backend/app/services/report_document_service.py:43-144,146-191`; `backend/app/models/report_document.py:14-47` |

### 3.6 Tushare 业绩预告/快报与 Tushare news

| 字段 | 证据结论 |
|---|---|
| 用户入口/API endpoint | fundamentals `announcements` 模块（经兼容/模块路由）；Tushare `news` 无入口 |
| service/provider | `AnnouncementsTool` → `tushare_client.get_forecast/get_express` → Tushare SDK |
| 是否需要 symbol | 是，转换为 ts_code |
| 支持范围 | 业绩预告/业绩快报，不是通用公司/行业/市场新闻 |
| snapshot | 工具层有 TTL/stale cache 语义，但不是来源记录持久化快照 |
| 字段 | ann_date 等结构化业绩字段；没有原公告 URL、唯一公告 ID、terms_status、as_of |
| 异常与 fallback | forecast/express 并发，允许单边 partial；Tushare 权限异常映射为 auth error |
| 来源等级 | `owner_review_required`，等待合同/Owner 书面确认；Tushare `news` 保持 `permission_denied` 与 `disabled` |
| 文件:行号 | `backend/app/tools/fundamental/announcements.py:1-82`; `backend/app/datasource/tushare_client.py:173-217,541-559`; `backend/app/core/config.py:211-223` |

## 4. 字段与治理缺口汇总

| 链路 | 标题 | 发布时间 | 来源名 | 原文 URL | 匹配依据 | 唯一标识 | as_of | 条款状态 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 个股 REST/Agent | 有 | 有，可能无法解析仍保留 | 有，可能空 | 有，可能空 | 仅请求 symbol 被写回 `symbols`，不是文章实体证明 | 无 | 无 | 无 |
| 行业关键词 | 有 | 有，未标准化 | 有 | 有 | 仅 keyword，未返回证据 | 无 | 无 | 无 |
| 实时关键词 | 有 | 有，未标准化 | 有 | Search 有；Universal 无 | 仅 keyword | 无 | 无 | 无 |
| CNINFO 报告 | 有 | 有（披露日） | 固定 cninfo | 有 | symbol/ts_code + 官方查询 | 上游 announcementId；持久化后 DB id | created_at 可作摄取时间，但没有显式 as_of | 无显式字段 |
| Tushare forecast/express | 类型/摘要 | ann_date | 固定 tushare | 无 | ts_code | 无 | 无 | 无 |

## 5. 来源分级

| 来源 | 唯一分级 | 结论 |
|---|---|---|
| CNINFO 官方公告/报告 | `approved` | 可用于公告/报告事实，保留官方 URL 和披露日 |
| Tushare forecast/express | `owner_review_required` | 供应商权限/合同状态需 Owner 确认；不能替代原公告 |
| AKShare → 东方财富新闻搜索 | `research_only` | 公开网页搜索抓取，无授权证明、无条款状态、匹配弱 |
| AKShare → 东方财富概念/行业/资金/热股 | `research_only` | 仅作为研究线索/行情热度，不是新闻事实 |
| Tushare `news` | `disabled` | 当前 `permission_denied`，无已接入实现；本轮不购买、不接入 |
| Finnhub 新闻 | `disabled` | 未发现实现、配置或来源契约 |
| Sina/Tencent 新闻 | `disabled` | 未发现新闻调用链；现有代码仅用于行情/基本面，不能冒充新闻源 |
| Universal news 输出 | `disabled` | 上游本身 research_only，且该链路丢失 URL、无质量字段 |

## 6. 必须执行的 Agent 边界

1. 禁止将 `get_latest_news_tool` 或 `/stocks/{market}/{symbol}/news` 用于行业问题；它要求 symbol，且股票关键词结果不能代表行业。
2. 禁止把公司名与行业关键词共现解释为“直接受益”、供应链关系、客户/供应商关系或确定性产业链位置。
3. 行业、主题和市场新闻在没有 approved 来源时必须返回结构化 `unavailable`；不得反问用户提供股票代码来绕成个股新闻，不得生成或补全新闻。
4. `research_only` 结果可以内部用于发现候选线索，但在进入 LLM 最终事实上下文前必须隔离；当前代码仍会把这些摘要注入 LLM，因此“可安全复用”尚未达成。
5. 官方公告事件只可由 CNINFO（或未来明确批准的交易所官方源）支持，并必须带披露日与官方来源 URL。
6. 在来源审批、字段补齐、持久化与 Agent fail-closed 改造完成前，不得宣告现有新闻链路 production-ready。

