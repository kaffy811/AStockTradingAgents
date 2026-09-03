---
目前完成的工作汇总：

已完成

1. Report Chat citation metadata containment
- 将模型可见证据从数据库 `chunk_id` 切换为单请求局部 `E1..En`。
- 后端仅在请求内保存 `E1 -> chunk_id` 映射，并在模型返回后解析回兼容的 `source_chunks`。
- 模型可见的结构化财务副本递归移除 `chunk_id/source_chunk_id`，原始结构化数据仍供 numeric validation 使用。

2. Citation resolver 与质量门
- 拒绝未知、纯数字、格式错误、重复和空 evidence label。
- citation claim 中的数字必须存在于映射证据或其报告期 metadata。
- 新增 request-aware `CITATION_METADATA_LEAK` 检测，只匹配本次 retrieved ID 与 citation 语境，不误伤普通四位金融数字。

3. 测试与运行取证
- 最终 targeted/regression：127 passed，0 failed，0 skipped。
- 最终镜像 Q1、Q4 completed，citation/numeric validation 均通过，无 raw chunk ID prompt/answer 泄漏。
- Phase R3.2C.1 使用一次受控调用关闭 Q2：S0–S8 完整、completed、citation/numeric validation 均通过，Prompt 与答案无 raw chunk ID。
- 详细证据见 `backend/docs/artifacts/company_agents_data_r3_2c_citation_metadata_containment.md`。

---
下一步：你需要操作

第一步：保持 `HOLD_1_PERCENT`，不要 push 或扩流。
第二步：核对本地隔离 commit 仅包含 R3.2C 白名单文件。
第三步：后续扩流必须经过独立 owner-approved gate；本阶段不部署、不扩流。
