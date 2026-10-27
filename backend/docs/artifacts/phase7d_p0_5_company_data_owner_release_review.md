# Phase 7D-P0.5 Integrated Company Data Owner Release Review

## 结论

**HOLD_WITH_EVIDENCE**

集成候选的提交重放、范围审计、公开响应收口、相关回归、前端完整门禁、前端 production build、Python compile、JSON validation、secret scan 与 `git diff --check` 均通过。候选暂不能标记为 Owner release approval ready，原因有两项：

1. 本机 Docker daemon 不可连接，无法完成 backend/frontend 纯镜像构建、OCI revision、Mounts、镜像 config/history、镜像内源码 hash 与响应样本检查。
2. Q3 虽返回报告期、来源、as_of、ROE 与估值，但候选运行结果没有数值校验标记或证据（`numeric_validation=null`），不满足“财务指标具备报告期、来源与数值校验”。

## 1. 隔离集成

- release baseline：`5dad7228bb7b54338a946b49daeee5eae58348f9`
- 隔离 worktree：`/private/tmp/tradingagents-phase7d-p0-5-review-20260907`
- 隔离分支：`audit/phase7d-p0.5-rc-review-20260907`
- replay 顺序：`851264f` → `d5cab4a` → `c4a506c`
- integrated candidate：`c812d4d2e572ffd08cfd56b8110c0ba87b0cab05`
- integrated tree：`d821f6804a4a57dace95664e2249024e3d48b717`
- 原末端提交 `c4a506c...` tree：`d821f6804a4a57dace95664e2249024e3d48b717`
- tree 等价检查：通过；三个提交均无冲突 replay。
- 主工作区原有脏改未进入候选；候选在验证开始时干净。

## 2. Baseline → candidate diff 审计

共 18 个文件，`1685 insertions / 19 deletions`。变更仅涉及：Company public history、Tushare EOD gateway、个股 EOD research、相关前端展示、测试、文档与更新记录。

未触碰：Dockerfile、依赖声明、lockfile、migration、`.env`、Token 配置、全局鉴权、RAG、numeric validation、未批准新闻 Provider。

公开边界复核：

- history 行记录与模块均使用正向 allowlist，未知字段默认丢弃。
- history warnings 仅接受本地 code→固定文案映射；Provider message 不透传。
- EOD public DTO 不含 endpoint、provider implementation、raw code/message、request metadata。
- profile exception 返回固定 `PUBLIC_PROFILE_UNAVAILABLE` 文案，不含 `str(exc)`。
- debug/raw 路由仍受既有 feature flag 与 dev/admin 鉴权保护；未新增匿名 debug/raw route。
- EOD 顶层 warning 为本地固定文案。

## 3. 验证结果

| Gate | 结果 | 证据 |
|---|---|---|
| 相关后端回归 | PASS | `106 passed, 1 warning` |
| 完整前端发布门禁 | PASS | `69 files, 764 tests passed`; worker timeout = 0 |
| 前端 production build | PASS | Vite build 完成；仅既有 chunk size warning |
| Python compile | PASS | `compileall -q backend/app backend/tests` |
| JSON validation | PASS | 仓库 JSON 逐文件 `python -m json.tool` |
| secret scan | PASS | candidate diff 未命中 OpenAI key、Bearer credential、Postgres/Mongo credential URI 模式 |
| git diff --check | PASS | 无输出 |
| backend/frontend 纯镜像 | BLOCKED | Docker daemon socket 不可连接 |
| 镜像 provenance/config/history/response | NOT RUN | 依赖成功构建纯镜像，故不能声称通过 |

关键源码 SHA-256：

- `backend/app/routers/company_v2_debug.py`: `2a190ab710e60f8f5284c3d145c1e0e33c3f275d85939fe55acb555da3426017`
- `backend/app/services/tushare_eod_gateway.py`: `7a944ea72938fa27ee0dce01c0c392f1981cbd16453e3c9278ffa8cd1a337e3c`
- `backend/app/agents/chat_orchestrator.py`: `4c4f7eb0a113ff4762637032c35b0211fbb5c39abed1869e6116ec11fa7dd376`
- `backend/app/datasource/tushare_client.py`: `891353fcae05bf00e71020747b79c9941413c70badb7dd88d5af2efa69571923`
- `frontend/src/api/companyV2.js`: `2f7eb53fa3f288fdb0f0ca9da0d416df0bee438839d0391b2b25df7185ea3bec`
- `frontend/src/views/CompanyV2View.vue`: `e8c606fd3fad6d3ab84704612b13cf5183d456357e9cf92285f31cd6be6c47b7`

## 4. Q1–Q4 串行单次执行

所有用例在同一隔离候选 worktree 中逐条串行执行，无重试。

- Q1 — PASS（hermetic fixture）：CN/000725 profile 非空；history/EOD 无 `AUTH_REQUIRED`；公开响应只含 allowlist 字段；模块级失败隔离由相关回归覆盖。
- Q2 — PASS（hermetic fixture）：解析为 `600519`（CN，即 Tushare `600519.SH`）；包含 source 与 as_of；文案明确“最近交易日/EOD、不是实时行情”。
- Q3 — FAIL：解析为 `600519`，有报告期 `2026-06-30`、source、as_of、ROE 与市盈率；但 `numeric_validation=null`，没有数值校验证据。
- Q4 — PASS（fail-closed fixture）：`unavailable / NO_APPROVED_INDUSTRY_NEWS_SOURCE`；在实体与工具调用前返回，Tushare news、AKShare、Eastmoney、Sina、Tencent 调用均为 0。

说明：Q1–Q4 使用受控 fixture 验证候选逻辑，不等同于真实 Provider/数据库生产样本。纯镜像运行验证因 Docker daemon 不可用未执行。

## 5. Owner 决策

当前不得请求合并。解除 HOLD 至少需要：

1. 在可用 Docker daemon 上从 `c812d4d2...` tree 重新构建两镜像，设置 OCI revision 为完整 integrated SHA，确认 Mounts=[]，并完成 config/history/源码 hash/响应 secret 检查。
2. 为 Q3 接入或复用已批准的数值校验结果，并以公开安全字段提供可验证证据；不得借此扩大本候选至未批准的 numeric-validation 改动，需另行审查。
3. 在同一纯镜像环境重新逐条执行 Q1–Q4，保存真实响应与 Provider call counters。

即使技术候选后续转为 READY，公开部署仍等待 Owner 对 Tushare 商业展示、缓存和 AI 摘要使用权的确认。
