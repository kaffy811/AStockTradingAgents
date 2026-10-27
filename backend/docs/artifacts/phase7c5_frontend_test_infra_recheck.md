# Phase 7C5 Frontend Test Infrastructure Pre-Deploy Recheck

## 结论

`BLOCKING_PRE_DEPLOY_TEST_INFRA_RECHECK` 已完成复验并闭环。本轮属于情况 A：低并发完整套件连续两次实现 756 passed、0 failed、0 worker startup timeout。

当前 release gate 标准命令：

```text
cd frontend
npm test -- --pool=forks --maxWorkers=1 --no-file-parallelism
```

不再将未限制并发的默认 `npm test` 称为稳定发布门禁命令。本轮无需修改 Vitest 配置、package scripts、测试 setup/teardown 或业务代码。

## 运行基线与环境

```text
branch: release/demo-staging
HEAD: 5dad7228bb7b54338a946b49daeee5eae58348f9
candidate tree: 0981783304376eed46a6a3276950aa95511f3b69
diagnostic worktree: /private/tmp/TradingAgents-phase7c5
worktree mode: detached clean
Node: v22.15.0
npm: 10.9.2
Vitest: 4.1.9 darwin-arm64
platform: darwin arm64
logical CPU cores: 14
total memory: 25769803776 bytes (24 GiB)
```

macOS `sysctl` 在受限沙箱中不可读，CPU 和内存由 Node `os` API 记录。每次命令前的可用内存见运行矩阵。

## 现有测试配置审计

`frontend/package.json`：

```json
{
  "scripts": {
    "test": "vitest run",
    "build": "vite build"
  }
}
```

`frontend/vite.config.js` 的 Vitest 配置：

```text
environment = jsdom
globals = true
include = src/tests/**/*.test.js
```

现有配置没有显式指定 `pool`、`maxWorkers`、`minWorkers`、`fileParallelism`、`testTimeout`、`hookTimeout` 或 `teardownTimeout`。Vitest 4.1.9 CLI 显示默认 pool 为 `forks`、默认开启 file parallelism、test timeout 为 5000 ms、hook timeout 为 10000 ms。

## 运行矩阵

| 运行 | 命令 | Pool / worker | Collected | Passed | Failed | Worker startup timeout | Duration | 运行前可用内存 |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 默认完整套件 | `npm test` | default forks / auto workers / parallel files | 756 | 756 | 0 | 0 | 5.41 s | 195346432 B |
| 低并发完整套件 #1 | `npm test -- --pool=forks --maxWorkers=1 --no-file-parallelism` | forks / 1 / serial files | 756 | 756 | 0 | 0 | 20.07 s | 1244921856 B |
| Chat Research UI 专项 | `vitest run src/tests/researchFulfillment.test.js --pool=forks --maxWorkers=1 --no-file-parallelism` | forks / 1 / serial files | 16 | 16 | 0 | 0 | 0.315 s | 1037025280 B |
| Production build | `npm run build` | N/A | 971 modules | N/A | 0 | 0 | 2.67 s | 1007009792 B |
| 低并发完整套件 #2 | 同 #1 | forks / 1 / serial files | 756 | 756 | 0 | 0 | 20.08 s | 979632128 B |

所有命令严格串行，无强制终止。两次完整低并发套件都是 67/67 测试文件通过。

## 超时归因

直接证据支持“运行环境资源争用”：

1. 上次 12 个 worker timeout 发生时，完整前端套件与前端构建、三组后端 pytest 并行运行，且同期进行过容器核验。
2. 超时均为 `Failed to start forks worker` / `Timeout waiting for worker to respond`，发生在测试文件执行前；已启动的 615 项没有业务断言失败。
3. 本轮在相同 HEAD、Node、Vitest 和测试代码上，取消外部并行负载后，默认套件即通过。
4. 显式限制为单 worker 后连续两次完整通过，零 worker timeout。

没有证据指向 Vitest config 语法、test setup、环境变量、模块 import 或测试泄漏错误，因此不创建 test-infra 修复提交。

## Release Gate

```text
FRONTEND_FULL_SUITE_COMMAND=npm test -- --pool=forks --maxWorkers=1 --no-file-parallelism
required_test_files=67
required_tests=756
allowed_failed=0
allowed_worker_startup_timeouts=0
```

发布流程中必须单独、串行执行该命令，不得与容器构建、前端 build 或后端完整回归并行。任何强制终止、worker startup timeout、未收集完整 67 个文件或测试数低于 756，均不得记为通过。

## 边界

- 未修改 package scripts、Vitest config、test setup/teardown 或任何业务代码。
- 未修改 Chat UI、CNINFO、Tushare Gateway、Provider、Docker、依赖、migration、Company V2、LLM/RAG/numeric/citation。
- 未 push、部署、执行 production migration 或扩流。
