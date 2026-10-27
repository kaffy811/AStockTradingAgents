# Google-only 账户机制

当前唯一准入方式为 Google Identity Services ID token。新用户验证成功后自动创建普通账户并登录，无邀请码、密码或额外注册步骤。现有 Google 绑定按稳定 `sub` 登录；邮箱变更不切换账户、不更新用户 UUID。新账户明确设置 `is_admin=false`，Google claims 或客户端字段不能授予管理员权限。

相同邮箱只用于阻止冲突，绝不用于自动关联。旧账户（包括管理员）未绑定 Google 时，普通登录返回 `409 ACCOUNT_MIGRATION_REQUIRED`，联系管理员处理；不再接受原密码完成绑定。迁移方案见 [旧账户迁移审阅方案](GOOGLE_ACCOUNT_MIGRATION.md)。已有绑定、历史报告、自选股、权限及旧密码/邀请码数据均保留。

## 身份与会话

- 后端固定使用 Google JWKS，验签算法仅 RS256；核对 issuer、audience、有效期、iat、非空 sub、已验证且有效的邮箱、nonce，并在 azp 存在时匹配 Client ID。不会采信客户端邮箱或管理员声明。Google 也要求用 sub 作为稳定标识，见[官方验证说明](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)。
- GET `/api/v1/auth/google/config` 生成 5 分钟 nonce，同时写 Redis 并设置 HttpOnly/SameSite=Lax cookie；正式环境要求 HTTPS/Secure cookie。验证后的 POST 通过 Redis GETDEL 原子消费 nonce；过期、重复或缺失会话不能签发 token，Redis 故障时拒绝准入。
- 首次开户由 `app_users.google_sub` 唯一约束兜底。flush/commit 唯一冲突后回滚并仅按同一 sub 读取胜出账户；相同邮箱的其他账户不能成为胜出账户。
- 继续签发原有用户 UUID 的 access/refresh JWT。`/auth/refresh` 加入限流，并重新检查账户存在且启用；`/auth/me` 保留。退出继续清理本机 token，并调用 GIS disableAutoSelect，不撤销 Google 授权。沿用现有无状态 JWT 模型，退出不代表所有已复制 token 即时作废，仍由原有效期及后端账户状态检查约束。
- 输入校验错误不回显 credential、refresh token 或额外敏感字段；Google、Redis、SQL 错误只返回安全提示。验证/数据库详情不放进响应正文。

## 停用的接口

下列写入口在后端永久返回 `410 AUTH_METHOD_DISABLED`，不依赖邀请码/验证码开关；无效或空请求也不会调用数据库或邮件发送器：

- POST `/api/v1/auth/login`
- POST `/api/v1/auth/register`
- POST `/api/v1/auth/email-verification/request`
- POST `/mvp/invites/check`
- POST `/mvp/invites`、POST `/api/v1/admin/invites`
- DELETE `/mvp/admin/invites/{id}`、POST `/api/v1/admin/invites/{id}/revoke`

管理类接口仍先鉴权，未授权/普通用户不能借停用接口绕过管理员权限。两个历史邀请码 GET 列表仍仅管理员可读，供审计；不返回 code hash 或明文码。表和旧数据不删除、邀请码不再消费。旧 `/register` 路由转到 `/login`，`/admin/invites` 转到个人资料；导航、表单、客户端不再提供旧入口。个人资料及普通业务路由的鉴权规则不变。

## 配置与 Google 控制台

1. 设置 `GOOGLE_CLIENT_ID=<Web application client ID>.apps.googleusercontent.com`。production/staging 缺少配置会拒绝启动；开发环境可启动并显示“暂未配置”。不要更换现有 SECRET_KEY 来切换登录方式，否则会使已有 JWT 失效。
2. Google 控制台配置实际 JavaScript origin：协议、主机、端口，不带路径。此实现使用 GIS popup/callback，无需 Client Secret，不申请 Drive/Gmail 授权。
3. 正式部署使用同站 HTTPS 和 `/api/v1` 反向代理；前端构建 `VITE_API_BASE=/api/v1`。本地前端已有 Vite `/api` 代理；使用客户端已配置的 localhost origin。不要公开后端调试服务。
4. Redis 为登录必需；注册、签发与刷新限流均 fail-closed。原 EMAIL_*、INVITE_*、MVP_PUBLIC_REGISTRATION_ENABLED 等旧准入设置不再控制 Google 注册，也不能重新打开密码接口。旧工具可保留这些配置用于历史审计/回滚，不要求配置邮件提供商才能启动 Google-only 服务。
5. Google 的 Testing/受众、Workspace 管理或应用策略仍可能限制可用账号。取消项目邀请码不会更改 Google 控制台。只有基本身份 scopes 时某些测试限制有例外，不能简单认定所有 GIS 应用都只允许测试名单；应核对实际 client、scopes、受众和浏览器结果。参见[管理受众](https://support.google.com/cloud/answer/15549945?hl=en)及[应用状态与基本身份 scope 例外](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)。本次没有修改控制台。

服务端默认限制（每个环境共享 Redis 计数；不能设 0 关闭）：

| 环境变量 | 默认上限 |
|---|---|
| AUTH_GOOGLE_NONCE_PER_MINUTE | 每 IP 20 次/分钟 |
| AUTH_GOOGLE_LOGIN_IP_PER_MINUTE | 每 IP 15 次/分钟 |
| AUTH_GOOGLE_LOGIN_SUB_PER_MINUTE | 每已验签 sub 10 次/分钟 |
| AUTH_GOOGLE_REGISTER_IP_PER_HOUR | 每 IP 5 次/小时开户尝试 |
| AUTH_REFRESH_IP_PER_MINUTE | 每 IP 30 次/分钟 |
| AUTH_REFRESH_USER_PER_MINUTE | 每用户 20 次/分钟 |

返回 429 时包含 Retry-After。反向代理场景必须核实并配置准确的 `TRUSTED_PROXY_IPS`，保持 Nginx 追加真实来源地址；未信任的连接忽略 X-Forwarded-For。若没有配置信任代理，多个用户可能共用代理 IP 的限额；不要信任任意外部来源以解决此问题。

## 数据库兼容

本次没有新增必须执行的迁移，也没有更改或执行原 Google 迁移。`hashed_password` 继续 NOT NULL：新 Google 用户写入随机不可知密码的有效 bcrypt hash，不返回原值；旧密码字段、旧用户 ID、邀请码表均不变。

必须核对服务器是否已经具备此前待审阅的 `backend/alembic/versions/2026_10_25_0001_google_identity.py`（revision `s7t8u9v0w1x2`）对应的 google_sub 列和唯一约束。若没有，必须先取得单独批准，审阅并在隔离副本验证该**加列/加唯一约束**迁移后才能发布；本次没有连接共享 Supabase 检查或执行它。应用回滚不执行该迁移的 downgrade，不删除已有 Google 绑定。

部署与回滚见 [Google-only 发布说明](GOOGLE_ONLY_DEPLOYMENT.md)。旧的 google-login.patch 是历史双登录实现，不能当作本次发布包；market-io-fix-v1 也不是账户发布包。

## 本地验收

测试使用伪 Google 签名/Redis、mock 账户或临时 SQLite；不访问共享 Supabase。建议命令显式使用无真实连接的测试地址：

```sh
DATABASE_URL=postgresql+asyncpg://unit:unit@127.0.0.1:1/unit \
SECRET_KEY=unit-test-only-google-session-signing-key \
backend/.venv/bin/python -m pytest -q \
  backend/tests/test_google_identity.py backend/tests/test_google_only_auth.py
cd frontend
npm test
VITE_API_BASE=/api/v1 npm run build
```

登录 UI 覆盖加载、未配置、SDK 加载失败、取消等待、迟到回调忽略、服务端失败/迁移提示及重试。关闭 Google 弹窗不一定有 GIS 回调，因此页面提示可以主动停止等待；不会声称取消等于关闭窗口或回滚已经完成的服务端开户事务。

真实 Google 弹窗、控制台受众限制、生产 PostgreSQL 竞争行为、Redis Lua 的实际部署权限及生产镜像尚需在隔离环境验收。本次不部署、不执行账户迁移、不修改共享 Supabase 数据。
