---
目前完成的工作汇总：

已完成

1. `backend/docs/artifacts/company_v2_phase6tp_*`
- 先前已把 live Supabase 可达性、live integration tests、same-region acceptance 阻塞状态记录清楚。
- 这次未修改 Fusion / RAG / cache / job admission / 前端业务逻辑。

2. `backend/docs/artifacts/company_v2_phase6tq_*`
- 新增 Phase 6T-Q 的 runner provisioning、runner environment、DB preflight、same-region acceptance、cross-region comparison、live tests、final gate artifacts。
- 真实结果写成 blocked / not executed，没有伪造 runner、同区域验收或性能通过。

3. `HKNA/update_report/update_32.md`
- 补充说明 live Supabase tests 已通过，但同区域 runner 未 provision，same-region acceptance 仍未完成。

---
下一步：你需要操作

第一步：如果要继续 Phase 6T-Q，先在 ap-northeast-2 真正 provision 一个临时 runner，再运行同区域 HTTP acceptance。

第二步：如果 runner 无法创建，保留当前 hold 状态，不要把 live Supabase tests 或本地 DNS 结果当成同区域部署等价验收。

第三步：一旦 runner 可用，再补跑 live tests、steady-state create 和并发去重，并只根据真实样本更新 gate。
