# Approved AI Chat Slice Local Merge Record

## 合并结果

- Target branch: `release/demo-staging`
- Pre-merge HEAD: `386e27fb35e1ea8ffb7b08a572c768b2ba9b6593`
- Approved candidate: `54339d556c21985a15f5aed8040e65fc7690dd4c`
- Merge commit: `5dad7228bb7b54338a946b49daeee5eae58348f9`
- Merge strategy: local non-fast-forward merge using `ort`
- Merge subject: `merge(release): integrate approved AI chat trust slice`
- Push/deploy/migration/traffic expansion: not performed

Fast-forward 不可用：合并前 `release/demo-staging` 的 `386e27f` 与候选 `54339d5` 是从 `e898547` 分叉的等价 replay 链。Owner 已授权 fast-forward/merge，因此使用本地 `--no-ff` merge 保留候选父链。

## HEAD 与 Git tree 核验

```text
HEAD=5dad7228bb7b54338a946b49daeee5eae58348f9
tree=0981783304376eed46a6a3276950aa95511f3b69
parent[0]=386e27fb35e1ea8ffb7b08a572c768b2ba9b6593
parent[1]=54339d556c21985a15f5aed8040e65fc7690dd4c
```

`git diff 54339d556c21985a15f5aed8040e65fc7690dd4c..HEAD` 无输出，证明合并后 HEAD tree 与获批候选 tree 完全一致。

## 候选文件范围

Baseline `e8985471d62ce74e5cd99b61b9eadf27a13878ce` 到合并后 HEAD 的增量为 21 个文件：

```text
HKNA/update_report/update_128.md
HKNA/update_report/update_129.md
HKNA/update_report/update_130.md
HKNA/update_report/update_131.md
backend/app/agents/chat_orchestrator.py
backend/app/services/official_company_event_service.py
backend/docs/artifacts/phase7c1_1_cninfo_candidate_runtime.json
backend/docs/artifacts/phase7c1_1_cninfo_commit_isolation.md
backend/docs/artifacts/phase7c1_cninfo_event_runtime_trace.json
backend/docs/artifacts/phase7c1_cninfo_official_event_research.md
backend/docs/artifacts/phase7c2_chat_status_ui_audit.md
backend/docs/artifacts/phase7c2_chat_status_ui_runtime.md
backend/docs/artifacts/phase7c3_approved_chat_slice_integration.md
backend/docs/artifacts/phase7c3_approved_chat_slice_runtime.json
backend/tests/test_phase7c1_cninfo_official_event_research.py
frontend/src/components/chat/ChatMessageList.vue
frontend/src/components/chat/ChatResearchStatusCard.vue
frontend/src/components/chat/ChatThinkingMiniPanel.vue
frontend/src/tests/researchFulfillment.test.js
frontend/src/utils/researchFulfillment.js
frontend/src/views/ChatCopilotView.vue
```

范围仅包含 CNINFO official event/report research、Chat Research 四种真实状态 UI、相关测试与文档。未包含 Tushare Gateway、Token/配置、公开抓取 Provider、Docker、依赖/lockfile、migration、Company V2 或历史脏改。

## 工作区核验

合并前暂存区为空。合并后暂存区仍为空。下列既有 tracked 脏改保持未暂存，不在 merge commit 中：

```text
backend/Dockerfile
backend/app/main.py
backend/app/services/report_embedding_provider.py
backend/pyproject.toml
backend/uv.lock
```

其它既有未跟踪文件也保持未跟踪。本记录和 `update_134.md` 是合并后新生成的本地取证，未提交。

## 部署前强制复验项

`BLOCKING_PRE_DEPLOY_TEST_INFRA_RECHECK`

前端完整套件上次并行运行时，615 项断言通过，12 个 Vitest worker 在启动前超时。该次不计为完整套件通过。任何部署授权前必须：

1. 在资源稳定的隔离环境中重跑完整前端套件。
2. 限制 worker 并发或调整测试基础设施，确保零 worker 启动超时。
3. 记录完整通过的测试数、运行时间、worker 配置与环境资源。
4. 未完成上述复验时，不得部署或扩流。
