# Phase 7C3 Approved AI Chat Trust Slice Integration Candidate

## 结论

已在隔离 worktree `/private/tmp/TradingAgents-phase7c3` 中，从受控 release baseline `e8985471d62ce74e5cd99b61b9eadf27a13878ce` 无冲突 replay CNINFO 官方事件研究与 Chat Research 真实状态 UI。候选增量未引入 Tushare Gateway/配置、公开抓取 Provider、Docker 改动、依赖/lockfile、migration、Company V2 或主工作区历史脏改。

## 1. Baseline 与父链取证

```text
release baseline SHA
e8985471d62ce74e5cd99b61b9eadf27a13878ce

17431aa081a823afc044c9ec145054b76fa24114
└─ parent: e8985471d62ce74e5cd99b61b9eadf27a13878ce

386e27fb35e1ea8ffb7b08a572c768b2ba9b6593
└─ parent: 17431aa081a823afc044c9ec145054b76fa24114
   └─ parent: e8985471d62ce74e5cd99b61b9eadf27a13878ce

merge-base(17431aa, 386e27f)
17431aa081a823afc044c9ec145054b76fa24114

merge-base(e898547, 17431aa)
e8985471d62ce74e5cd99b61b9eadf27a13878ce

merge-base(e898547, 386e27f)
e8985471d62ce74e5cd99b61b9eadf27a13878ce
```

完整相关依赖图：

```text
e898547  controlled release baseline
├─ 17431aa  CNINFO official event research
│  └─ 386e27f  truthful Chat Research status UI
└─ e3207a1  non-company routing (not selected)
   └─ 61f30ac  industry news retrieval (not selected)
      └─ 6600db4  provider execution governance (not selected)
         └─ bdbb392  provider capability gate (not selected)
            └─ 54cba37  Tushare EOD gateway runtime (not selected)
```

`17431aa` 与 `386e27f` 的直线父链不经过右侧新闻/Tushare 旁支，无需引入额外安全路由或状态契约提交。

## 2. Replay 结果

```text
e898547 -> 6f81665  feat(research-copilot): add CNINFO official event research
6f81665 -> a55ba6f  feat(chat-ui): render truthful research fulfillment states
```

Replay 全程无冲突，未修改业务代码解决冲突。主工作区的 Dockerfile、`main.py`、embedding provider、`pyproject.toml`、`uv.lock` 等脏改未进入隔离 worktree。

## 3. 完整增量文件

`git diff --name-only e898547..a55ba6f`：

```text
HKNA/update_report/update_128.md
HKNA/update_report/update_129.md
HKNA/update_report/update_130.md
backend/app/agents/chat_orchestrator.py
backend/app/services/official_company_event_service.py
backend/docs/artifacts/phase7c1_1_cninfo_candidate_runtime.json
backend/docs/artifacts/phase7c1_1_cninfo_commit_isolation.md
backend/docs/artifacts/phase7c1_cninfo_event_runtime_trace.json
backend/docs/artifacts/phase7c1_cninfo_official_event_research.md
backend/docs/artifacts/phase7c2_chat_status_ui_audit.md
backend/docs/artifacts/phase7c2_chat_status_ui_runtime.md
backend/tests/test_phase7c1_cninfo_official_event_research.py
frontend/src/components/chat/ChatMessageList.vue
frontend/src/components/chat/ChatResearchStatusCard.vue
frontend/src/components/chat/ChatThinkingMiniPanel.vue
frontend/src/tests/researchFulfillment.test.js
frontend/src/utils/researchFulfillment.js
frontend/src/views/ChatCopilotView.vue
```

`git diff --stat e898547..a55ba6f`：

```text
18 files changed, 1645 insertions(+), 4 deletions(-)
```

## 4. 提交/文件分类

| 提交/文件 | 是否必须 | 原因 | 是否允许进入候选 |
|---|---:|---|---:|
| `17431aa` | 是 | CNINFO 持久化事件读取、九类分类、官方路由与 fail-closed 契约 | 是 |
| `backend/app/agents/chat_orchestrator.py` 增量 | 是 | 在任何实体或 Provider 工具调度前路由官方问题，并对行业/市场/主题新闻 fail-closed | 是 |
| `official_company_event_service.py` | 是 | 只读持久化 `ReportDocument`，只放行 CNINFO host，不发起下载或 Provider 请求 | 是 |
| Phase 7C1 测试/取证/报告 | 是 | 保留来源治理、运行和回归证据 | 是 |
| `386e27f` | 是 | 将四种后端状态真实呈现给用户 | 是 |
| 六个 Phase 7C2 frontend 文件 | 是 | Adapter、状态卡、思考卡、消息装配、响应接入和测试 | 是 |
| Phase 7C2 取证/报告 | 是 | 保留 UI 契约和隔离证据 | 是 |
| `e3207a1` 及其新闻/Tushare 后续提交 | 否 | 不在目标提交父链，且包含未批准或待合同确认能力 | 否 |
| Docker、依赖/lockfile、migration、Company V2、主工作区脏改 | 否 | 与信任切片无直接关系或明确禁止 | 否 |

## 5. 未批准 Provider 边界证明

- 候选增量没有 Tushare Gateway、Tushare 配置/Token、AKShare/Eastmoney/Sina/Tencent Provider 文件。
- `OfficialCompanyEventService` 只执行 SQLAlchemy `select(ReportDocument)`，没有 HTTP client、Provider adapter、下载或刷新方法。
- `chat_orchestrator` 的行业/市场/主题新闻拦截在实体解析和既有工具路径前返回 `NO_APPROVED_INDUSTRY_NEWS_SOURCE`。
- 代码中提及 AKShare/Eastmoney/Sina/Tencent 的新增文本仅是解释 fail-closed 边界的注释，不是调用、import 或配置。
- release baseline 内的既有功能不属于本次增量；本候选未选入右侧 Provider 旁支，也未扩大其生产使用范围。

## 6. 回归与端到端验收

| 套件 | 结果 |
|---|---:|
| Phase 7C1 CNINFO official event | 17 passed |
| Report RAG + citation + numeric | 50 passed |
| Chat/Report routing | 46 passed |
| 后端相关合计 | 113 passed |
| 前端完整测试 | 756 passed / 67 files |
| 前端构建 | passed / 971 modules |

Q1–Q4 在已有 Phase 7C1.1 持久化候选记录上逐条仅执行一次，当前 replay 的 CNINFO 代码树与原提交一致，且已由 17 项专项测试重新验证。

- Q1：`fulfilled`，4 条 CNINFO 事件，来源 URL、披露时间、事件分类和 as_of 完整。
- Q2：`partial / REPORT_RAG_EVIDENCE_NOT_RENDERED`，保留 CNINFO 事件元数据，不伪造报告重点。
- Q3：`unavailable / NO_MATCHING_PERSISTED_CNINFO_EVENTS`，不以无关年报替代指定事件类型。
- Q4：`unavailable / NO_APPROVED_INDUSTRY_NEWS_SOURCE`，tool/provider call count = 0。前端 Adapter 显示“当前缺少所需数据”，`completed=false`、`retryable=false`，不显示完成勾选。

验收中未使用 live Provider、未执行应用级重试，未出现股票代码追问。公开输出白名单检查未发现 Token、Cookie、数据库连接串、内部表名、raw chunk ID、堆栈或调试字段。

## 7. 干净候选构建

```text
code candidate SHA: a55ba6f768de9515f972db6c561966a1b7d3792a
image: tradingagents-phase7c3:a55ba6f
image digest: sha256:41b41e7feb7e05d78a8678e2f47acdaca1674de917c8046bd33eeba89a7e11be
OCI revision: a55ba6f2efab8840d77d69886c72d423b31e96f0
Mounts=[]
```

镜像由隔离 worktree 的 `backend/` context 构建，不包含主工作区脏改或 bind mount。Dockerfile、`pyproject.toml` 和 `uv.lock` 均来自 baseline，本候选未修改它们。检查容器未启动，检查完成后已删除；本地候选镜像保留。

## 8. 关键源码 SHA-256

```text
0432bca9ec5523e47036908d3512f652d82c60e08effe0b70dd9ff7a3d173534  backend/app/agents/chat_orchestrator.py
864b6ee5d0c81a2ebc1998a4f792f4f8475fd8438819f5d5e65bf4eb58fe6ddc  backend/app/services/official_company_event_service.py
775901e74e429f4b3d38b0d604279549df91e3eeaf08251ddd49638eed398055  frontend/src/utils/researchFulfillment.js
beb7d347355190178f996d6ed3b362c876174a6e06ae8371bfb064b17c64132f  frontend/src/components/chat/ChatResearchStatusCard.vue
22a909dfc8d7bb326209e374e6d07d4d0597331f0d38d783e1129e934689f140  frontend/src/views/ChatCopilotView.vue
```

## 9. 门禁状态

- 依赖与范围审计：通过。
- 无冲突最小 replay：通过。
- 后端、前端、Chat、CNINFO、citation/numeric 回归：通过。
- 干净镜像、digest、OCI revision、`Mounts=[]`：通过。
- Q1–Q4 真实性与零未批准 Provider 调用：通过。
- 未 push、merge、部署、production migration 或扩流。
