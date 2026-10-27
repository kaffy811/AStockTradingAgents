---
name: Phase 6W-R1.4 Staging Smoke 完成状态
description: 提交/push/staging部署/21次请求观察/14/15 gates PASS/G9 browser color deferred
type: project
---

Phase 6W-R1.4 staging smoke 基本通过，14/15 gates PASS。

**Why:** 完成 R1 工作区整理、3 commit 提交、staging 热更新部署、Smoke A-G 全量验证。

**How to apply:** G9（浏览器 computed style 红涨绿跌）未做到 browser-level，仅 vitest + source 验证。Production 1% 灰度前需项目负责人手动浏览器确认 A股颜色。其他14项全通过可继续推进。

**Commit SHAs:**
- Base: `9005c08`
- Commit 1 (backend): `4ab8edf`
- Commit 2 (frontend): `5529ffe`
- Commit 3 (artifacts): `7438d18`
- Commit 4 (R1.4 smoke): `d3b7063`
- Final HEAD: `d3b7063fb4941561d2ecce0eea26ef569d11b685`

**Staging:**
- Method: docker cp hot-update to P1.25 containers (base images unavailable locally)
- Backend: 127.0.0.1:18000 healthy
- Frontend: 127.0.0.1:18080 HTTP 200
- New code active: validate_numeric_claims, cache intent_type, color fix

**Test results:**
- Backend targeted: 75/75 PASS
- Frontend vitest: 740/740 PASS
- Vite build: exit 0

**Observation window:** 21 requests, 3 symbols, 0 5xx, 3 correct partial (report-chat no RAG), 18 success

**Artifact:** `backend/docs/artifacts/company_agents_data_r1_4_staging_smoke.md`
