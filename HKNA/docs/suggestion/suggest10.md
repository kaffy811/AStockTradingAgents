# HKNA 产品验收报告 10

## 1. 本次验收范围

只读检查 `aastock.cloud` 当前部署版本、公开 HTTP 路由、Company V2 server-local API、Supabase 关键数据量、Redis、CNINFO/RAG、Tushare/BaoStock 状态、调度与脱敏日志。未执行代码修改、部署或数据写入。浏览器不可用，因此页面截图、console、登录交互和 Chat 新会话没有完成。

## 2. 已完成内容盘点

- Git/backend/frontend 版本一致，无 deployment skew。
- 服务器健康，Company profile 与 EOD backend 数据实际存在。
- Tushare EOD 提供字段级 source/as_of/unit 与非实时标记。
- CNINFO company profile 对 000725/600519 非空且 fresh。
- Company RAG 数据库已有 6 个索引文档与 1721 chunks，但线上 feature flag 关闭。
- 匿名 `/api/v1/stocks/*` 鉴权边界稳定。

## 3. 数据验收

### 3.1 新闻数据

- 数据内容：生产数据库未发现 news/event 领域表。
- 数据来源：没有证据表明存在 approved 行业新闻源。
- 获取或运行方式：未发现新闻 scheduler/worker。
- 当前状态：UNAPPROVED / 未形成可验证线上链路。
- 当前可用性：不能验证；五条 Chat 因浏览器阻断未执行。
- 主要问题：deep health 中 AKShare 显示 available 只能表示能力可装载，不能解释为获批或已调用。

### 3.2 股票数据

- 数据内容：Company profile、EOD quote/valuation/financial、annual history 可用；000725 quarterly history 缺失。
- 数据来源：CNINFO、Tushare、BaoStock。
- 获取或运行方式：当前主要由请求时读取与 Redis cache 支撑；未发现应用 scheduler。
- 当前状态：backend 数据可用，但公网 `/api/v2` 被 SPA fallback 阻断；带交易所后缀的 EOD 代码失败。
- 当前可用性：从真实用户公网路径看为不可接受；从 server-local backend 看为部分可用。
- 主要问题：公网反代、symbol normalization、季度覆盖、BaoStock timeout、缺少 endpoint telemetry。

## 4. 功能验收

- 功能/模块：公网首页与静态资源
- 当前作用：SPA 入口和资源加载
- 当前状态：HTTP 可用
- 是否可用：PARTIAL（无浏览器渲染证据）
- 当前价值：站点可到达
- 主要缺口或风险：不能确认 console、交互、移动布局或登录态

- 功能/模块：Company V2 页面数据
- 当前作用：公司资料、history、EOD 展示
- 当前状态：P0 阻断
- 是否可用：FAIL
- 当前价值：backend 数据完整，但公网无法取得 JSON
- 主要缺口或风险：frontend Nginx 仅代理 `/api/v1/`

- 功能/模块：Stock EOD identifier handling
- 当前作用：统一股票代码获取 Tushare EOD
- 当前状态：P0
- 是否可用：PARTIAL
- 当前价值：裸六码可用
- 主要缺口或风险：`.SZ/.SH` 在 EOD 路径返回 unavailable

- 功能/模块：Chat research
- 当前作用：个股 EOD 与主题 fail-closed
- 当前状态：NOT_TESTED
- 是否可用：无法确认
- 当前价值：不能基于既有本地 artifact 推定线上结果
- 主要缺口或风险：无浏览器、无指定测试账号，且新建会话会写数据库

- 功能/模块：Report RAG
- 当前作用：财报问答与证据检索
- 当前状态：数据部分存在，runtime disabled
- 是否可用：UNAVAILABLE
- 当前价值：已有 6 文档/1721 chunks 可供后续恢复
- 主要缺口或风险：feature flag false、embedding provider mock

- 功能/模块：自动更新与覆盖审计
- 当前作用：数据刷新、缺失字段回填
- 当前状态：未部署调度
- 是否可用：FAIL
- 当前价值：表结构与队列存在
- 主要缺口或风险：snapshot 陈旧、108 pending

## 5. 当前产品阶段判断

当前处于“backend 数据链路可用、生产公网契约与运行闭环未完成”的阶段。最优先的不是接入更多 Provider，而是恢复 Company V2 的真实公网可用性，并补齐浏览器验收和可观测性。

## 6. 下一步任务

### P0

1. 修复受版本控制的 frontend Nginx `/api/v2` 反代，并以公网 JSON contract 验收。
2. 统一 EOD 对 `000725/000725.SZ/600519/600519.SH` 的解析。
3. 用真实浏览器和测试账号补齐五条新会话、UI 状态与 console/Network 证据。

### P1

1. 明确 000725 quarterly history 的数据覆盖和空态。
2. 建立 bounded scheduler 和 last-success telemetry，处理 108 项 pending queue。
3. 为 request ID、Tushare endpoint、cache hit、BaoStock timeout 增加脱敏结构化日志。
4. 独立决定 Report RAG runtime 是否启用；不能把 mock embedding 当线上可用。

### P2

1. 统一 profile 的 top-level source 与 profile_source 解释，同时保留完整 provenance。
2. 评估静态 JS 体积与公网加载时间，但不要在 P0 修复前抢占优先级。

## 7. 注意事项

- `HTTP 200 text/html` 不能作为 API 成功。
- health 中 provider `available` 不能解释为授权或线上调用成功。
- EOD 是最近交易日数据，不能描述为实时。
- provider_error_log 为 0 不代表零 Provider 错误；运行日志已证明 BaoStock timeout。
- 在获得浏览器证据前，不得宣称主题 fail-closed、numeric evidence 或 UI 完成态线上通过。

## 8. 推荐的单一步骤

先提交一个只覆盖 frontend Nginx `/api/v2` 反代和公网 contract test 的最小 P0 修复；发布后立即用浏览器复验 Company 页面，再处理股票标识归一化。
