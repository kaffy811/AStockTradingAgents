---
目前完成的工作汇总：

已完成

1. 固定 release 与隔离构建
- 在新的 `/private/tmp/phase7d_p0_11_retry.mBNgDx/worktree` 中检出 `98c111b…`，确认 tree 为 `24a9961…` 且构建前后无业务文件改动。
- 远端 ancestor 检查通过；执行非 force push，结果为 `Everything up-to-date`。

2. 顺序构建并验证 Linux 镜像
- 严格按 backend、frontend 顺序构建 `linux/amd64` 镜像。
- 两个镜像均记录 OCI revision、source tree、image digest 与独立版本标签；配置/history 凭据模式扫描均为 0。

3. 安全传输与服务器预检
- 将两个 tar 顺序传至服务器 `/tmp`，服务器 SHA-256 与本地完全一致。
- 复核 `/opt/tradingagents` 的 Git、容器、内存、磁盘与 backend health。
- 保留 `docker-compose.staging.yml` 修改和 `.env.staging.local.backup.20260728-130419`；二者与 release diff 无重叠且未进入 staging。

4. 分步切换与验收
- 在加载前为旧 backend/frontend 镜像创建独立 rollback tag。
- 先切换 backend；`/health` 返回 HTTP 200，Company profile 与 annual history 均返回 HTTP 200、无 `AUTH_REQUIRED`。
- backend 验收通过后切换 frontend；本机 `18080` 与公开 `https://aastock.cloud/` 均返回 HTTP 200。
- 最终运行镜像分别为 backend `sha256:6e21f29…` 与 frontend `sha256:0312050…`，本次最终尝试未触发 rollback。

5. 发布边界与授权记录
- 未执行 migration、Compose `down`、`--remove-orphans`、服务器构建、force push、并行构建、扩流或清理镜像/卷/容器。
- Owner 已确认 Tushare EOD 商业展示、缓存与 AI 研究摘要用途；交付物未记录 Token 或客服私密信息。

---
下一步：你需要操作

第一步：观察 `aastock.cloud` 现有单实例的 health 与错误日志，不扩流、不改变缓存或 Provider 配置。

第二步：如发现应用异常，只使用已保留的 backend/frontend rollback tag 恢复上一镜像，不执行破坏性 Git 回退。

第三步：在单独授权的后续阶段整理 `/tmp` 中的镜像 tar 与验收响应文件；本阶段不删除任何服务器文件。
