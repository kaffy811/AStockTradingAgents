# Google-only 候选增量

只包含本次账户机制修改，相对于开始任务时已有 Google 功能的工作区；不包含已有行情缓存、分析报告、模型依赖或 Dockerfile 的其他改动。完整白名单和指纹见 manifest.json。

未获得服务器当前源码，**不是已验证可直接部署的生产包**。不适用于假定的最初仓库版本；需要先核对 `/opt/tradingagents` 的实际文件。只读检查：

```sh
python3 /tmp/google-only-v1/check_compatibility.py /opt/tradingagents
```

未知源码、缺失 Google 先决文件或部分应用会拒绝；不要绕过检查。此检查不连接数据库，也不能证明 google_sub 列/唯一约束已在服务器数据库中。

账户规则/限制：[GOOGLE_LOGIN.md](../../docs/GOOGLE_LOGIN.md)。旧账户人工审阅方案：[GOOGLE_ACCOUNT_MIGRATION.md](../../docs/GOOGLE_ACCOUNT_MIGRATION.md)。独立构建、发布、受保护回滚：[GOOGLE_ONLY_DEPLOYMENT.md](../../docs/GOOGLE_ONLY_DEPLOYMENT.md)。

没有执行生产部署、迁移或账户绑定。保留共享 Supabase、旧账户和邀请码数据。应用回滚不得顺带删除 google_sub 或恢复数据库快照；退回旧登录实现之前必须阻断旧准入路径，不能重新公开密码/邀请码入口。

本地验证记录：相关后端 646 passed（33 个已有 mock/弃用 warnings）；前端全量 73 files / 799 passed；`VITE_API_BASE=/api/v1` 生产构建成功。隔离副本已检查候选补丁应用/逆向兼容，并完成前端全量测试与构建。JWT 缺失 audience 现在也会拒绝，不能只验证“存在的 audience 是否匹配”。

并发开户使用临时 SQLite 的真实唯一约束；Redis 为模拟原子存储，Google 签名为本地生成 RSA 测试密钥。没有将测试连接指向共享 Supabase。尚未验证真实 Google 弹窗/受众、生产 PostgreSQL 与 Redis ACL、Docker 镜像或生产运行状态。
