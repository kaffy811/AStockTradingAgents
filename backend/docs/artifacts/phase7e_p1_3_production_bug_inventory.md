# Phase 7E-P1.3 — aastock.cloud 线上功能与数据 Bug 全量取证

## 结论

`HOLD_WITH_EVIDENCE`

本轮只完成了可证明的公网 HTTP、服务器运行与数据侧只读取证。浏览器控制面返回空浏览器列表，因此没有真实页面截图、Network 面板、console、登录态或新对话证据；这些项目全部标为 `NOT_TESTED`，没有用 curl 或本地结果冒充浏览器验收。

已找到首个 P0：公网 frontend Nginx 只代理 `/api/v1/`，Company V2 使用的 `/api/v2/` 落入 SPA fallback。结果是服务器内网 Company API 返回 JSON 200 且数据存在，但公网同 URL 返回 868-byte `index.html`。这会直接阻断公司页通过公网加载 profile/history/EOD。

## 1. 生产基线

| 项目 | 结果 |
|---|---|
| Server Git | `fdcdc264e9178f7bb432f9101092b08c78af1ee6` |
| Backend OCI revision | `fdcdc264…` |
| Frontend OCI revision | `fdcdc264…` |
| Version skew | 否 |
| Backend image | `sha256:ab10aacc…aa90d` |
| Frontend image | `sha256:dba69ce1…2289a` |
| Containers | backend healthy；frontend running；postgres/redis healthy；四个容器 restart=0、OOM=false |
| 内存 / Swap | available 806 MiB / Swap 0 B used |
| 磁盘 | `/` 44% used，22 GiB free |
| Server dirty state | 保留 `docker-compose.staging.yml` 修改及一个 `.env.staging.local.backup...` 未跟踪文件 |

Git、backend、frontend revision 一致，因此没有登记 `DEPLOYMENT_VERSION_SKEW`，后续结果可归因到当前已部署版本。

## 2. 测试汇总

| 状态 | 数量 |
|---|---:|
| PASS | 27 |
| FAIL | 11 |
| PARTIAL | 11 |
| NOT_TESTED | 6 |
| 合计 | 55 |

计数口径：版本/健康、主要公网路由、4 个静态资源、公开 API、服务器内网 Company API 格式矩阵、匿名鉴权边界、5 条 Chat、数据库/Redis/Provider/RAG/调度/日志关联分别作为独立 gate。主要页面虽然 HTTP 200，但没有浏览器渲染/交互证据，因此计为 `PARTIAL`；五条 Chat 与整体浏览器 console/screenshot gate 计为 6 个 `NOT_TESTED`。

### 基础可用性

- `/`、`/login`、`/register`、`/chat`、两只股票详情、`/history`、`/watchlist`、`/industries`、`/compare` 均返回 HTTP 200 SPA HTML，单次 curl 总耗时约 0.67–1.10 秒。
- manifest、主 JS、Vue vendor JS、CSS 均返回 HTTP 200；主 JS 约 453 KB，下载耗时 2.41 秒。
- `/api/v1/health` 返回 JSON 200，DB/Redis 状态为 ok。
- `/health` 返回 SPA HTML，而不是 backend health JSON，登记 P1。
- 浏览器页面渲染、导航、刷新、移动宽度、加载/空态/错误态、console/CORS、缓存、旧会话和登录态影响均无法确认。

### 匿名边界

匿名请求 `/api/v1/stocks/search` 以及 profile/quote/kline/news 均稳定返回 `401 AUTH_REQUIRED`，未触发股票或新闻 Provider；这与当前路由的登录边界一致，不登记为 Bug。Company V2 原本是公开接口，但公网代理没有将 `/api/v2` 请求送到 backend。

## 3. 数据事实

### 3.1 000725

- Server-local profile：HTTP 200，`京东方科技集团股份有限公司`，`ts_code=000725.SZ`，profile source=`cninfo_company_profile`，cache=`fresh`，as_of=`2026-09-10`。
- Server-local EOD：`fulfilled`，source=`tushare`，as_of=`2026-09-09`，明确 `latest_available_eod_not_realtime`。
- 可用事实包括 close `5.55 CNY`、PE `35.1028x`、PE-TTM `26.1648x`、PB `1.5442x`、ROE `3.9218%`，财务报告期 `2026-06-30`；字段均带 source/as_of/unit。
- Annual history 有数据并带受控 outlier warnings；quarterly history 为 `DATA_NOT_AVAILABLE`。
- `000725.SZ` profile 能归一化为 `000725`，但同格式 EOD 返回 `unavailable/DATA_NOT_AVAILABLE`。

### 3.2 600519

- Server-local profile：HTTP 200，`贵州茅台酒股份有限公司`，`ts_code=600519.SH`，CNINFO profile fresh as_of=`2026-09-10`。
- Server-local EOD：`fulfilled`，Tushare as_of=`2026-09-09`，财务报告期 `2026-06-30`，明确非实时。
- 可用事实包括 close `1290.88 CNY`、PE `19.6028x`、PE-TTM `19.8161x`、PB `6.4226x`、ROE `17.9543%`，均有字段级 source/as_of/unit。
- `600519.SH` profile 能归一化，但 EOD 返回 `unavailable/DATA_NOT_AVAILABLE`。

以上是 API 数据事实，不代表网页已渲染，也不代表 Chat 已展示 request-local evidence。

## 4. Bug 清单

### P1.3-P0-001 — 公网 `/api/v2` 被 SPA fallback 吞掉

- 严重级别：P0
- 根因分类：`API_CONTRACT`
- 线上 URL/API：`https://aastock.cloud/api/v2/company/{market}/{symbol}/*`
- 复现：匿名 GET 000725 profile、annual/quarterly history、EOD，以及 600519 profile、EOD。
- 预期：Company JSON。
- 实际：六项均为 HTTP 200 `text/html`，body 为 868-byte SPA index，无 request ID；服务器 `127.0.0.1:18000` 同路径为 JSON 200。
- 浏览器截图：无，浏览器不可用。
- 服务器证据：000725 profile request `747e392b-fad0-4635-8d4d-b4afbcce0ec5`；EOD request `9479e59a-5e16-4710-94c7-8970633c91ee`。未找到 request-id 对应日志行。
- 数据：实际存在且新鲜，CNINFO profile as_of 2026-09-10、Tushare EOD as_of 2026-09-09。
- 根因：部署版本的 `frontend/nginx.conf` 只有 `location ^~ /api/v1/`；`/api/v2` 进入 `location /` 的 `try_files ... /index.html`。
- 影响：所有通过公网 origin 使用 Company V2 的用户。
- 最小修复模块：frontend Nginx API proxy；增加真实 `/api/v2` content-type/body regression。
- 配置修复：服务器临时配置可以绕过，但应在受版本控制的镜像配置中修复并重新验收。
- 数据授权：不需要新增授权。

### P1.3-P0-002 — 带交易所后缀的 EOD 标识未统一

- 严重级别：P0
- 根因分类：`ROUTING`
- API：server-local `/api/v2/company/CN/{symbol}/eod`
- 复现：比较 `000725`/`000725.SZ` 与 `600519`/`600519.SH`。
- 预期：等价标识命中同一证券。
- 实际：裸六码 fulfilled；两个带后缀标识均 HTTP 200、`unavailable/DATA_NOT_AVAILABLE`、as_of=null；profile 接口却能正确归一化四种格式。
- 浏览器截图：无。
- 数据：裸代码路径证明 Tushare 数据存在且 as_of 2026-09-09。
- 最小修复模块：Company EOD symbol normalization 与 stock EOD routing matrix。
- 配置修复：否。
- 数据授权：否。

### P1.3-P1-001 — 000725 季度 history 无数据

- 分类：`DATABASE_DATA_GAP`
- 实际：HTTP 200，`ok=false/DATA_NOT_AVAILABLE`；request ID `b67d5d13-096e-493f-a2cb-ed6c104f888c`。
- 最小修复：先确认 BaoStock 季度覆盖与数据库快照，再补受限回填或确保前端明确空态；不可把空数据伪装成成功。

### P1.3-P1-002 — 数据覆盖/回填调度未运行

- 分类：`SCHEDULER`
- 证据：运行中仅 frontend/backend/postgres/redis；无应用 systemd timer 或 crontab。coverage snapshot 最近为 2026-07-07，108 条 missing-field queue 仍 pending。
- 最小修复：独立部署有边界、可观测的调度，并记录 last success；本轮不得直接全量抓取。

### P1.3-P1-003 — BaoStock worker 20 秒超时

- 分类：`PROVIDER_NETWORK`
- 错误原文：`BaoStock subprocess failed [000725.SZ]: {'ok': False, 'error_code': 'provider_unavailable', 'timeout': 20.0, 'stderr': "Command '['/app/.venv/bin/python', '/app/app/provider_workers/financial_provider_worker.py']' timed out after 20.0 seconds"}`
- 影响：需要 uncached BaoStock 的请求可能等待 20 秒后降级；本轮 profile/cache 与 annual history 仍可用。
- 最小修复：先建立 worker/provider latency 日志并复现，不先放大全局 timeout。

### P1.3-P1-004 — request ID 无法关联 Provider/缓存日志

- 分类：`UNKNOWN`
- 证据：API 返回六个 x-request-id，但近 30 分钟日志按 ID/Provider/cache 查询为空。
- 影响：无法证明 Tushare `stock_basic/daily/daily_basic/fina_indicator` 的本轮 live/cache 调用次数、成功率与延迟。
- 最小修复：补充脱敏 structured access/provider/cache telemetry。

### P1.3-P1-005 — 公网 `/health` 是 SPA 假阳性

- 分类：`API_CONTRACT`
- 实际：公网 `/health` HTTP 200 HTML；`/api/v1/health` 与 server-local `/health` 才是 JSON health。
- 最小修复：固定公开健康路径并让监控断言 JSON body/content-type。

### P1.3-P2-001 — profile 来源字段语义不够单一

- 分类：`API_CONTRACT`
- 实际：top-level `source=baostock`，同时 `profile_source=cninfo_company_profile`；数据正确且 `source_metadata` 保留双来源。
- 最小修复：明确 source precedence，不能为简化而丢失 provenance。

## 5. Chat 与 UI

以下五条必须在新对话中验证，但因没有浏览器/登录测试面且本轮禁止数据库写入，全部 `NOT_TESTED`：

1. 贵州茅台近期情况
2. 600519 财务指标、ROE、估值
3. CN/000725 公司资料 + EOD
4. 新能源行业最近有什么重要新闻？
5. AI 半导体设备主题问题

因此，本轮不能证明 request-local numeric evidence、exact Q3 routing、主题 fail-closed、LLM/Provider 调用数，以及 `partial/unavailable` UI 是否错误显示完成勾选。既有部署 artifact 或本地 fixture 没有被当作本轮线上证据。

## 6. 数据源矩阵

| 数据源/能力 | 状态 | 证据与边界 |
|---|---|---|
| Supabase PostgreSQL | AVAILABLE | health ok；目标 host 指纹 `2b73921d4030`，未输出 URL |
| Redis | AVAILABLE | PONG；db0 32 keys，全部有 expiry；未读取 value |
| Tushare EOD | AVAILABLE | 裸码 000725/600519 fulfilled，as_of 2026-09-09；本轮无法区分 live/cache 或统计 endpoint latency |
| CNINFO company profile | AVAILABLE | 两家公司非空、fresh、as_of 2026-09-10 |
| CNINFO reports | DEGRADED | 302 条 annual：245 pending、51 discovered、5 indexed、1 verified；数据更新时间不统一 |
| Company report RAG data | DEGRADED | 6 active indexed documents、1721 chunks，最近 index 2026-08-12 |
| Report RAG runtime | UNAVAILABLE | deep health: `report_rag=false`、embedding provider=`mock` |
| BaoStock | DEGRADED | annual available；quarterly unavailable；一次 20 秒 timeout |
| AKShare | UNAPPROVED | deep health 显示 library/provider available，不等于获准生产使用；本轮未调用 |
| Eastmoney/Sina/Tencent | UNAPPROVED | 未发现获批证据，本轮未调用 |
| 行业/主题新闻 | UNAPPROVED | 数据库没有 news/event 领域表；Chat fail-closed 因浏览器阻断未复验 |

数据库规模证据：`stock_master=5196`、`analysis_reports=22`、`report_documents=302`、旧 `report_chunks=0`、Company RAG documents=`6`、Company RAG chunks=`1721`、provider_error_log=`0`。`provider_error_log=0` 不能解释为零错误，因为运行日志已经出现 BaoStock timeout，说明该表不覆盖全部在线失败路径。

## 7. 首个 P0 与最小修复顺序

第一修复项是 `P1.3-P0-001`：让公网 `/api/v2` 稳定反代 backend，并加 JSON content-type/body smoke。否则公司页数据即使在 backend 存在，也无法形成真实用户可用体验。

之后修复 `P1.3-P0-002` 的 symbol canonicalization。两个 P0 修复后，必须在可用浏览器和指定测试账号下重新新建五个会话，保存页面截图、Network/request ID、console，并关联服务器日志，才能把本轮从 `HOLD_WITH_EVIDENCE` 提升为完整 production inventory。

## 8. 操作边界

本轮没有修改业务代码、push、部署、重启容器、Docker build、migration、全量抓取、缓存清理或扩流。服务器仅执行 HTTP/health、container inspect/log、Redis INFO/PING 和 Supabase read-only transaction 查询。
