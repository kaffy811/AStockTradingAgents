# TradingAgents — 面试讲解稿

---

## 1 分钟版本（适合"介绍一下你的项目"）

**中文版**

TradingAgents 是我独立开发的 AI 股票研究辅助系统，支持 A 股和港股。用户输入股票代码后，系统会同时跑四路 Agent——技术面、基本面、同行对比、新闻面，通过 SSE 实时推送进度，最后由 LLM 汇总生成结构化报告。

技术上比较有意思的地方有三个：一是 AnalysisRunRegistry 抽象层，支持内存和 Redis 双后端，Redis 模式可以横向扩展到多 worker；二是双 engine 设计，custom coordinator 和 LangGraph 并行维护，通过一个环境变量就能灰度切换；三是 output_language 与 UI 语言完全解耦，用户可以在中文界面生成英文报告。

系统最终通过了 RC 收口验证，4 个 worker 并发跑了 16 个分析任务，全部通过。

---

**English Version (1-min)**

TradingAgents is a full-stack AI equity research assistant I built independently, covering A-share and Hong Kong stocks. Users enter a stock ticker and four Agents run in parallel—technical, fundamental, peer comparison, and news—with real-time progress via SSE, and a synthesis LLM producing a structured report.

Three things I'm particularly proud of technically: first, an AnalysisRunRegistry abstraction that supports both in-memory and Redis backends, enabling multi-worker horizontal scaling. Second, a dual-engine design—custom coordinator and LangGraph—where a single environment variable controls which engine is the default, with no code changes needed. Third, report output language is completely decoupled from UI language, so users can generate English reports in a Chinese interface.

The system passed release-candidate validation with 16 concurrent runs across 4 workers, all passing.

---

## 3 分钟版本（技术面试深入介绍）

**项目背景**

这个项目的起点是我想做一个能替代手动查财务数据的工具。最初只是单 agent 生成报告，后来逐步演进成多 Agent 并行的架构，并加入了 SSE 实时进度、双引擎、多语言等特性。整个项目从 MVP 到 RC 经历了约 43 个迭代阶段。

**技术栈**

后端是 FastAPI + SQLAlchemy + PostgreSQL（Supabase 托管）+ Redis。前端是 Vue 3 + Vite，195 个模块。部署用 Docker Compose，Nginx 反向代理。

**多 Agent 分析流程**

用户请求进来后，`POST /analysis/runs` 创建一个分析任务，后台启动 custom coordinator 或 LangGraph runner。coordinator 会并行调度 4 个 Agent：
- TechnicalAgent：拉 K 线数据，计算 MA/MACD/RSI
- FundamentalAgent：财务数据，PE/PB/营收
- PeerComparisonAgent：申万行业对比，Hot Score 排名
- NewsAgent：72 小时新闻摘要

四路 Agent 都完成后，synthesis LLM 汇总生成最终报告。

**SSE 实时进度**

前端通过 `GET /analysis/runs/{id}/events` 订阅 SSE 流。这里有个细节：我用的是 `fetch + ReadableStream` 而不是标准 `EventSource`，原因是 `EventSource` 不支持 Authorization header。

SSE 可靠性方面修了一个比较有意思的 bug：原来用 `asyncio.wait_for(__anext__(), timeout=15)` 来实现心跳，但超时会触发 coroutine 取消，导致 async generator cleanup 提前关闭流。修复是用 `asyncio.shield(pending_task)`，把 task 和超时逻辑分离——超时只是 yield 一个 heartbeat comment，task 继续跑。

**Redis Registry 多 worker 设计**

AnalysisRunRegistry 是一个 ABC，有 Memory 和 Redis 两个实现。Redis 模式下每个 run 对应 4 个 key：Hash 存状态、List 存事件历史、INCR counter 提供单调递增 event_id、Pub/Sub channel 推送实时事件。这样 4 个 uvicorn worker 共享同一 run 状态，任意 worker 都可以继续 SSE 流。

**双 engine 灰度**

custom_coordinator 是纯 Python 实现，容易 debug；LangGraph 用 Send API 做 fan-out，节点级更新流式推送。两者 response shape 完全兼容——我做了 Python set diff 验证，top-level key 差集为空。

灰度机制是一个优先级链：`explicit body.engine > DEFAULT_ANALYSIS_ENGINE env > "custom_coordinator"`。非法 env 值会 fallback，服务不崩。

**验证结果**

14 项运行时回归全通过；8 项 env 灰度 case 全通过；4-worker 并发 8 run × 2 engine = 16/16 PASS。

---

## 5 分钟版本（作品集展示）

### 项目背景与动机

这个项目源于我对 A 股研究工具链的一个观察：市面上大多数工具要么是纯数据展示，要么是黑盒 AI 推荐。我想做一个透明的、可以看到分析过程的研究辅助工具，而且需要支持多维度、结构化的报告输出。

从 MVP 到最终的 Release Candidate，项目经历了约 43 个迭代阶段，核心演进路径是：单 agent 报告 → 多 agent 并行 → SSE 实时进度 → 双 engine 灰度 → Redis 多 worker → 多语言 → RC 收口。

### 技术架构

整体分三层：
1. **数据层**：AkShare / yfinance / Sina 多源数据融合，PostgreSQL 存报告历史和股票主数据，Redis 做 run registry 和行情缓存
2. **分析层**：4 个专项 Agent + synthesis LLM，支持 6 个分析 scope
3. **展示层**：Vue 3 前端，195 模块，SSE 实时进度，8 个路由页面

### 多 Agent 分析流程

每次分析请求通过 `POST /analysis/runs` 异步创建，在后台 worker 线程中运行。4 个 Agent 并行调度——技术面、基本面、同行对比、新闻面——通过 `asyncio.gather` 或 LangGraph Send API fan-out 同时执行，全部完成后 synthesis LLM 汇总。

事件流是细粒度的：`analysis_started` → `identity_resolved` → `agent_started` × 4 → `agent_completed` × 4 → `synthesis_started` → `synthesis_completed` → `report_ready`。前端用进度条 + event 列表实时展示每个节点的状态。

### SSE 实时进度与 Registry 设计

SSE 流的实现有两个技术决策值得提：

第一，用 `fetch + ReadableStream` 替代 `EventSource`，解决 Authorization header 问题。断线重连通过 `?after_event_id=N` 参数 replay 已发事件。

第二，`asyncio.shield` 心跳修复。原先 `asyncio.wait_for(gen.__anext__(), timeout=15)` 在超时时会取消底层 coroutine，触发 async generator 的 cleanup 逻辑关闭整个流。用 `asyncio.shield` 包裹 pending task，让超时只影响 wait，不影响 task 本身，心跳就是 yield 一行注释。

AnalysisRunRegistry 抽象层让 Memory 和 Redis 后端完全可替换。Redis 模式的四键设计（Hash / List / INCR / Pub/Sub）支持任意 worker 读写同一 run 状态，解决了多进程 SSE 的核心问题。

### LangGraph 与 custom coordinator 双 engine

LangGraph 用 `StateGraph` + `Send` API 做 fan-out，每个 agent 是一个独立节点，输出合并到 `collect_node`。与 custom coordinator 相比：代码更声明式，fan-out 结构更清晰，但 debug 成本更高，版本升级时 Send API 行为可能变化。

为了让前端无感知切换，我做了 response shape 兼容验证——用 Python set 取两个引擎真实输出的 top-level key 差集，结果为空集。所有 SSE 事件类型和字段也完全对齐。

灰度机制：`DEFAULT_ANALYSIS_ENGINE=langgraph` 将 staging 默认引擎切换为 LangGraph，显式请求始终优先。非法 env 值 fallback 到 custom_coordinator，服务不崩。这是一个典型的防御性设计——配置错误不应该导致服务崩溃。

### 多语言设计

UI 语言和报告 output_language 是完全独立的设置。UI 通过自定义 `i18n.js`（不引入外部库，直接 reactive ref + computed）控制 11 个组件的界面文本；AI 报告语言通过请求 body 传 `output_language`，透传到每个 Agent 的 system prompt 里，LLM 直接生成目标语言的报告。6 种 UI 语言 × 6 种报告语言可以任意组合。

### 验证与 RC 收口

压测配置：4-worker uvicorn + Redis registry，并发 8 run × 2 engine。所有 16 个 run 都成功，terminal_event 全为 `report_ready`，event_id 无重复。

整个项目的测试覆盖分层：
- 14 项运行时回归（memory + Redis × custom_coordinator + LangGraph）
- 8 项 env 灰度矩阵（含 bad_value fallback + Redis 模式 + 前端 dev/non-dev）
- 16 项多 worker 并发压测
- build / compileall / alembic 三项静态检查

### 已知限制与改进方向

主要限制：
- 分析耗时较长（20-180s，LLM 速度绑定）
- 港股行业覆盖有限（约 30 只主流港股）
- asyncio.to_thread 不可强制取消（取消语义为"停止等待"）

低优先级改进：
- LangGraph 升为生产默认（条件：staging 稳定 1-2 周 + 50 次无异常）
- 港股 stock_master 扩充（依赖稳定数据源）
- Redis event TTL / maxlen 配置化

---

## 常见追问与参考回答

**Q: 为什么不用 WebSocket 而用 SSE？**
A: SSE 是单向推送，天然适合"服务端生成 → 客户端消费"的模式。事件有序、有 ID、可 replay，不需要客户端发消息。实现比 WebSocket 简单，部署不需要额外的 WS 协议升级处理。如果需要双向实时通信（比如用户实时干预分析），才考虑 WebSocket。

**Q: LangGraph 和 custom coordinator 最终会保留哪个？**
A: 计划长期双轨。custom_coordinator 是稳定 fallback，LangGraph 是探索更声明式架构的路径。两者 shape 兼容，前端无感知。G4 升级的条件是 staging 稳定验证，不是"替换"而是"提升默认"。

**Q: Redis 多 worker 方案有什么风险？**
A: 主要风险是 Redis 单点。当前方案在 Redis 不可用时 fail-fast 返回 HTTP 503，不会静默降级到内存模式（防止跨 worker 数据不一致）。event_maxlen 满后老事件被淘汰是已知 trade-off，通过文档说明。

**Q: asyncio.shield 为什么能解决问题？**
A: `asyncio.wait_for(coro, timeout)` 在超时时会取消传入的 coro。如果这个 coro 是 async generator 的 `__anext__()`，取消会触发 generator 的 `athrow(CancelledError)`，进而关闭整个 generator。`asyncio.shield` 把 task 包装成一个"受保护"的 future，外层超时取消的是 shield 返回的 future，不是 task 本身，task 继续在 event loop 里跑。
