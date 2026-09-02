# Phase 7C1.1 — CNINFO Official Event Research Commit Isolation

## 1. 结论

本地提交候选满足最小白名单边界，可创建独立 commit。最终门禁状态：`CNINFO_OFFICIAL_EVENT_COMMIT_READY`。

未 push、merge、部署、执行 migration 或扩流。

## 2. 提交前完整工作树差异

`git diff --name-only` 在隔离前仅报告以下已跟踪文件：

```text
backend/Dockerfile
backend/app/agents/chat_orchestrator.py
backend/app/main.py
backend/app/services/report_embedding_provider.py
backend/pyproject.toml
backend/uv.lock
```

`git diff --stat`：

```text
backend/Dockerfile                                |  13 +
backend/app/agents/chat_orchestrator.py           | 173 ++++++
backend/app/main.py                               |  17 +
backend/app/services/report_embedding_provider.py |   5 +-
backend/pyproject.toml                            |   1 +
backend/uv.lock                                   | 633 +++++++++++++++++++++-
6 files changed, 837 insertions(+), 5 deletions(-)
```

说明：Git 的普通 `diff` 不显示未跟踪文件；完整 `git status --short` 同时显示大量历史未跟踪 artifact/报告。除下述白名单文件外，所有历史修改和未跟踪文件均保持未暂存，不进入本 commit。

## 3. 拟提交白名单及直接关系

| 文件 | 与 CNINFO 官方事件能力的直接关系 |
|---|---|
| `backend/app/services/official_company_event_service.py` | 只读官方事件投影、CNINFO URL 白名单、九类事件分类、公开字段契约 |
| `backend/app/agents/chat_orchestrator.py` | `official_company_events` / `official_report_analysis` 优先路由和未批准新闻 fail-closed |
| `backend/tests/test_phase7c1_cninfo_official_event_research.py` | fulfilled/partial/unavailable、字段、分类、零工具调用和类型真实性验收 |
| `backend/docs/artifacts/phase7c1_cninfo_official_event_research.md` | 7C1 设计、边界与回归记录 |
| `backend/docs/artifacts/phase7c1_cninfo_event_runtime_trace.json` | 7C1 隔离测试运行契约 |
| `HKNA/update_report/update_128.md` | 7C1 代码更新报告 |
| `backend/docs/artifacts/phase7c1_1_cninfo_commit_isolation.md` | 本次 commit 边界、文件关系和门禁证据 |
| `backend/docs/artifacts/phase7c1_1_cninfo_candidate_runtime.json` | 配置数据库只读 Candidate 的脱敏结果 |
| `HKNA/update_report/update_129.md` | 7C1.1 隔离与提交报告 |

## 4. 明确排除

以下现有工作树差异未暂存、未提交：Dockerfile、应用启动文件、embedding provider、依赖清单/锁文件，以及所有 Company V2、Phase 7C0、历史 suggestion/update/artifact 和 memory 脏改。

本提交没有改动 Tushare Gateway/Token/配置、新闻抓取源、frontend、migration、LLM Prompt、Report RAG、numeric validation 或 citation validation。

## 5. 真实性修正

首次只读预验收发现：指定“分红/回购/股东变动/风险”时，旧候选会返回无关年度报告并标记 fulfilled；“财报重点”在只展示元数据时也标记 fulfilled。提交前已最小修正：

- 根据用户明确指定的事件类型过滤持久化事件；无匹配时返回 `NO_MATCHING_PERSISTED_CNINFO_EVENTS`，不以无关报告替代。
- `official_report_analysis` 未实际渲染 RAG 正文证据时返回真实 `partial` + `REPORT_RAG_EVIDENCE_NOT_RENDERED`。
- 新增专项测试防止回归。

## 6. 自动化验证

同一组合命令运行 Phase 7C1、Report RAG、citation、numeric 与 Chat/Report 路由测试：

```text
113 passed, 16 warnings
```

原有 112 项相关回归全部通过，新增 1 项“指定事件类型不得用无关报告替代”测试通过。Warnings 为既有 datetime deprecation 与 AsyncMock runtime warnings，无测试失败。

## 7. 配置数据库只读 Candidate

最终 Candidate 在修正后执行；四个问题各一次，无应用级重试。未触发 live discovery 或未批准 Provider。

| 问题 | route | fulfillment | reason_code | 结果摘要 |
|---|---|---|---|---|
| 贵州茅台最近有什么官方公告？ | official_company_events | fulfilled | — | 4 项持久化 CNINFO 报告事件；字段契约完整 |
| 贵州茅台最近一期财报披露了什么重点？ | official_report_analysis | partial | REPORT_RAG_EVIDENCE_NOT_RENDERED | 元数据可核验；正文重点未在确定性路径渲染，真实降级 |
| 贵州茅台近期是否有分红、回购、股东变动或风险公告？ | official_company_events | unavailable | NO_MATCHING_PERSISTED_CNINFO_EVENTS | 无匹配持久化事件，不用年度报告替代 |
| 新能源汽车行业最近有什么重要新闻？ | industry_news | unavailable | NO_APPROVED_INDUSTRY_NEWS_SOURCE | 0 工具调用 |

可见事件均含 CNINFO 来源、官方 URL、披露时间、事件类型和 as_of。脱敏运行证据见 `phase7c1_1_cninfo_candidate_runtime.json`。

## 8. 泄漏检查

对白名单代码、测试与 artifact 执行静态检查，并核对 Candidate 输出：

- 无 Token、Cookie、数据库连接串。
- 用户可见回答和 artifact 无数据库 ID、内部存储名称、原始 chunk ID。
- 官方 source URL 中的 CNINFO 公告公开标识属于必要官方链接，不是数据库 ID。
- 未批准来源没有作为事实进入回答或 artifact；仅门禁说明和零调用验证提及其类别。

## 9. 最终提交门禁

提交前必须再次验证：

- `git diff --check` 与 `git diff --cached --check` 通过；
- staged 文件与第 3 节白名单完全一致；
- staged 之外不存在本阶段遗漏；
- 本地 commit message 为 `feat(research-copilot): add CNINFO official event research`。
