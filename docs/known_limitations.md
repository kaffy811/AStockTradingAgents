# TradingAgents — 已知限制与注意事项

> 版本：M40-c 运行时回归（2026-06-09）  
> 用途：部署说明、面试透明度、产品交接

---

## 一、数据源限制

| 限制 | 说明 |
|------|------|
| 第三方接口依赖 | AkShare / Sina / yfinance 均为非官方或公开接口，稳定性不受控；超时会触发降级路径 |
| 港股行业体系不完整 | 申万行业分类仅覆盖 A 股；港股无行业热门股功能，前端显示友好提示 |
| HK stock_master 覆盖有限 | 当前约 30 只主流港股（腾讯/阿里/美团等）；长尾港股搜索 fallback 到 AkShare 实时查询 |
| 基本面数据 HK 覆盖差 | 港股基本面数据通过 yfinance 获取，字段覆盖率较低，报告会注明数据不足 |
| 新闻覆盖依赖数据源 | 东方财富 AkShare 新闻接口，覆盖范围和时效受限；港股新闻通过关键词搜索，相关性有限 |
| K 线数据可能存在缓存或延迟 | AkShare 行情存在 15 分钟左右延迟；前端 stale 标记在 metadata.warnings 中记录 |
| 实时报价精度 | 报价数据通过 Sina 获取，非 Level 2 行情，仅供参考 |

---

## 二、后端运行时限制

| 限制 | 说明 |
|------|------|
| SSE run registry 默认内存单 worker | `MemoryAnalysisRunRegistry` 默认模式；进程重启后 run 状态丢失。设置 `ANALYSIS_RUN_REGISTRY=redis` 切换为持久化 Redis 模式（M40-b 已验证） |
| 多 worker Redis 模式就绪 | `uvicorn --workers N` + `ANALYSIS_RUN_REGISTRY=redis` 已通过 M40-c 验证。不配置 Redis 时 registry fail-fast 返回 HTTP 503 |
| `asyncio.to_thread` 无法强制取消 | 取消分析只是"停止等待"（前端断开 SSE + 后端标记 cancelled）；已启动的同步 agent 线程不可强制中断 |
| LangGraph 支持 Redis registry | LangGraph runner 与 custom_coordinator 共享同一 AnalysisRunRegistry ABC，两种模式均已验证 |
| Redis event_maxlen 淘汰 | 事件超过 `ANALYSIS_RUN_EVENT_MAXLEN`（默认 500）时，最旧事件被 LPUSH+LTRIM 淘汰；replay 仅能回放未被淘汰的事件 |
| MAX_RUNS = 200 LRU 淘汰（内存模式） | 超过 200 个 run 时，最旧的已完成 run 会被淘汰；活跃 run 不会被淘汰 |
| 分析耗时较长 | comprehensive scope 全量分析约 60-180 秒（取决于 LLM 响应速度和数据源）；technical_only 通常 20-40 秒 |

---

## 三、LangGraph 限制

| 限制 | 说明 |
|------|------|
| 灰度状态（M42：G2 已实现）| `DEFAULT_ANALYSIS_ENGINE=langgraph` 环境变量已实现（M42）；staging 可通过 env 切换默认引擎，生产仍为 custom_coordinator；显式 engine 请求优先于 env |
| 未使用 astream_events | 当前使用 `graph.astream(stream_mode="updates")`；节点级 updates 足够，但 agent_started 事件晚于节点实际开始时间（node 完成才能确认下一批 agent）|
| LangGraph 版本耦合 | StateGraph Send API 在 LangGraph 版本间有变化；升级时需验证 fan-out 行为 |
| synthesis 失败降级 | synthesis LLM 失败时使用 `_fallback_report` 生成降级报告；降级内容不包含 LLM 汇总，质量较低 |

---

## 四、前端限制

| 限制 | 说明 |
|------|------|
| 移动端为 PWA / Mobile Web | 非原生 App；依赖浏览器支持 PWA，Service Worker 当前未配置 offline cache |
| SSE 依赖 fetch + ReadableStream | 使用原生 fetch 替代 EventSource，因 EventSource 不支持 Authorization header；IE 完全不支持 |
| keep-alive 缓存下的 setup 不重跑 | ComprehensiveAnalysisView 使用 keep-alive；路由参数变化通过 watch(route.query) 响应，setup() 不重跑 |
| 历史报告 auto-save 仅限 auto_save_report=true | 默认自动保存；手动关闭后结果不会自动入库，需用户手动点"保存报告" |

---

## 五、业务声明

| 声明 | 说明 |
|------|------|
| 不构成投资建议 | 所有报告仅供研究参考；系统禁止生成买入/卖出/持有建议 |
| LLM 输出需用户自行判断 | AI 生成内容可能存在事实性错误，尤其是数值类；用户应以官方数据源为准 |
| 数据仅供研究 | K 线、财务数据、新闻均来自第三方，不保证实时性和准确性 |
| 报告中的风险提示 | 所有 LLM 生成报告末尾包含"风险提示：仅供研究参考，不构成投资建议" |

---

## 六、已实现与低优先级路线

| 特性 | 当前状态 | 说明 |
|------|----------|------|
| Redis run registry | ✅ M40-b 已实现，M43 4-worker 压测 16/16 PASS | 配置 `ANALYSIS_RUN_REGISTRY=redis`；event_maxlen 满后旧事件被 LTRIM 淘汰 |
| LangGraph 双引擎 | ✅ M42 G2 env 灰度 | `DEFAULT_ANALYSIS_ENGINE=langgraph` 可在 staging 灰度；生产保持 custom_coordinator |
| UI 多语言 | ✅ M34/M35 已实现 6 种语言 | zh-CN / zh-TW / en-US / ja-JP / ko-KR / de-DE |
| AI 报告多语言 | ✅ M36/M37 Agent-level prompt 透传 | output_language 独立于 UI 语言 |
| LangGraph 生产默认（G4）| 低优先级 | 条件：staging 稳定 1-2 周 + 50 次 comprehensive 无异常 |
| 移动端原生 App | 未计划 | PWA 已覆盖移动端 |
| 实时 WebSocket 行情 | 未计划 | 当前轮询/快照满足 demo 需求 |
| 港股全量 stock_master | 30 只（低优先级扩充）| 依赖稳定数据源 |
| 报告分享链接 | 未计划 | |

---

## 行业热股数据量限制（M50 更新，2026-06-11）

**现象：** 部分冷门行业入库股票数量本身较少（如"综合"14支、"钢铁"43支、"煤炭"43支、"环保"28支）。

**原因：**
- 申万一级行业部分冷门行业收录股票数量本身较少
- 行业热度数据来自 AkShare/Sina spot 接口，个别行业当日无成交数据时不出现在热股列表中
- 后端 `limit` 为上限，实际返回 `min(limit, 实际有效数量)`

**M50 修复：**
- `refresh_industry_hot_stocks.py --top-n 50` 已重新运行（M47-b 时仅运行 top-n=5）
- 30/30 行业均已写入 Top-50 快照（银行 42 支因当日部分银行股无成交数据）
- 后端 `le=50` → `le=100`，为未来扩容留余量
- 响应新增 `total` 字段：行业在 `stock_industry_map` 中的真实成分股总数

**当前行业数据覆盖（2026-06-11）：**
- 大部分主流行业：50 支热股快照（电力设备/计算机/医药生物/汽车等）
- 冷门行业：实际可用快照数量（14-43 支）
- 银行：42 支（38 家上市银行中有 42 只股票在 spot 数据中可见）

**交互行为：** 
- 股票数量 ≤ 20：不显示"查看更多"按钮
- 股票数量 > 20：可展开，显示 `N / industry_total` 格式
- 股票数量 = 0（无数据）：显示空状态文案
