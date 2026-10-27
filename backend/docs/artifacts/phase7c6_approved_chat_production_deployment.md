# Phase 7C6 — Approved AI Chat Slice Production Deployment

## 结论

`APPROVED_AI_CHAT_SLICE_DEPLOYMENT_BLOCKED`

记录时间：`2026-09-03T04:06:38Z`

本次部署在 SSH 认证门禁处停止。未进入服务器，未执行代码拉取、Docker 构建、容器重启、migration、流量调整或回滚。线上现场保持不变，流量状态继续为 `HOLD_1_PERCENT`。

## 已核验证据

- 目标：`GitHub release/demo-staging@5dad7228bb7b54338a946b49daeee5eae58348f9`
- 本地主分支：`release/demo-staging`
- 本地 HEAD：`5dad7228bb7b54338a946b49daeee5eae58348f9`
- 通过 `ssh-keyscan -t ed25519 aastock.cloud` 获取的 ED25519 指纹与 Owner 已核验指纹一致：`SHA256:AeQr+HV5vMRgKGsKH7cN0hGzQStzDOe44dhFIsgaGsw`
- 连接强制使用临时专用 `known_hosts`、`StrictHostKeyChecking=yes` 和 `BatchMode=yes`。
- 本地历史记录表明既有服务器操作使用 `root@43.108.58.137`，并确认既有 Compose 组合为 `aastock-mvp` + `docker-compose.yml` + `docker-compose.staging.yml` + `docker-compose.mvp-server.yml` + `.env.staging.local`；本轮没有读取任何环境变量值。

## 阻断证据

以下两个非交互认证尝试均在执行任何远端命令前被拒绝：

1. `kaffy@aastock.cloud`: `Permission denied (publickey,password)`
2. `root@aastock.cloud`: `Permission denied (publickey,password)`

未继续猜测用户名、密码或认证材料，也未降低 host-key 校验等级。

## 未执行门禁项

由于无法建立已认证 SSH 会话，下列项目无法核验或执行：

- `/opt/tradingagents` 的 branch、HEAD、工作区脏改、Compose 状态、内存和磁盘预检查；
- 正在运行的 Docker build 排查；
- 保留并记录服务器 `docker-compose.staging.yml` 脏改与 `.env` 备份；
- fetch、祖先关系检查和 `merge --ff-only`；
- backend/frontend 串行构建与重启；
- 容器、localhost 与公网健康检查；
- 最近日志、migration 未执行和重启次数核验。

## 安全状态

- production migration：未执行
- migrate 容器：未执行
- Docker build：未执行
- backend/frontend 重启：未执行
- `docker compose down` / `--remove-orphans` / prune：未执行
- 服务器脏改、Token、`.env`、数据库、Redis：未修改
- 流量扩展：未执行
- 当前流量门禁：`HOLD_1_PERCENT`

## 解除阻断条件

Owner 需先为已登记的服务器账号恢复可用的非交互 SSH 公钥认证，或提供已经配置好的 SSH Host 别名/IdentityFile。认证恢复后必须从服务器预检查重新开始，不得跳过任何部署门禁。
