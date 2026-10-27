---
目前完成的工作汇总：

已完成

1. Phase 7C6 SSH 主机身份核验
- 从目标主机读取 ED25519 host key，并确认指纹与 Owner 已核验值 `SHA256:AeQr+HV5vMRgKGsKH7cN0hGzQStzDOe44dhFIsgaGsw` 精确一致。
- 使用临时专用 `known_hosts`、严格 host-key 校验和非交互模式，未降低 SSH 安全门禁。

2. Phase 7C6 部署认证门禁
- `kaffy` 与本地历史记录所指向的 `root` 账号均未接受现有非交互公钥凭据，连接在远端命令执行前停止。
- 未猜测密码或其他账号；未执行服务器预检查、拉取、构建、重启、migration、回滚或流量调整。

3. 部署证据交付
- 已生成 `backend/docs/artifacts/phase7c6_approved_chat_production_deployment.md`。
- 已生成 `backend/docs/artifacts/phase7c6_approved_chat_production_deployment.json`。
- 状态登记为 `APPROVED_AI_CHAT_SLICE_DEPLOYMENT_BLOCKED`，流量继续保持 `HOLD_1_PERCENT`。

---
下一步：你需要操作

第一步：为已登记服务器账号恢复当前工作机可用的非交互 SSH 公钥认证，或提供已配置 IdentityFile 的 SSH Host 别名；不要在聊天中发送密码或私钥。
第二步：认证恢复后，从 `/opt/tradingagents` 的只读预检查重新开始，核验 branch、HEAD、脏改、Compose 状态、资源和运行中的 Docker build。
第三步：仅在全部预检查通过后，按 backend 构建/重启/健康检查、frontend 构建/重启/健康检查的严格串行顺序继续部署；继续禁止 migration 与扩流。
