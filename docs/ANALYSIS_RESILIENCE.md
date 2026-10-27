# 分析报告故障修复与上线验收

## 本地确认

Redis 基础 PING 正常不能证明主事件循环内的缓存桥接安全。工作区现有缓存修复已包含目标循环线程保护、超时取消以及行情接口的线程卸载；本次运行 `test_market_io_resilience.py` 验证相关行为，没有覆盖或重新实现这些已有改动。

用户报告的技术面错误包含 PROVIDER_TIMEOUT，说明该维度在模型请求阶段失败，不能由此推断原始 K 线缺失。此次改动将错误原因与数据缺失分开显示；综合摘要失败时保留分项报告，metadata.synthesis 标记 degraded，metadata.warnings 提示降级。

## 等待与重试

- DeepSeek OpenAI SDK 客户端显式 `max_retries=0`，避免默认 SDK 重试将单次请求超时乘倍。瞬时故障因此可能直接失败，用户可稍后重新分析；没有自动更换模型或新增付费请求。
- 原有 `PI_REAL_PROVIDER_TIMEOUT_SECONDS` 仍控制 SDK 请求超时。
- 新增 `ANALYSIS_SYNTHESIS_TIMEOUT_SECONDS`，默认 60 秒，允许 0 到 300 秒之间的正值。实时分析综合生成阶段受此等待上限约束，包括技术面+基本面组合范围。
- 这是综合生成阶段上限，不是整个分析的总时限；数据获取和各分析维度仍受各自原有策略约束。
- asyncio 超时可结束等待，但不能强行终止已经启动的同步线程。SDK 调用仍由自身超时约束。本次没有宣称取消等于底层调用已停止。

## 内容与显示

默认中文报告也显式注入中文指令，并要求事实、分析、局限、观察项使用目标语言标签，禁止自行单位换算和新增未经证据支持的计算。保留现有数字验证，不通过移除校验来恢复被拒绝的数字。

已有报告中的英文和“未提供数字”不会自动修复；需重新生成。语言指令不能保证模型绝对遵守，也不等于修复全部原始财务字段覆盖问题。报告覆盖度是依据报告内容与执行状态的启发式估计，不代表原始数据准确率。

## 验证与上线

本次先做本地修复，未更新线上服务、数据库、DNS 或 Vercel。

测试命令：

```sh
backend/.venv/bin/python -m pytest backend/tests/test_analysis_report_resilience.py backend/tests/test_market_io_resilience.py backend/tests/test_c14_deepseek_client.py backend/tests/test_phase6w_r2_6_synthesis_optimization.py backend/tests/fundamental/test_phase6u_specialist_analysis.py -q
cd frontend
npm test
npm run build
```

上线前应在本地使用有效模型配置，分别分析 CN/600519 和另一个标的，核对语言、真实请求耗时、模型失败降级、报告保存及重开历史记录。此操作会调用模型和外部行情源，不能用离线模拟测试结果代替。

服务器仍按 `/opt/tradingagents`、项目名 `aastock-mvp` 和三份既有 Compose 配置更新。先核对线上源码与待发布版本，再打包补丁或构建镜像；保留 `.env.staging.local` 与服务器配置改动。本次不需要数据库迁移。不要运行 down 或 remove-orphans，因为现有 PostgreSQL 容器不在当前服务定义内。

建议优先在 Mac/CI 构建可部署产物，避免 2 GB 服务器同时构建多个镜像。发布前记录旧镜像 ID 并备份源码；回滚时恢复旧镜像及本次修改文件，然后只重建前后端容器，不回退数据库。

## 补充验收（2026-10-26）

复查发现技术面+基本面合成函数内部捕获即时模型异常并返回 fallback，实时 runner 原先不能据此识别失败，可能将 metadata.synthesis 标记为 success。现在该函数默认行为保持不变，实时 runner 显式选择异常传递，由外层统一保留分项报告、标记 degraded/partial、写入 warnings 并发出降级事件。不是只测试人为挂起后的 asyncio 超时：新增测试通过真实合成函数模拟立即返回的 PROVIDER_TIMEOUT 和普通异常，并确认不会新增模型调用。

降级报告原先直接输出 technical/news 等内部键及固定中文状态。现已复用六种语言的维度标签，并补充“正常生成/暂不可用”的翻译。已有分项全文仍保存在 sections，fallback 摘要不复制全部分项；本次不改写已保存的历史报告，不修改数字验证。

本轮实测：

- 上述五组后端测试：134 passed，1 个既有 passlib 弃用警告，1.48 秒；新增分析报告回归 11 项。
- 另跑 test_c12_analysis_save_history_e2e.py、test_c302_routing_and_persistence.py、test_c303_transaction_safety.py：55 passed，22 warnings，10.21 秒。其保存/历史行为使用 mocks 与契约校验，不代表真实数据库保存和重开已经通过；warnings 涉及旧测试 AsyncMock/后台协程清理及 passlib 弃用。
- 前端 npm test：71 个文件、784 passed，6.58 秒。
- 前端 npm run build：成功，972 modules，6.29 秒；仍有 Vite CJS API 和大 chunk 警告。
- git diff --check：通过。缓存桥接与行情接口既有修复未重新实现。

真实验收尚未执行。本地仅核对配置存在性，没有输出 API key 或数据库凭据，也没有验证 key 的真实有效性。当前数据库地址指向 Supabase，实际 SDK 请求超时为 90 秒，综合阶段等待上限为 60 秒。真实分析 CN/600519 和另一个标的（可选 CN/000001）、报告保存及重新打开历史，需提供隔离测试库和测试账号后进行；不能让本地验收向可能共用的线上 Supabase 写入测试报告。尚未调用付费模型或外部行情，也没有修改线上、DNS、Vercel。

现有 deployment/market-io-fix-v1/market-io.patch 仅包含行情与缓存修复，**不包含本次分析报告修改**。服务器当前源码版本仍未核对，故本轮未制作或宣称已验证可上线的分析报告补丁，也未构建发布镜像。应先取得服务器当前 commit、修改清单及相关源码，再按该版本整理发布增量，在 Mac/CI 构建与服务器架构相符的产物。保留原有三份 Compose、.env.staging.local、Supabase 和不在服务定义中的 PostgreSQL 容器；仅更新前后端，不运行迁移或全量容器清理。
