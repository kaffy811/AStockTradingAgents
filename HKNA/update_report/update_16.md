---
目前完成的工作汇总：

已完成

1. backend venv 验收环境确认
- 本阶段所有后端命令均使用 `backend/.venv/bin/python`。
- 原因：项目后端实际运行环境是 `backend/.venv` 的 Python 3.12.10；裸 `pytest` 会走全局 pyenv Python 3.11.8，不作为本项目验收命令。

2. 601686 2024 年报记录恢复确认
- 已确认 `report_documents` 中存在真实记录：
  - `report_id`: 1
  - `market`: CN
  - `symbol`: 601686
  - `ts_code`: 601686.SH
  - `report_year`: 2024
  - `report_type`: annual
  - `source`: cninfo
  - `pdf_url`: https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF
- 未手工伪造 `report_id` 或 PDF URL。

3. Phase 6T-C2 专用脚本
- 新增 `backend/scripts/company_v2_run_601686_ai_verify_phase6tc2.py`。
- 脚本仅服务 601686 2024 年报 artifact 生成，按 discover、download、parse、ai-verify 顺序调用既有服务。
- 脚本不做 RAG、不做批量下载、不改 CNINFO discovery 主逻辑、不改 PDF download/parse 主链路。

4. PDF download 与 parse 状态
- download 状态：`verified`。
- parse 状态：`parsed`。
- `page_count`: 265。
- parsed page sidecar 已存在：`company_v2_report_1_e6a216071c389d92.pages.json`。
- artifact 输出中未暴露本地文件路径，未返回完整 PDF 文本。

5. AI verification agent 稳定性补丁
- 修改 `backend/app/services/company_v2_ai_official_verification_agent.py`。
- `_extract_json` 现在会校验 LLM 输出必须是 JSON object；如果返回数组、字符串等非 object 结构，会进入既有 fallback/结构化处理路径。
- 该补丁只修结构化输出健壮性，不改变业务主链路。

6. 601686 live AI verification artifact
- 已生成真实 artifact：
  - `backend/docs/artifacts/company_v2_601686_ai_official_verification_phase6tc2.json`
  - `backend/docs/artifacts/company_v2_601686_ai_human_review_queue_phase6tc2.json`
  - `backend/docs/artifacts/company_v2_601686_ai_verification_summary_phase6tc2.md`
- ai-verify 最终状态：`conflict`。
- 字段检查数量：10。
- `verified_count`: 1。
- `likely_match_count`: 0。
- `mismatch_count`: 3。
- `needs_human_review_count`: 1。
- `insufficient_evidence_count`: 5。

7. human_review_queue 摘要
- 队列数量：10。
- 涉及字段：
  - `total_share`
  - `revenue`
  - `net_profit_parent`
  - `operating_cashflow`
  - `total_assets`
  - `equity_parent`
  - `eps_basic`
  - `roe_weighted`
  - `float_share`
- 主要原因包括结构化值与年报披露值不一致、结构化字段缺失、年报证据不足、期末口径无法确认。

8. 测试结果
- `backend/.venv/bin/python -m pytest backend/tests/fundamental/test_phase6tc1_ai_official_verification_agent.py -q`
  - 结果：10 passed。
- `backend/.venv/bin/python -m pytest -q`
  - 结果：2767 passed, 1 skipped。
- `npm run test`
  - 结果：43 test files passed, 564 tests passed。
- `npm run build`
  - 结果：通过。

9. 是否建议进入 Phase 6T-D
- 当前不建议直接进入 Phase 6T-D。
- 建议先验收 Phase 6T-C2 artifact，并对 human_review_queue 中的结构化字段口径差异和缺失字段做人工确认，再决定是否进入下一阶段。

---
下一步：你需要操作

第一步：打开 `backend/docs/artifacts/company_v2_601686_ai_verification_summary_phase6tc2.md`，确认 report_id、PDF URL、download/parse 状态和 final_status 是否符合验收预期。

第二步：打开 `backend/docs/artifacts/company_v2_601686_ai_human_review_queue_phase6tc2.json`，逐项确认 `revenue`、`net_profit_parent`、`roe_weighted`、`total_share` 等字段的口径差异。

第三步：确认是否需要进入一个小范围的 Phase 6T-C2 follow-up，用于修正结构化年报字段口径或补齐缺失字段；在此之前不要进入 Phase 6T-D。
