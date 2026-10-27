---
目前完成的工作汇总：

已完成

1. R3.2 工作区与依赖审计
- 确认基线为 `3c30787`、分支为 `release/demo-staging`。
- 保留并审计 Claude Code 留下的 5 个 tracked 修改，没有覆盖或清理用户改动。
- 确认 `sentence-transformers` 已进入 `pyproject.toml` 与 `uv.lock`。

2. Production backend 镜像与本地模型验证
- 成功重建 backend 镜像并重启 backend 服务。
- 容器内确认 `sentence-transformers 5.7.0` 可导入。
- `intfloat/multilingual-e5-small` 成功加载，原生输出 384 维，与当前 `vector(384)` 约束一致。
- Runtime provider 为 `local`，模型可用，单条 embedding 约 0.22 秒，未回退 Mock。

3. Fresh RAG 检索验证
- 对真实 600519.SH / report_id=17 执行 10 个唯一问题的无缓存检索。
- 10/10 成功，0 timeout；P50 约 485.9ms，首个请求最大 5101.9ms。
- 确认实际 report-chat fast path 是 `indexed_db_lexical`，不是 local sentence-transformer vector path。

4. Fresh API E2E 验证与门禁停止
- 完成 10 个唯一财报问题的真实 API E2E 请求，RAG timeout 为 0。
- 仅 1/10 `numeric_validation.valid=true`；其余 9 个由 numeric guard 正确降级为 `partial_success`。
- 按 R3.2 规则在 G7 失败后停止，没有执行 30-request observation、没有提交、没有 push、没有扩大流量。

5. R3.2 证据制品
- 新增 `backend/docs/artifacts/company_agents_data_r3_2_dependency_remediation.md`。
- 新增 `backend/docs/artifacts/company_agents_data_r3_2_canary_observation.md`。
- 最终判定为 `HOLD_1_PERCENT`。

---
下一步：你需要操作

第一步：保持生产流量在 1%，不要扩大到 10%。

第二步：由项目负责人审阅 R3.2 报告，确认是否接受“依赖问题已解决，但 G7 冷生成数字非确定性仍未达到扩流门禁”的结论。

第三步：在没有新的明确授权前，不要提交当前 5 个 tracked 修改；其中 `backend/app/main.py` 的数据库连接池预热超出了原定 dependency/build-only 提交范围，需要单独决定保留或撤销。

第四步：若后续授权处理 G7，应以现有失败样本为证据单独立项，不得在本阶段修改 numeric validator、RAG timeout、retrieval algorithm 或阈值。
