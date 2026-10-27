# Beta V1 E0 Capability Matrix

Audit ID: `e0_20260915T013926Z`
Observed: `2026-09-15T01:39:26Z`
This is a static, local audit. “开放候选” is not production approval.

| capability_id | 用户场景 | 当前工作区实现状态 (`98c111b…` + dirty files) | 其他候选实现状态 | 历史运行证据 | 输入 / 输出 | 来源、权限与开关 | 失败状态与主要缺口 | 首版建议 | 证据 |
|---|---|---|---|---|---|---|---|---|---|
| company.profile | 查看中文 A 股公司资料 | 已实现公开 `/api/v2/company/{market}/{symbol}/profile`，异常返回受控空结果 | `c197e19…`、`9d05b07…` 保留；包含后续路由/展示修复 | `phase7e_p1_3` 曾记录 000725、600519 server-local 非空；非本轮复验 | market/symbol → profile、source、as-of | CN；匿名允许；CNINFO/Tushare 已审阅范围 | 当前工作树 Nginx 不代理 `/api/v2`; 浏览器未运行 | 开放候选，但必须基于已修 proxy 的发布链并浏览验收 | `backend/app/routers/company_v2_debug.py:1445`; `frontend/src/api/companyV2.js:228`; `backend/docs/artifacts/phase7e_p1_3_production_bug_inventory.md` |
| company.eod | 查询盘后收盘价、估值 | 已实现公开 EOD Gateway 投影，明确非实时 | 候选含真实数值对齐、显式证券路由与单位展示 | P1.10 fixture：3 场景 valid；P1.3 历史线上 API 有 000725/600519 EOD | 明确证券 → fulfillment、modules、source、as_of | Tushare EOD；不允许新闻 fallback；匿名接口 | 当前 HEAD 不含 `1ec336d/dbf2073` 的路由及显示修复；本轮未运行 | 仅在合并后续已审候选并新 smoke 后开放 | `backend/app/routers/company_v2_debug.py:1470`; `backend/docs/artifacts/phase7e_p1_10_eod_display_pure_image.json`; commits `1ec336d`, `dbf2073` |
| company.financial_metrics | 查询 PE/PB/ROE/已披露指标 | 基础结构化模块存在 | 候选包含 request-local numeric evidence 与确定性显示格式 | P1.10 fixture 记录 valid=true、unsupported=[]；非 live | 个股问题 → EOD/财务事实、报告期、证据 | Tushare `daily_basic/fina_indicator` 已批准 EOD 范围 | 配置启用不等于当前数据可用；本轮未执行 Provider | 受限开放：只承诺已披露且可验证字段 | `backend/app/services/stock_eod_numeric_validation.py`; `backend/tests/fundamental/test_phase7d_p0_6_stock_eod_numeric_validation.py`; candidate `dbf2073…` |
| company.history.annual | 查看年度历史指标 | 公开 allowlist 与模块隔离已实现 | 后续候选未放宽 allowlist | P0.12 历史 smoke：000725 annual 6/6 modules；非本轮复验 | period=annual → allowlisted modules/history | 匿名；受控字段/文案 | 数据覆盖随 symbol 变化；不得承诺全市场完整 | 开放候选，明确空数据与 as-of | `backend/app/routers/company_v2_debug.py:1343`; `backend/tests/fundamental/test_phase7d_p0_1_public_company_history.py` |
| company.history.quarterly | 查看季度历史指标 | 路由存在，默认 quarterly | 同上 | P1.3 历史证据：000725 quarterly `DATA_NOT_AVAILABLE` | period=quarterly/all → history envelope | 同年度接口 | 已有数据缺口；没有本轮复现 | 受限展示，不承诺可用 | 同上；`phase7e_p1_3_production_bug_inventory.md` |
| entity.switching | 连续对话中从 600519 切到 CN/000725 | 当前 HEAD 有早期实体解析，但不含完整后续修复 | `c197e19…`/`9d05b07…` 包含 `1ec336d` 显式输入优先与跨轮隔离 | 候选 fixture/测试历史；上线后 live smoke 不属于本轮 | 当前消息/页面/会话 → canonical symbol | 当前输入应优先；已认证 Chat | 当前工作树版本较旧；本轮不运行路由测试 | 仅在后续候选复核后开放 | `backend/app/services/security_entity_resolver.py`; commit `1ec336d`; `backend/tests/test_phase7e_p1_6_explicit_symbol_routing.py`（候选） |
| report.discovery | 查找官方财报标题/元数据 | 路由、CNINFO discovery 与持久化模型存在 | 候选继承 | 历史 P1.3：302 annual，状态分布不完整；不是“完成分析” | symbol/year/type → report metadata | CNINFO；部分写操作需登录/管理员 | 找到标题不等于 PDF 可用、已解析或已索引 | 受限展示 | `backend/app/routers/report_discovery.py`; `backend/app/routers/company_v2_debug.py:692`; P1.3 artifact |
| report.interpretation | 针对指定财报追问并引用 | PDF、parse、RAG、report-chat 代码存在 | 候选继承；Phase 8 不改善 RAG | 历史 P1.3：runtime `report_rag=false`, provider mock；6 documents/1721 chunks；本轮未核验文件 | report ID + question → answer/citations/validation | 登录；CNINFO/RAG；开关 `enable_report_pdf/report_rag` 默认 false | 最新索引不等于最新披露；“6 个文件引用缺失”仅是未定位原报告的待核实线索 | 保持关闭 | `backend/app/routers/report_rag.py`; `backend/app/routers/report_chat.py`; `backend/app/core/config.py:223-224`; P1.3 artifact |
| industry.theme | 问新能源或 AI 半导体设备行业新闻 | fail-closed 规则在后续发布链中存在 | `c197e19…`/`9d05b07…` 继承 `4434fc6` | 历史 fixture：`NO_APPROVED_INDUSTRY_NEWS_SOURCE`; 本轮未运行 | 主题问题 → unavailable/reason_code | 无批准行业新闻源；LLM/未批准 Provider 应为 0 | 当前前端 mock fallback 可伪造行业新闻，破坏 fail-closed 用户体验 | 保持关闭，先移除 mock fallback | `backend/app/agents/chat_orchestrator.py`; commit `4434fc6`; `frontend/src/mocks/chatMock.js` |
| general.qa | 通用金融问题 | 通用 skill/LLM 路径存在 | 候选继承 | 无本轮运行证据 | 自然语言 → answer/tools/cards | 登录；LLM 配置与网络依赖 | 来源边界与失败语义不统一；mock fallback 可生成硬编码答案 | 保持关闭或仅内部受控 | `backend/app/agents/chat_orchestrator.py`; `frontend/src/views/ChatCopilotView.vue:630` |
| chat.sessions | 创建、搜索、恢复研究会话 | 已实现 DB 持久化、所有权检查、消息历史和 memory | 候选加入 persistent action 状态恢复但不改变基础会话 | 多个历史测试文件存在；本轮 NOT_TESTED | session/message → stored messages/status | JWT；session 以 user_id 查询，跨用户 404 | `client_request_id` 不在当前 `ChatMessageSendRequest`; SSE 断线后 run 恢复语义分散 | 开放候选，E1 需统一 HTTP/SSE/history terminal contract | `backend/app/routers/chat.py`; `backend/app/models/chat.py`; `frontend/src/api/chat.js` |
| watchlist.read | 查看个人自选 | 已有 REST API、页面和用户过滤 | 候选继承 | 历史测试存在；本轮未运行 | list/enriched → items/total | JWT user_id；现有 watchlist_items | 静态存在不证明生产权限/RLS；需邀请账号浏览验收 | 开放候选（仅原有 REST） | `backend/app/routers/watchlist.py`; `frontend/src/views/WatchlistView.vue` |
| chat.watchlist.write | Chat 提议、确认加入及撤销 | 当前 HEAD 仅旧 confirmation，可直接执行工具；无持久化动作账本 | `c197e19…` 有持久化账本；`9d05b07…` 加独立连接及白名单，默认关闭 | Phase 8K 隔离测试：56 related backend / 794 frontend；非生产 | message → opaque plan/receipt/undo | 必须登录、session ownership、global flag + allowlist + dedicated DB | 生产历史报告：三账本表不存在、角色过宽；需要 `s7/t8` migration 与独立权限审批 | 保持关闭 | candidate routers/models/migrations; `/private/tmp/phase8k_safe_enablement/...phase8k_production_safe_enablement.md` |
| alerts | 创建价格/事件提醒 | 未找到明确 beta API、模型或页面闭环 | 两候选未新增 | 无 | 不存在 | 无 | 能力不存在 | 保持关闭 | 当前 `backend/app/routers`, `frontend/src/api` 静态清单 |
| portfolio | 管理组合/持仓 | 未找到明确 beta API、模型或页面闭环 | 两候选未新增 | 无 | 不存在 | 无 | 能力不存在；不得与 watchlist 混同 | 保持关闭 | 同上 |

## First invitation promise

可作为后续发布审阅候选：中文 A 股公司资料、盘后 EOD、估值及有报告期的已披露财务指标、年度历史、已认证研究会话与已有报告记录。所有数据必须显示 source/as-of/非实时边界并允许 partial/unavailable。

首版不承诺：完整财报解读、季度覆盖、行业新闻、实时行情、通用开放问答、Chat 写入自选、提醒或组合管理。

## E1 minimum change recommendation

E1 应从 Owner 明确选择的干净后续候选建立隔离工作树，不能使用当前六项 tracked 修改作为输入。

| 文件 | 最小修改理由 | 可复用实现 |
|---|---|---|
| `frontend/src/views/ChatCopilotView.vue` | 删除生产 session/API 失败后 `_sendMock` 路径，改为真实失败与重试状态 | 现有 timeout、session guard、`researchFulfillment` 映射 |
| `frontend/src/mocks/chatMock.js` | 从生产页面依赖中移除；文件可保留给显式测试注入 | 既有 fixture 思路，不进入 production bundle/runtime |
| `backend/app/models/chat.py` | 增加兼容的公共结果字段或 DTO；明确 execution status 与 fulfillment 分离 | 当前 `ChatMessageSendResponse` 与 stored metadata |
| `backend/app/routers/chat.py` | 同步 HTTP 使用统一结果投影并返回 request correlation | 现有 ownership、error handler、orchestrator metadata |
| `backend/app/agents/chat_streaming.py` | SSE terminal event 与同步结果使用同一投影 | 现有 `sequence`、terminal event、keepalive |
| `frontend/src/utils/researchFulfillment.js` | 作为 UI 真实状态唯一映射，补齐统一契约兼容 | 已有 fulfilled/partial/unavailable/failed 定义 |
| `frontend/src/utils/chatEventNormalizer.js` 与 `chatReducer.js` | 统一 SSE、HTTP fallback、历史恢复语义 | 已有 normalizer/reducer 架构 |
| `frontend/src/api/chat.js` | 传递/接收 request correlation；是否加入 client_request_id 先由复现决定 | 现有 SSE universal event passthrough |

必须先复现：SSE 已产生持久化结果后连接断开并进入同步 fallback、相同用户消息重复提交、切换 session/账号期间旧响应返回。只有复现证明需要持久化幂等时，才设计 `client_request_id` 唯一约束。

Migration 结论：移除 mock 与统一兼容响应本身不需要 migration；`client_request_id` 的持久化/唯一性是否需要 migration 为 **UNKNOWN**，取决于上述复现和能否安全复用 `chat_messages.msg_metadata`。Phase 8 的 `s7/t8` migration 不属于 E1。

E1 最小测试矩阵：session 创建失败、SSE 连接前失败、SSE terminal 后断线、sync fallback、partial/unavailable 历史恢复、request ID 一致性、切换 session/账号旧响应隔离、行业主题 fail-closed、EOD fulfilled 对照。所有 Provider/LLM 使用 fixture/mock boundary，不调用 live 服务。
