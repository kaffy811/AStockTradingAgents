---
目前完成的工作汇总：

已完成

1. `backend/app/routers/company_v2_debug.py` 匿名 history 正向白名单修复
- 删除未知标量默认透传逻辑，改为六个公开模块各自的固定业务字段 allowlist。
- 未知字段、未知模块、未知 `None`、嵌套 dict/list 均默认拒绝。
- 模块状态、原因码、期间类型、来源和截断原因使用固定枚举或受控映射。

2. 公开 warning 与错误文案硬化
- warning code 仅允许固定枚举，message 仅来自本地通用中文映射，不复制上游错误文本。
- warning field 必须属于当前模块公开字段，outlier status 必须属于固定枚举。
- profile 异常统一返回 `PUBLIC_PROFILE_UNAVAILABLE`，不再回显 `str(exc)`。

3. 匿名 EOD 最小响应投影
- Gateway 数据获取、行情计算与缓存逻辑未改动；仅在匿名 route 返回前执行正向 DTO 投影。
- 删除 `endpoint`、provider 原始 code/message、request metadata、raw 字段和未知字段。
- 保留业务事实、来源、as_of、freshness、状态、reason code 与 field availability。

4. 安全与前端回归测试
- 新增敏感命名字段、随机未知标量、`None`、嵌套值、恶意 warning 文案、EOD provider detail、profile 异常原文的负向测试。
- 匿名 history 继续返回公开数据，不出现 `AUTH_REQUIRED`；前端在 allowlist 响应下正常消费业务字段，并保持模块级 unavailable。
- 直接相关后端测试 33 passed；扩大相关后端回归 97 passed。
- 完整前端低并发发布门禁 69 files / 764 passed / 0 failed / 0 worker timeout；production build 通过。
- Python compile、JSON 校验、secret scan 与 `git diff --check` 通过。

5. 范围控制
- 未调用 live Provider，复用 Phase 7D-P0.2 持久化 evidence。
- 未修改 Docker、依赖、lockfile、migration、Token、Tushare 数据逻辑、行情计算、新闻、RAG 或全局鉴权。
- 未 push、merge、部署、执行 migration 或扩流。

---
下一步：你需要操作

第一步：审阅 `phase7d_p0_4_public_response_allowlist.md` 与 JSON 字段矩阵，确认公开财务字段集合符合产品契约。
第二步：独立复核匿名 history、EOD 与 profile 的负向安全测试结果。
第三步：部署前仍需 Owner 单独确认 Tushare 的公开展示、缓存与 AI 摘要使用权；本提交不得自动获得部署授权。
