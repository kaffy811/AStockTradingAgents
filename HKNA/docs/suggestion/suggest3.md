# HKNA 产品验收报告 3

## 1. 本次验收范围

验收 Phase 6W-R3.2D 的运行镜像完整性、Company V2 fresh RAG 实际调用路径与 30 条观察结果。

## 2. 已确认完成

- D3 引用元数据泄漏修复已作为独立 commit `9c65027` 固化。
- Company V2 10/10 fresh 请求均选择 2024 年报告，检索均完成且无 retrieval timeout。
- 实际检索路径为 `indexed_db_lexical / indexed_report_db`；本轮未调用 local 或 Mock embedding provider。

## 3. 关键修正

“sentence-transformers 缺失导致 Company V2 fresh RAG 超时”的假设，已被本轮实际调用链否定。该链路不依赖 embedding provider，故现有 Dockerfile、embedding provider、pyproject、uv.lock 改动不得以此理由提交。

## 4. 当前风险

- backend 运行镜像含未提交 dependency 与 warmup 改动，不能代表 commit `9c65027` 的可发布镜像。
- 30 条观察中 14 条 numeric validation invalid、22 条 partial_success，属于 P1 数据可信度问题。
- 未发现 report year 错配，且 RAG retrieval timeout 为 0；当前主阻塞已从检索性能转为数字失败归因和镜像可追溯性。

## 5. 当前产品阶段判断

系统具备真实年报选择、检索和基础回答能力，但尚未达到可扩展流量的金融事实稳定性门槛。

## 6. 下一步任务

P0：对 14 条 numeric invalid 逐条进行 S0–S8 归因，建立“token → 首次出现阶段 → 证据覆盖 → 用户可见性 → 根因类别”矩阵。禁止在取证前放宽 numeric validator。

P1：单独建立 release provenance 计划，隔离验证纯 `9c65027` 镜像；不得将 dirty image 的性能结果用作扩流依据。

P2：仅在 P0 归因后，为已证实根因创建最小修复任务。

## 7. 发布建议

维持：`HOLD_1_PERCENT`。

不得提交既有 dependency/warmup 改动、不得扩至 10%、不得将 14 条 numeric failures 归为可接受性能波动。
