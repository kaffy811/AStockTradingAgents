---
目前完成的工作汇总：

已完成

1. 修复生产 API 反向代理契约
- 将 frontend Nginx 从仅代理 `/api/v1/` 调整为统一代理 `/api/`，保持已有 v1 路径不变并覆盖 v2。
- 将 `/health` 和 `/health/` 子路径交给 backend，避免 SPA HTML 假 200。
- 显式保留 backend 的 401、403、404、422 和 500 JSON 状态与响应。

2. 保持 SPA 页面路由
- 普通前端页面仍由 `location /` 的 `try_files ... /index.html` 处理。
- API 与 health location 优先级高于 SPA fallback。

3. 新增双层自动化验证
- Vitest 静态契约：5/5 passed。
- 纯 frontend 镜像 + 受控 mock backend：11/11 HTTP contract passed。
- 完整前端测试：70 files、769 tests passed，0 worker timeout。
- production build、`nginx -t`、Python compile 均通过。

4. 保持范围边界
- 未修改 backend、股票代码路由、Tushare、CNINFO、数据库、Docker Compose、依赖、Token、migration、RAG、调度或新闻 Provider。
- 未 push、merge 或部署。

---
下一步：你需要操作

第一步：Owner 只读审阅本地候选 commit 的完整 diff 与文件范围。

第二步：若批准，单独执行 frontend-only 镜像发布；不得夹带 `000725.SZ / 600519.SH` 路由修复。

第三步：部署后从公网验证 `/api/v2/company/CN/000725/profile`、annual history 与 `/health` 为真实 JSON，并确认 4xx/5xx 不再被 SPA 改写。
