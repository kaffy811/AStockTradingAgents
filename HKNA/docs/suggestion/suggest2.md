# HKNA 产品验收报告 2

## 1. 本次验收范围

验收 Phase 6W-R3.2C.1 的 D3（报告 RAG 引用元数据泄漏）修复、隔离提交和运行时证据。

## 2. 已确认完成

- D3 修复已提交：`9c65027 fix(report-rag): contain citation metadata leakage`。
- 模型只接收请求局部的 `E1..En` 证据标签；数据库 `chunk_id` 由后端解析。
- Q1、Q2、Q4 三条串行运行时请求均完成，答案未泄漏内部 chunk ID，数值校验通过。
- 127 项相关回归测试通过。

## 3. 产品与数据验收

财报分析结果不再把内部证据定位编号暴露给用户，避免将非财务元数据误判成无证据数字并降级为 `partial_success`。这提升的是结论可读性与引用安全性，不改变财务事实、检索策略或数字校验规则。

## 4. 当前产品阶段

处于 1% Canary 的正确性修复后观察阶段。D3 已关闭，但尚未具备扩大流量条件。

## 5. 未关闭风险

- `backend/app/main.py` 的连接池预热仍缺少必要性 A/B 证据，必须与 D3 提交保持隔离。
- Dockerfile、embedding provider、`pyproject.toml`、`uv.lock` 仍是既有未提交改动，不能被视为已验证发布内容。
- R3.1 所称「sentence-transformers 缺失导致 fresh RAG timeout」需要重新建立实际调用路径、镜像与性能因果证据；不得据此直接提交 dependency 改动。

## 6. 下一步建议

P0：开展只读的 release-integrity 与 RAG-causality re-baseline：确认 1% 运行镜像 digest、运行时代码 SHA、真实 retrieval path、cache hit/miss 与 fresh retrieval latency。

P1：在不改代码、不调超时、不扩大流量的前提下，按原 R3.1 方法重新采集 fresh/uncached RAG 样本，区分 lexical fast path、local embedding 路径与 Mock provider 实际使用。

P2：仅在因果链被实证后，另立受控修复任务处理 dependency 或运行镜像问题。

## 7. 发布建议

维持：`HOLD_1_PERCENT`。

不得 push、部署、扩大流量，直至运行镜像与 fresh RAG 的 P1 根因得到独立验证。
