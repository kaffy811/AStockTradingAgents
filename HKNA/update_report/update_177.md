---
目前完成的工作汇总：

已完成

1. 用户批准后的共享 Supabase 单步迁移
- 只读确认原数据库版本为 r6s7t8u9v0w1，且 google_sub 字段不存在。
- 执行 backend/.venv/bin/alembic upgrade s7t8u9v0w1x2 成功。
- 迁移仅新增可空 app_users.google_sub VARCHAR(255) 及 uq_app_users_google_sub 唯一约束，维护 Alembic 版本；不更新或删除现有账户记录。
- 未执行其他迁移，未部署服务器代码。

---
下一步：你需要操作

第一步：刷新 http://localhost:3000/login，重新发起登录以获取新 nonce。
第二步：已有邮箱账户首次绑定 Google 时先填写原账户密码，再点击 Google 按钮；也可先使用密码登录测试报告。
第三步：若仍出错，提供页面提示，继续结合本地后端日志排查，不重复执行迁移。
