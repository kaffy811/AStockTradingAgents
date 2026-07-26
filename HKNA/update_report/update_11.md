---
目前完成的工作汇总：

已完成

1. Production 默认 CompanyV2 配置
- `frontend/.env.production.example` 已设置 `VITE_COMPANY_TAB_VERSION=v2`。
- `.env.example` 和 `backend/.env.example` 已更新为 Phase 6S 后 production 默认 v2、legacy 为 rollback。
- 保留 `company_v2=0` 强制 legacy 回退。

2. Cutover / rollout 文档更新
- 更新 `backend/docs/artifacts/company_v2_staged_rollout.md`。
- 更新 `backend/docs/artifacts/company_v2_production_staged_cutover.md`。
- 更新 `backend/docs/artifacts/company_v2_production_cutover_manual_acceptance.md`。
- 更新 `backend/docs/artifacts/company_v2_legacy_inventory.md`。

3. Post-cutover observation
- 新增 `backend/docs/artifacts/company_v2_post_cutover_observation.md`。
- 首轮 observation status：stable。
- rollback_recommended=false。

4. Post-cutover smoke
- 已生成 `backend/docs/artifacts/company_v2_production_smoke_summary_after_cutover.json/md`。
- 三股票 smoke gate PASS。
- providers_data_success=8，modules_renderable=9，strong_failed_count=0。

5. 测试更新
- 更新旧阶段测试中 production 默认策略预期。
- `pytest -q`：2628 passed, 1 skipped。
- `npm run test`：487 passed。
- `npm run build`：passed。

---
下一步：你需要操作

第一步：部署生产前端时确认 build env 使用 `VITE_COMPANY_TAB_VERSION=v2`。
第二步：部署后打开 `/stocks/CN/600519`、`/stocks/CN/000725`、`/stocks/CN/601686` 做浏览器人工验收。
第三步：验证 `/stocks/CN/600519?company_v2=0` 可回 legacy。
第四步：继续 Phase 6T 24-48 小时观察，不删除 legacy。
