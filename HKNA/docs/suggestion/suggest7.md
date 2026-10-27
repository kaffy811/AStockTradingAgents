# HKNA 产品验收报告 7：纯提交候选镜像已就绪

## 1. 本次验收范围

验收 `b055da8` 对应的独立 worktree、候选 backend image、源码 hash、OCI revision、import 与 secret 扫描。

## 2. 已完成内容

- `tradingagents-backend:rc-b055da8` 可追溯到 Git revision `b055da8`。
- 候选镜像不含既有 dirty warmup、embedding、dependency、lockfile 或模型预载改动。
- trace durability、Report Chat 及 migration 模块可正常 import。
- 当前 production container 未被替换或重启。

## 3. 当前产品阶段

已具备隔离候选运行时验证条件，但尚未部署候选镜像，也未证明 numeric failure 的主导根因。

## 4. 下一步任务

在隔离候选环境以 `rc-b055da8` 执行受控财报问题，使用 durable trace 对 numeric-invalid token 逐项归因。测试环境应使用独立 Redis namespace、非生产 API 入口和受控写入边界；不得接入用户流量或替换 1% 容器。

## 5. 发布建议

维持 `HOLD_1_PERCENT`。候选镜像准备完成不等于部署完成；仅在新 trace 明确主导根因、完成最小修复与候选运行时回归后，才可评估新的发布门禁。
