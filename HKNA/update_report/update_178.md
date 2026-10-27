---
目前完成的工作汇总：

已完成

1. Google-only 自动开户与身份边界。
- backend/app/routers/auth.py、services/google_accounts.py：新用户只需 Google 验证即可创建普通账户，不需要邀请码、密码或注册页面；现有账户只按稳定 sub 登录，邮箱只用于冲突阻断。
- 相同邮箱但未绑定/绑定其他 sub 一律返回 ACCOUNT_MIGRATION_REQUIRED，不能凭邮箱或原密码接管旧账户，包括管理员。停用账户拒绝登录；新用户明确 is_admin=false；不改旧 UUID、权限、历史报告、自选股或既有 Google 绑定。
- flush/commit 都在 IntegrityError 保护内。并发首次开户以 google_sub 唯一约束选出胜出账户，回滚后只按同一 sub 读取；邮件冲突查询期间出现同 sub 账户时也安全重查。
- NOT NULL 密码列保留：写入随机不可知密码的有效 bcrypt hash，在线程中计算；不提供可用密码，也不破坏回滚前的字段格式。

2. 认证验证、会话与限流。
- services/google_identity.py 保留固定 Google JWKS、RS256、issuer、audience、有效期、已验证邮箱及 nonce 校验；补充非空 sub/服务端 nonce、必需 audience、未来 iat、有效邮箱及 azp 检查。
- 测试特别覆盖缺失 aud：JWT 库仅校验存在的 audience 不够，现明确 require_aud=true。
- 保留 HttpOnly/Secure/SameSite nonce cookie、五分钟 Redis 会话、GETDEL 原子消费和防重放；真实本地 RSA 签名凭证通过一次后，原会话/新 nonce 均不能复用旧凭证。
- services/auth_rate_limit.py：Lua 原子计数与过期，跨进程共享；按 IP、已验签 sub、注册尝试和 refresh 用户设置正整数限额，429 返回 Retry-After，Redis 故障 503 fail-closed。配置及 .env.example 已说明默认值和可信代理要求。
- refresh 保留原用户 UUID 并重新检查账户存在/启用；me、现有前端退出机制保留，退出清本机 JWT 并 disableAutoSelect。沿用原无状态 JWT 生命周期，不声称本机退出可立即撤销所有已复制 token。
- SafeAuthRoute 不回显输入校验中的 credential/refresh token，对数据库与未知错误返回安全 JSON；即使 debug=true 也不展示凭证、SQL 或堆栈。错误日志仅记录类别名。

3. 旧入口服务端停用与界面收口。
- 密码 login/register、注册验证码、邀请码校验/创建/撤销接口均返回 410 AUTH_METHOD_DISABLED，标记 deprecated；旧参数和开关不能重新启用。
- 管理类接口继续要求管理员鉴权；历史邀请码 GET 列表只读保留，不输出 hash 或明文，不删除表或行。
- frontend LoginView、LoginCard、router、auth store/API、AppHeader、RegisterView、AdminInvitesView 已移除密码/邀请码表单、注册导航和邀请码管理入口。旧路径重定向到登录/个人资料，无旧 API 客户端方法。
- Google-only 页面覆盖加载、未配置、选择账户、停止等待、迟到回调忽略、15 秒 HTTP 等待截止、失败与重新取得 nonce 重试。关闭弹窗不保证 GIS 回调，因此提供明确停止等待提示。
- 网络失败转换为可理解中文提示，非 JSON 正文不暴露；已有行情缓存和分析报告修复不重写。
- startup_validation 不再要求旧邮件/邀请码配置，正式环境需要正确 Google Web client；不强制轮换已有 SECRET_KEY。

4. 测试与构建证据。
- 最终相关后端 646 passed，33 warnings，13.67s，覆盖认证、历史邀请码工具/只读审计、报告生成/保存/历史、事务、管理员权限、行情、自选股聚合与 CORS。
- 后端命令使用 DATABASE_URL=postgresql+asyncpg://unit:unit@127.0.0.1:1/unit 和仅测试用 SECRET_KEY，避免测试误用共享 Supabase。新 Google 身份/账户核心在候选补丁隔离副本另有 62 passed，1 warning，2.54s。
- 并发首次开户使用临时 SQLite 的真实 SQL 事务和唯一约束；Redis 原子存储为模拟，RSA 签名为本地测试密钥。没有依赖真实 Google 凭证或共享数据库。
- 前端全量 73 个文件 / 799 passed，另验证 Google-only 页面、取消/重试、网络/非 JSON 错误、会话与管理员状态；生产 Vite 构建成功，VITE_API_BASE=/api/v1。
- 旧密码/邀请码“成功写入”测试按新停用契约替换；哈希工具、历史模型、只读列表与管理员鉴权测试继续保留。中间旧契约测试的失败已处理，没有通过重新开放旧接口满足旧断言。
- 后端 warnings 为既有 AsyncMock/后台任务清理及 crypt/utcnow 弃用；前端有既有 Vite CJS/大 chunk 提示。git diff --check 通过。

5. 迁移与独立交付。
- docs/GOOGLE_ACCOUNT_MIGRATION.md：独立旧账户归属证据 + Google 验签证据、按 UUID 的工单审批、审计、演练、资源归属核对和撤销计划。管理员必须单独双人审批，不走普通绑定模板。
- docs/GOOGLE_ACCOUNT_MIGRATION_REVIEW.sql：仅审阅、默认 ROLLBACK，限定启用且非管理员且未绑定的目标 UUID，仅更新 google_sub/updated_at；不移动外键、不改权限、不执行。
- 本次没有新增必需迁移、修改/运行已有 Google 迁移。已存在 google_sub 唯一约束的环境无需新增 schema 变更；若服务器缺列/约束，需另获批准后审阅并验证已有 s7t8u9v0w1x2 迁移。
- docs/GOOGLE_LOGIN.md、README、环境示例与旧指南标注更新；Google 测试/受众及 Workspace 策略仍可能限制登录，本地取消邀请码不会修改控制台，基本身份 scopes 可能适用例外，已链接官方依据。
- docs/GOOGLE_ONLY_DEPLOYMENT.md：先核对服务器实际源码、Mac/CI 构建、备份旧镜像及白名单源码、用既有 aastock-mvp 三份 Compose 仅更新前后端；回滚不得删除 Google 列或恢复数据库，退回旧登录实现前须阻断旧准入路径。
- deployment/google-only-v1：38 文件候选补丁、manifest.json、只读源码兼容脚本及 validation.json。基于任务开始时已有 Google 功能的工作区增量，未混入行情、报告、Dockerfile、模型依赖等其他改动。验证了隔离应用/逆向应用/再次应用及源码漂移拒绝。
- 服务器当前源码未知，候选包未声称可直接上线。检查器验证的是文件，不是共享数据库 schema 或生产运行状态。

6. 未执行与剩余限制。
- 没有部署、提交、推送、执行迁移/账户绑定、修改共享 Supabase、删除旧用户/邀请码数据、改 Google 控制台或 DNS/Vercel。
- 没有真实 Google 弹窗/控制台受众验收；未在生产 PostgreSQL/Redis ACL 或生产镜像上验证。没有运行完整后端全库。
- 原 Google 绑定模型和迁移文件保持不变；工作区此前 Google、行情缓存、报告生成及其他未提交改动保留。
- 本次白名单（完整内容另见 manifest.json）：
- `backend/app/routers/auth.py`
- `backend/app/routers/admin_invites.py`
- `backend/app/routers/mvp.py`
- `backend/app/services/google_identity.py`
- `backend/app/services/google_accounts.py`
- `backend/app/services/auth_rate_limit.py`
- `backend/app/core/config.py`
- `backend/app/core/startup_validation.py`
- `frontend/src/api/auth.js`
- `frontend/src/stores/auth.js`
- `frontend/src/router/index.js`
- `frontend/src/views/LoginView.vue`
- `frontend/src/views/RegisterView.vue`
- `frontend/src/views/AdminInvitesView.vue`
- `frontend/src/components/LoginCard.vue`
- `frontend/src/components/AppHeader.vue`
- `frontend/src/utils/googleIdentity.js`
- `backend/tests/test_google_identity.py`
- `backend/tests/test_google_only_auth.py`
- `backend/tests/test_admin_invites.py`
- `backend/tests/test_email_verification.py`
- `backend/tests/test_invite_hasher.py`
- `backend/tests/test_mvp_r12_invite_security.py`
- `backend/tests/test_mvp_r12b_invite_code_format.py`
- `frontend/src/tests/marketApiErrors.test.js`
- `frontend/src/tests/googleOnlyLogin.test.js`
- `frontend/src/tests/googleAuthSession.test.js`
- `README.md`
- `.env.example`
- `backend/.env.example`
- `docs/GOOGLE_LOGIN.md`
- `docs/GOOGLE_ACCOUNT_MIGRATION.md`
- `docs/GOOGLE_ACCOUNT_MIGRATION_REVIEW.sql`
- `docs/GOOGLE_ONLY_DEPLOYMENT.md`
- `docs/server_deployment_guide.md`
- `docs/manual_product_test_guide.md`
- `docs/frontend_engineering_smoke_test.md`
- `docs/api_smoke_test_plan.md`

---
下一步：你需要操作

第一步：本地审阅与隔离验收。
- 阅读 docs/GOOGLE_LOGIN.md 与 docs/GOOGLE_ACCOUNT_MIGRATION.md；检查候选包 deployment/google-only-v1。
- 可重跑：DATABASE_URL=postgresql+asyncpg://unit:unit@127.0.0.1:1/unit SECRET_KEY=unit-test-only-google-session-signing-key backend/.venv/bin/python -m pytest -q backend/tests/test_google_identity.py backend/tests/test_google_only_auth.py。
- frontend 目录执行 npm test 与 VITE_API_BASE=/api/v1 npm run build。真实 Google 验收使用独立 OAuth client/测试账号与隔离数据库，不把测试报告或账户写入共享 Supabase。

第二步：若未来批准发布，先核对服务器与管理员迁移准备。
- /opt/tradingagents 记录 git rev-parse HEAD、git status --short 及相关实际源码；核对 google_sub 列/唯一约束是否已存在，不自动执行迁移。
- 使用只读 check_compatibility.py 核对候选基线；不匹配就根据实际版本重整并复测，不能覆盖服务器修改。
- 确认现有管理员的合法 Google 绑定与 Google 控制台受众/测试配置；未绑定账户迁移需要独立批准和审计，普通登录不能替代。

第三步：只在明确批准后按独立步骤部署/回滚。
- 见 docs/GOOGLE_ONLY_DEPLOYMENT.md：在 Mac/CI 按服务器架构构建；保留 .env.staging.local、Supabase 与服务器三份配置。
- 项目 aastock-mvp，使用 docker-compose.yml、docker-compose.staging.yml、docker-compose.mvp-server.yml，仅 backend/frontend，--no-deps --no-build；不 down、不 --remove-orphans、不重建 PostgreSQL 或数据库。
- 回滚恢复旧镜像及本次源码增量，不删除期间新账户和绑定；旧实现必须先进入受保护维护状态，不能重新公开密码/邀请码入口。
