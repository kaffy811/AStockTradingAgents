---
目前完成的工作汇总：

已完成

1. Google 登录后端
- 新增 Google 配置与登录接口、JWKS 签名校验服务。
- 校验 audience、issuer、有效期、已验证邮箱与 nonce；Redis 原子消费五分钟会话，防重复使用。
- 保留邀请码准入，老账户首次绑定必须验证原密码；后续按稳定 Google sub 登录，拒绝停用账户。
- 新增 google_sub 唯一字段及 Alembic 迁移，未修改线上数据库。

2. 登录体验与账户状态
- 登录页面中文化，增加 Google 官方登录按钮、邀请码输入及绑定说明。
- Google 脚本加载失败提示和重试；密码登录继续可用。
- 统一两种登录方式的会话保存，清理旧账户管理员显示状态。

3. 配置与文档
- 环境变量示例添加 GOOGLE_CLIENT_ID，README 链接 docs/GOOGLE_LOGIN.md。
- 部署说明覆盖 Google Console 来源、HTTPS、同域代理、Redis、数据库迁移和真实验收。

4. 验证
- Google 身份相关后端测试 12 项通过。
- 前端现有测试 69 个文件、764 项通过。
- 前端生产构建通过，保留现有 ECharts 大包提示。
- git diff --check 通过。未进行真实 Google 授权、线上迁移或服务器部署。
- 保留工作区原有改动，未提交或推送。

---
下一步：你需要操作

第一步：在 Google Cloud Console 创建 Web OAuth Client ID，配置实际来源与测试用户。
第二步：后端 .env 设置 GOOGLE_CLIENT_ID；正式环境使用 HTTPS 域名，APP_ENV=production，前端 VITE_API_BASE=/api/v1。
第三步：备份数据库后在项目根目录执行 docker compose build、docker compose up -d redis、docker compose run --rm migrate、docker compose up -d backend frontend。
第四步：按照 docs/GOOGLE_LOGIN.md 完成真实 Google 注册、绑定、再次登录和退出重登验收。
