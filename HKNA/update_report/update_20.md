---
目前完成的工作汇总：

已完成

0. 修改文件清单
- Backend:
  - `backend/app/core/database.py`
  - `backend/app/main.py`
  - `backend/app/models/__init__.py`
  - `backend/app/models/company_v2_report_rag.py`
  - `backend/app/routers/company_v2_report_rag.py`
  - `backend/app/services/company_v2_report_chunker.py`
  - `backend/app/services/company_v2_report_embedding_service.py`
  - `backend/app/services/company_v2_report_rag_index_service.py`
  - `backend/app/services/company_v2_report_rag_retriever.py`
  - `backend/app/services/company_v2_report_rag_answer_service.py`
  - `backend/app/services/company_v2_report_rag_prompt_builder.py`
  - `backend/scripts/company_v2_report_rag_eval.py`
  - `backend/tests/fundamental/test_phase6td_report_chunker.py`
  - `backend/tests/fundamental/test_phase6td_report_rag_index.py`
  - `backend/tests/fundamental/test_phase6td_report_rag_retriever.py`
  - `backend/tests/fundamental/test_phase6td_report_rag_answer.py`
  - `backend/tests/fundamental/test_phase6td_report_rag_api.py`
- Frontend:
  - `frontend/src/api/companyV2.js`
  - `frontend/src/components/company-v2/CompanyV2ReportDocuments.vue`
  - `frontend/src/components/company-v2/CompanyV2ReportTimeline.vue`
  - `frontend/src/components/company-v2/reports/CompanyV2ReportQaPanel.vue`
  - `frontend/src/components/company-v2/reports/CompanyV2ReportCitationList.vue`
  - `frontend/src/components/company-v2/reports/CompanyV2ReportRagStatus.vue`
  - `frontend/src/tests/companyV2ReportQaPanel.test.js`
- Artifacts / report:
  - `backend/docs/artifacts/company_v2_601686_report_rag_index_phase6td.json`
  - `backend/docs/artifacts/company_v2_601686_report_rag_eval_phase6td.json`
  - `backend/docs/artifacts/company_v2_601686_report_rag_eval_phase6td.md`
  - `backend/docs/artifacts/company_v2_phase6td_final_gate.json`
  - `backend/docs/artifacts/company_v2_phase6td_final_gate.md`
  - `HKNA/update_report/update_20.md`

1. Phase 6T-D 单报告 RAG 数据模型与服务
- 新增 `backend/app/models/company_v2_report_rag.py`，定义 `ReportRagDocument` 与 `ReportRagChunk`，字段覆盖 report_id、symbol、report_year、report_type、source_url、pdf_hash、parse_version、page_count、chunk_count、embedding_model、status、page_start/page_end、text_hash、metadata_json 等。
- 新增 Company V2 专用 chunk/index/retrieve/answer/prompt 服务，限定单股票、单报告、已下载且已解析的 CNINFO PDF sidecar。
- 当前实现不引入外部付费向量库，不上传整份报告，不自动下载 PDF，不自动索引。

2. Chunking
- 新增 `backend/app/services/company_v2_report_chunker.py`。
- 基于 page sidecar 生成带页码 chunk，默认 target_tokens=560、overlap_tokens=100、max_tokens=900、min_tokens=80。
- 保留页码、section_title、单位、年份、财务数字和表格附近文本。
- 去除重复页眉页脚，但不删除“单位：元/万元/亿元”等关键上下文。
- 不跨公司、不跨报告。

3. Embedding / Index
- 新增 `backend/app/services/company_v2_report_embedding_service.py`。
- 使用本地 deterministic `company-v2-hash-keyword-v1`，无外部 API 成本。
- 新增 `backend/app/services/company_v2_report_rag_index_service.py`，支持幂等索引、text_hash 去重、indexed/partial/failed/stale 状态、chunk_count 与 embedding_version 追踪。
- 当前 repository 已抽象，后续可替换为 PostgreSQL/pgvector。

4. Retrieval
- 新增 `backend/app/services/company_v2_report_rag_retriever.py`。
- report_id、symbol、report_year 强过滤，禁止跨报告检索。
- top_k 默认 6，上限 12。
- 使用 hybrid score：embedding similarity + keyword recall，并对主要会计数据页做轻量排序优先级。
- 支持关键词 fallback 语义，不暴露 local_path。

5. Answer Guardrails
- 新增 `backend/app/services/company_v2_report_rag_answer_service.py` 与 `company_v2_report_rag_prompt_builder.py`。
- 只基于 retrieved chunks 生成 extractive answer；无证据返回 `insufficient_evidence`。
- 拒绝投资建议、目标价和未来涨跌预测。
- 每个可回答结论返回 page citation，不输出完整 PDF 文本，不暴露系统 prompt 或 local_path。
- 对“归属于上市公司股东的净利润”避免误选“扣除非经常性损益”的扣非口径。

6. API
- 新增 `backend/app/routers/company_v2_report_rag.py` 并注册到 `backend/app/main.py`。
- 新端点：
  - `POST /api/v2/company/{market}/{symbol}/reports/{report_id}/rag/index`
  - `GET /api/v2/company/{market}/{symbol}/reports/{report_id}/rag/status`
  - `POST /api/v2/company/{market}/{symbol}/reports/{report_id}/rag/query`
- API 校验 report_id 与 symbol 一致；PDF 未下载/未解析或 sidecar 缺失时返回明确 precondition error。

7. Frontend
- 更新 `frontend/src/api/companyV2.js`，新增 RAG index/status/query API。
- 更新 `CompanyV2ReportTimeline.vue` 与 `CompanyV2ReportDocuments.vue`，在单份报告卡片内增加 Report QA toggle。
- 新增：
  - `CompanyV2ReportQaPanel.vue`
  - `CompanyV2ReportCitationList.vue`
  - `CompanyV2ReportRagStatus.vue`
- 面板默认不展开；只在用户展开后读取 status；只有点击“建立报告问答索引”才触发索引。
- 显示未索引、索引中、可提问、索引失败、索引过期、insufficient evidence、citation 页码与 CNINFO source URL。

8. 601686 真实索引结果
- 报告：601686 / 2024 annual / report_id=1。
- 来源：已解析 CNINFO page sidecar `company_v2_report_1_e6a216071c389d92.pages.json`。
- page_count=265。
- chunk_count=296。
- embedded_chunks=296。
- embedding_model=`company-v2-hash-keyword`。
- elapsed_ms=357。
- auto_download=false。
- auto_parse=false。
- batch_all_stocks=false。

9. 真实 QA / RAG Eval
- 8 个问题完成评估：
  - 营业收入：answered，引用主要会计数据页。
  - 归属于上市公司股东的净利润：answered，避免扣非口径误选。
  - 经营活动产生的现金流量净额：answered。
  - 主要风险：answered。
  - 前五名客户销售额占比：answered。
  - 主营业务：answered。
  - 未来利润保证：insufficient_evidence。
  - 明天会涨吗：拒绝投资建议。
- retrieval_hit_rate=1.00。
- citation_page_accuracy=1.00。
- grounded_answer_rate=1.00。
- cross_report_leakage=0。
- investment_advice_refusal=1.00。
- unsupported_answer_rate=0.00。

10. Artifacts
- 已生成：
  - `backend/docs/artifacts/company_v2_601686_report_rag_index_phase6td.json`
  - `backend/docs/artifacts/company_v2_601686_report_rag_eval_phase6td.json`
  - `backend/docs/artifacts/company_v2_601686_report_rag_eval_phase6td.md`
  - `backend/docs/artifacts/company_v2_phase6td_final_gate.json`
  - `backend/docs/artifacts/company_v2_phase6td_final_gate.md`

11. Tests / Build
- Backend targeted：18 passed。
- Backend full：2887 passed, 1 skipped。
- Frontend targeted：2 files / 22 tests passed。
- Frontend full：49 files / 617 tests passed。
- Frontend build：成功。
- 环境 warning：`pyenv: cannot rehash`，不影响测试/build 结果。

12. Phase 6T-D Gate
- index_gate_passed=true。
- retrieval_gate_passed=true。
- citation_gate_passed=true。
- grounded_answer_gate_passed=true。
- safety_gate_passed=true。
- frontend_gate_passed=true。
- tests_gate_passed=true。
- phase6td_passed=true。
- blocking_issues=[]。
- warnings=[]。

13. Limitations
- 当前只支持单股票、单报告、已下载并已解析的 CNINFO PDF。
- 暂不做多股票横向比较、多报告跨年度综合问答、新闻 RAG、行业研报、全文摘要一次性生成。
- 当前 embedding 为本地 deterministic hash-keyword，后续可替换为 PostgreSQL/pgvector 或本地语义模型，但必须保持 report_id 强过滤。

14. Rollback
- 可回滚新增 Company V2 RAG router 注册、前端 Report QA toggle、RAG services/models/tests/artifacts。
- 不影响 legacy report_rag v1、AI verification、Phase 6T-E artifacts 或 CNINFO stability artifacts。

---
下一步：你需要操作

第一步：在本地页面选择 601686 的 2024 年年报，展开 Report QA，确认索引按钮、状态、问答与 citation 展示符合预期。

第二步：如需继续扩展，优先做多报告/多股票范围设计，但必须保留 report_id/symbol/year 强过滤和证据页码。

第三步：进入多报告扩展前，先决定是否将当前 in-memory repository 迁移到 PostgreSQL/pgvector 或继续使用本地 deterministic 检索作为过渡实现。
