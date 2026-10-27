# Phase 7C0 — Agent News Reuse Decision

## 决策

当前新闻 Agent/工具不能直接复用于 AI Research Copilot 的生产事实输出。仅 CNINFO 官方公告/报告链路可复用；其余新闻链路要么只可作为隔离的研究线索，要么必须禁用。

| 问题类型 | 可复用现有接口？ | 允许生产事实输出？ | 原因 |
|---|---:|---:|---|
| 个股新闻 | 仅研究线索 | 否 | `stock_news_em` 是东方财富公开网页关键词搜索，经 AKShare 抓取；无授权证明、唯一 ID、as_of、条款状态，且 HK 弱相关 |
| 行业新闻 | 否 | 否 | 现有工具只是把行业词传给个股新闻关键词搜索；不是批准的行业新闻源，也没有行业匹配依据 |
| 主题产业链研究 | 否 | 否 | 关键词共现不能证明直接受益、客户/供应商或产业链关系；缺少批准来源与实体关系证据 |
| 市场新闻 | 否 | 否 | 通用工具仍使用同一网页关键词搜索，部分链路还丢失原文 URL；热点/排行不是新闻 |
| 官方公告事件 | 是，限 CNINFO | 是 | 官方域名、披露日、来源 URL、公告/报告标识与可持久化记录可形成来源链 |

## Agent 复用白名单

- 可复用：CNINFO discovery/provider、URL 白名单校验、`report_documents` 持久化读取、官方公告/报告元数据。
- 条件复用：Tushare `forecast`/`express` 仅在 Owner 书面确认合同/权限后使用；在此之前不输出事实。
- 研究线索：`NewsDataService`、`EastmoneyNewsProvider`、`SearchRealtimeNewsTool`、`GetIndustryNewsTool` 只能在与最终回答隔离的研究发现层使用，不得直接进入最终事实上下文。
- 必须禁用：`UniversalMarketSearchTool(mode=news)` 的生产事实输出；Tushare `news`；不存在的 Finnhub/Sina/Tencent 新闻链路。

## 必须 fail closed 的行为

### 行业新闻

当没有 approved 行业新闻源时返回：

```json
{
  "status": "unavailable",
  "reason_code": "APPROVED_INDUSTRY_NEWS_SOURCE_UNAVAILABLE",
  "message": "当前没有已批准的行业新闻来源。"
}
```

不得要求用户提供股票代码，不得退化为个股新闻，不得虚构或补全新闻。

### 主题/产业链

允许回答“当前没有批准来源可验证该关系”。禁止基于新闻中行业词与公司名共现输出“直接受益”“核心供应商”“产业链龙头”等关系事实。

### 个股与市场新闻

在批准新来源前，对事实型提问返回 `unavailable`。如产品明确开放研究线索模式，必须显式标记 `research_only`，且不得把线索转述成已确认事实。

### 官方公告事件

只有 `source=cninfo` 且带有效官方 `source_url`/`pdf_url` 和 `disclosure_date` 的记录可作为生产事实来源。缺字段时返回 `unavailable` 或降低为待核实，不得用东方财富转载替代官方公告。

## 现有实现中的复用风险

1. `NewsAgent` 将未验证的网页新闻写为 `source_level=authoritative_media`，虽然同时设置 `verified=false`，仍可能造成错误权威升级（`backend/app/agents/orchestrator/news_agent.py:91-100`）。
2. Financial Agent 当前会把行业和实时新闻工具文本直接加入 LLM 上下文（`backend/app/agents/financial_agent.py:701-704,798-799`），与本轮 `research_only` 禁止最终事实输出的规则不一致。
3. `UniversalMarketSearchTool` 非法 mode 自动回落到 news，且 news 输出无 URL（`backend/app/agents/chat_tools/realtime_search_tools.py:141-150,168-202`）。
4. 股票新闻缓存不是持久化来源快照；进程内 stale 无自动过期，不能作为可追溯历史事实库（`backend/app/services/news_data_service.py:58-97`）。

## 上线前置门槛

- Owner 批准至少一个覆盖目标范围的新闻 Provider，并留存合同/授权状态。
- 每条新闻强制保存 provider、source_name、source_url、published_at、provider_item_id、matched_entities/match_basis、ingested_at/as_of、terms_status。
- 新闻先持久化为不可变来源快照，再供 Agent 读取；禁止 Copilot 请求时直接 live 抓取。
- Agent 按来源级别 fail closed；`research_only` 不进入最终事实输出。
- 建立行业与公司关系的独立证据模型；关键词共现永远不能自动升级为产业链关系。
- Tushare `news` 继续保持 `permission_denied`，本阶段不购买、不接入。

最终状态：`EXISTING_NEWS_SOURCE_APPROVAL_REQUIRED`

