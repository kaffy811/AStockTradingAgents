# TradingAgents — 简历项目经历（中英文版）

---

## 中文简历版

**项目：TradingAgents — AI 多 Agent 股票研究助手**

- 基于 FastAPI + Vue 3 构建面向 A 股与港股的 AI 多 Agent 股票研究系统，支持技术面、基本面、同行对比、新闻面及综合分析，集成报告保存、历史中心、自选股工作台、行业热度与股票横向对比功能，前端 195 模块构建通过。
- 将 4 Agent 综合分析从串行改为并行，端到端报告生成时延由约 120s 降至 35–45s（约 3×）；当前后端声明 109 个 HTTP 路由，前端覆盖 11 个顶层业务页面。
- 设计 custom coordinator 与 LangGraph 双分析引擎，通过统一 response schema 与 SSE 事件协议实现前端无差异接入；实现 `_resolve_analysis_engine()` 优先级链（显式传参 > 环境变量 > 硬编码 fallback），支持 `DEFAULT_ANALYSIS_ENGINE` env 一行灰度切换，服务不因 env 误配崩溃。
- 实现 `AnalysisRunRegistry` 抽象层（Memory / Redis 双后端），Redis 模式通过 Pub/Sub + event_id replay 支持 `uvicorn --workers N` 多进程 SSE 状态共享；修复 `asyncio.wait_for` 取消 async generator 的 B1 bug（改用 `asyncio.shield`），完成 4-worker、16 个并发 run 压测（16/16 通过）；重连回放 3/3 事件正确，event_id 无重复。
- 建立财报 RAG 索引与检索链路，持久化 4 份活跃报告、1,217 个 chunks；在 8 个多报告问题评估中 retrieval hit rate 与 citation page accuracy 均为 100%，跨报告泄漏为 0。
- 构建多语言 UI（6 种语言，自定义 i18n.js）与多语言 AI 报告体系，将 UI 语言与报告 `output_language` 解耦，Agent-level system prompt 透传语言参数，支持同一界面生成不同语言的分析报告。
- 完成 Release Candidate 全量收口：后端 4,975/4,975、前端 688/688 自动化测试通过（0 failed），并完成 14 项运行时回归、8 项 M42 env 灰度验证、16 项多 worker 压测与 3 套主题 × 6 语言静态验证。

---

## English Resume Version

**Project: TradingAgents — AI Multi-Agent Equity Research Assistant**

- Built a full-stack AI equity research assistant for A-share and Hong Kong stocks using FastAPI and Vue 3, supporting technical, fundamental, peer comparison, news, and comprehensive analysis modes with report history, watchlist management, industry heat maps, and stock comparison; production build passes at 195 modules.
- Parallelized the 4-agent comprehensive-analysis pipeline, reducing end-to-end report latency from about 120s to 35–45s (~3×); the current product exposes 109 HTTP routes across 11 top-level Vue business views.
- Designed dual analysis engines (custom coordinator and LangGraph) with a unified response schema and SSE event protocol for transparent frontend integration; implemented a `_resolve_analysis_engine()` priority chain (explicit param → env default → hardcoded fallback) enabling zero-downtime engine rollout via the `DEFAULT_ANALYSIS_ENGINE` environment variable.
- Implemented an `AnalysisRunRegistry` abstraction with Memory and Redis backends; the Redis backend uses Pub/Sub and persisted event lists with monotonic `event_id` replay to support multi-worker (`uvicorn --workers N`) cross-process SSE task sharing; fixed an `asyncio.wait_for` async-generator cancellation bug using `asyncio.shield`; validated 16/16 concurrent runs across 4 workers, with 3/3 replayed events correct and no duplicate event IDs.
- Built a financial-report RAG pipeline with 4 persisted active documents and 1,217 chunks; achieved 100% retrieval hit rate and citation-page accuracy on an 8-question multi-report evaluation with zero cross-report leakage.
- Developed a multilingual UI (6 languages, custom i18n.js) and multilingual report generation pipeline, decoupling interface language from report `output_language` and passing language parameters to each Agent's system prompt at the LLM call level.
- Delivered a release-candidate build with 4,975/4,975 backend tests and 688/688 frontend tests passing (0 failures), plus a 14-item runtime regression, 8-case engine rollout matrix, 16-run multi-worker stress test, and cross-theme × cross-language static build check.

---

## 关键技术词（面试关键词列表）

**后端**：FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis Pub/Sub, SSE, asyncio, LangGraph, Send API fan-out, AnalysisRunRegistry ABC, asyncio.shield

**前端**：Vue 3 Composition API, Vite, Vue Router, Pinia, lightweight-charts, marked + DOMPurify, i18n, CSS variables

**架构**：多 Agent 并行分析, dual engine gradual rollout, multi-worker run registry, event replay, SSE heartbeat, output_language decoupling

**质量**：14-item runtime regression, 16-run concurrent stress test, 8-case env rollout matrix, RC delivery
