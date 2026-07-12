---
目前完成的工作汇总：

已完成

1. Phase 6T-C1 AI-assisted verification 后端最小闭环
- 更新 `backend/app/services/company_v2_pdf_evidence_retriever.py`、`backend/app/services/company_v2_ai_verification_guardrail.py`、`backend/app/services/company_v2_ai_official_verification_agent.py`。
- evidence retriever 只返回候选片段，每个字段最多 3 条，每条 excerpt 不超过 1500 字，保留 page，不返回 `local_path`。
- AI verifier 输出结构化 JSON；未配置真实 LLM provider/key 时走 deterministic/mock safe mode，返回 `AI_KEY_MISSING` / `INSUFFICIENT_EVIDENCE` 等结构化结果，不阻塞。
- 新增 `backend/app/services/company_v2_ai_verification_response.py`，统一 ai-verify public payload 脱敏与 structured error 构造。

2. Guardrail 规则补齐
- evidence 缺失时不能保持 `verified`。
- `confidence < 0.75` 会进入 `human_review_queue`，并将 verified 降为 `likely_match`。
- `report_year` / `report_type` mismatch 会阻止 verified。
- 数值差异超过阈值会降级为 `mismatch`。
- 单位数量级疑似错误会输出 `UNIT_SCALE_SUSPECTED`，并进入人工复核。
- warning 做去重，页码判断不再误伤 page=0。

3. ai-verify API 路由
- 更新 `backend/app/routers/company_v2_debug.py`。
- `POST /api/v2/company/{market}/{symbol}/reports/{report_id}/ai-verify` 返回 `request_id`、`report_id`、`report_year`、`report_type`、`ai_verification_status`、`fields`、`human_review_queue`、`warnings`。
- `REPORT_NOT_FOUND`、`REPORT_NOT_PARSED`、`STRUCTURED_ANNUAL_HISTORY_MISSING`、`AI_VERIFICATION_FAILED` 均返回 structured error，不抛 500。
- 返回前递归移除 `local_path`、`path`、`text_pages`、`pdf_text`、`full_pdf_text`、`raw_pdf_text`，并截断 evidence excerpt。
- 未新增买入、卖出、目标价、保证上涨等投资建议输出。

4. 前端轻量接入确认
- 保留 `frontend/src/api/companyV2.js` 的 `aiVerifyCompanyV2Report`。
- 保留 `frontend/src/components/company-v2/CompanyV2ReportTimeline.vue` 的 AI 校对按钮、AI badge、human review queue 简单列表、evidence excerpt 简要展示。
- 保留 `frontend/src/components/company-v2/CompanyV2ReportDocuments.vue` 的 AI 校对调用与状态消息。
- 未改 CompanyV2 主布局，未改图表，未新增复杂页面。

5. 最小测试
- 更新 `backend/tests/fundamental/test_phase6tc1_ai_official_verification_agent.py`。
- 覆盖 revenue excerpt 命中、excerpt 长度限制、每字段 top 3、missing evidence 不能 verified、低置信度进入人工复核、单位数量级疑似、period mismatch 阻止 verified、API public payload 不泄露 `local_path` / 不返回全文、无投资建议词。
- 保留 `frontend/src/tests/companyV2AIOfficialVerification.test.js`。
- 覆盖 AI 校对按钮、AI badge、human review queue、evidence excerpt、`local_path` 不渲染、无投资建议词。

6. Targeted test 结果
- `pytest backend/tests/fundamental/test_phase6tc1_ai_official_verification_agent.py -q`：10 passed，1 warning（pytest unknown `asyncio_mode` config）。
- `npm run test -- companyV2AIOfficialVerification.test.js`：1 file passed，5 tests passed；有 pyenv shim 不可写和 Vite CJS deprecation 警告。
- `npm run build`：passed；有既有 chunk size warning。

7. 601686 AI verification artifact
- 未生成以下 artifact：
  - `backend/docs/artifacts/company_v2_601686_ai_official_verification_phase6tc1.json`
  - `backend/docs/artifacts/company_v2_601686_ai_human_review_queue_phase6tc1.json`
  - `backend/docs/artifacts/company_v2_601686_ai_verification_summary_phase6tc1.md`
- 原因：本地 artifact 记录显示 601686 report_id=1、parse_status=parsed，但当前本地 SQLite 无 `report_documents` 表，且未找到真实 parsed PDF `.pages.json` 或 PDF 文件，无法调用 ai-verify API 形成真实闭环。
- AI verification artifact skipped because parsed PDF/report_id is unavailable.

8. 是否建议进入 Phase 6T-D
- 不建议立即进入 Phase 6T-D。
- 建议先恢复或重建本地 `report_documents` 记录与 601686 parsed page sidecar，完成一次真实 `ai-verify` API 调用并生成 artifact 后，再进入 Phase 6T-D。

---
下一步：你需要操作

第一步：确认是否允许补齐本地 601686 `report_documents` 表记录和 parsed page sidecar，以便生成真实 AI verification artifact。

第二步：如允许，执行一次 `POST /api/v2/company/CN/601686/reports/{report_id}/ai-verify`，保存三份 phase6tc1 artifact。

第三步：artifact 确认可复现后，再决定是否进入 Phase 6T-D；进入前不启动 RAG 实作。
