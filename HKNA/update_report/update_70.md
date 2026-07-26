---
目前完成的工作汇总：

已完成

1. backend/app/agent_runtime
- 新增 Pi-Compatible 金融 Agent Runtime 原型模块。
- 定义运行请求/结果、事件、工具、模型网关、Manifest、错误码和 metrics sink。
- 实现 bounded agent loop、context transform、tool adapter、tool executor、executor 和 shadow runner。
- 首个 Agent 为 `official_report_pdf_pi_v1`，只读、shadow、deterministic path 优先，不调用 LLM 猜测 PDF URL。

2. backend/docs/artifacts
- 新增 pi-mono 组件清单、MIT license/security review、Python vs Node 采用决策、runtime 架构、agent/tool/event 协议文档。
- 新增 `pi_official_report_pdf_shadow_results.json` 与 `pi_compatible_runtime_gate.json`。
- 当前无真实 shadow 样本，未填写虚假 match rate，Gate 决策为 `do_not_enable_pi_compatible`。

3. backend/app/agents/chat_orchestrator.py 与 backend/app/core/config.py
- 新增 `AGENT_EXECUTOR_MODE`、`PI_AGENT_*` 配置，默认全部关闭。
- 在 legacy orchestrator 中挂接 `pi_compatible_shadow` 旁路执行，仅当 shadow 开关和 agent allowlist 同时满足时运行。
- shadow 失败只记录 debug，不影响 legacy 用户回答、assistant message、context 或业务写入。

4. backend/tests/fundamental/test_phase6v_pi_runtime.py
- 新增 21 个 hermetic tests，覆盖 P0 artifacts、tool allowlist、event/schema、max turns、max tool calls、deadline、cancellation、参数校验、未知/越权工具、tool timeout、顺序/并行、provenance、official_report_pdf deterministic path、shadow comparison 和默认配置。

5. 验证
- `pytest backend/tests/fundamental/test_phase6v_pi_runtime.py -q` 通过。
- `pytest backend/tests/fundamental/test_phase6u_e1_layered_runtime.py backend/tests/fundamental/test_phase6u_e1_1_shadow_gate.py -q` 通过。
- `pytest backend/tests -q` 通过：3311 passed, 16 skipped。
- `npm test` 通过：61 files, 679 tests。
- `npm run build` 通过。

---
下一步：你需要操作

第一步：保持生产环境默认配置：
`AGENT_EXECUTOR_MODE=legacy`
`PI_AGENT_SHADOW_ENABLED=false`

第二步：如需在 staging 采集 shadow 样本，仅设置：
`AGENT_EXECUTOR_MODE=pi_compatible_shadow`
`PI_AGENT_SHADOW_ENABLED=true`
并保留 `PI_AGENT_ALLOWED_AGENTS=official_report_pdf_pi_v1`。

第三步：采集 official_report_pdf 真实 shadow comparison 样本后，更新：
`backend/docs/artifacts/pi_official_report_pdf_shadow_results.json`
`backend/docs/artifacts/pi_compatible_runtime_gate.json`

第四步：只有 Gate 通过后，才评估下一阶段 quote_query；本轮不建议启用 `pi_compatible` 正式路径。
