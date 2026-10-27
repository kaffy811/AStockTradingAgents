---
目前完成的工作汇总：

已完成

1. 本地登录故障定位
- 实际 Google 请求返回数据库 UndefinedColumnError：app_users.google_sub 不存在。
- 仅本地服务启动成功不能证明数据库迁移已完成，当前共享 Supabase 的结构不匹配。

2. 本地连接与错误提示
- Vite 增加 /api 到 127.0.0.1:8000 的同源代理。
- 本机 .env.local 的 VITE_API_BASE 改为 /api/v1，避免跨域错误响应被浏览器遮蔽。
- Google 配置与登录也复用 readJsonResponse，避免非 JSON 响应解析崩溃。
- 同源代理配置接口返回 HTTP 200。未改数据库、未部署生产。

---
下一步：你需要操作

第一步：刷新 http://localhost:3000/login。
第二步：确认是否允许对当前共享 Supabase 执行 Google 身份字段迁移，或改用隔离测试数据库。未经确认不执行共享数据库迁移。
第三步：字段迁移完成后验证密码登录、Google 首次绑定和再次登录。
