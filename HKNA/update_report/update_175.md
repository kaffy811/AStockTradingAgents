---
目前完成的工作汇总：

已完成

1. 核对并保留既有工作。
- 先检查 Git 状态与当前 HEAD（98c111b684cb19de0e0e92cb46e1d675ef3e8d0a），保留 Google 登录、行情/缓存及其他未提交修改。
- 重跑用户指定五组后端测试，初次 123 passed；前端 71 files / 784 passed，生产构建成功。未重复实现 cache_service 或 stocks.py 中的现有修复。

2. 修复即时模型失败被误标成功的遗漏。
- backend/app/agents/comprehensive_analysis_coordinator.py：技术面+基本面合成增加可选 propagate_failure，默认仍返回既有 fallback，避免破坏其他调用方。
- backend/app/agents/realtime_analysis_runner.py：实时合成选择异常传递，使即时 PROVIDER_TIMEOUT/普通异常也由 runner 统一降级；metadata.synthesis=degraded、metadata.partial=true、warnings 与 synthesis_completed.degraded 保持一致，分项内容和保存流程继续执行。
- 不新增重试、替换模型或移除数字校验。既有 max_retries=0 和综合等待截止保持原样。

3. 降级报告标签本地化。
- comprehensive_analysis_coordinator.py 复用 report_label 显示维度，避免输出 technical/news 等内部键。
- backend/app/agents/language_utils.py 补充六种语言的正常生成/暂不可用标签。
- 分项全文仍保存在 sections，fallback 摘要保留维度状态；历史报告不会被自动改写。

4. 回归与构建结果。
- backend/tests/test_analysis_report_resilience.py 新增 11 项，覆盖实际合成函数立即失败、两种分析范围、超时/普通异常、旧调用方 fallback、六语言标签。
- 用户指定五组后端测试最终 134 passed，1 warning，1.48s；原有 market I/O 回归包含在内。
- 保存/历史/事务相关三组测试 55 passed，22 warnings，10.21s；均为 mock/契约测试，不代表真实数据库端到端验收。warnings 为旧 AsyncMock/后台协程清理与 passlib 弃用提示。
- 前端 71 files / 784 passed，6.58s；npm run build 成功，972 modules，6.29s。Vite CJS/大 chunk 警告仍在。
- git diff --check 通过。补充测试最初错误期待 fallback 内嵌分项全文，已按原有 sections 保存契约修正，最终测试通过。

5. 真实验收与部署边界。
- 只检查了配置存在性：模型 key 有配置，但没有真实验证其有效性；当前数据库指向 Supabase。SDK 请求超时实际为 90s，综合等待上限为 60s，后者不能强杀已启动线程。
- 已请求隔离测试数据库和测试账号；未收到这些信息，未对 CN/600519 或第二标的调用付费模型/外部行情，未向 Supabase 写测试报告。
- 未修改生产、数据库、DNS 或 Vercel，未提交或推送。服务器源码版本未知，不打包声称可直接上线的分析补丁。
- 更新 docs/ANALYSIS_RESILIENCE.md 记录实际结果与限制。现有 market-io-fix-v1 补丁仅含行情缓存修复，不能视作本次分析报告发布包。

---
下一步：你需要操作

第一步：提供隔离验收环境。
- 指定测试数据库和测试账号，在该环境使用有效现有模型配置分别运行 CN/600519 与 CN/000001，核对中文/标签、真实耗时、失败降级、保存后重开历史。
- 当前本地配置连接 Supabase，未确认隔离前不要写入测试报告；离线测试不能替代这项验收。

第二步：核对线上基线后准备发布产物。
- /opt/tradingagents 记录 git rev-parse HEAD 与 git status --short，并提供涉及文件的服务器实际源码；保留 .env.staging.local 和服务器配置修改。
- 基于核实后的源码整理包含分析修复的增量，在 Mac/CI 按服务器架构构建镜像；不要直接发布当前混有其他功能的工作区，也不要误用仅含行情修复的旧补丁。

第三步：按现有三份 Compose 发布与回滚。
- 项目名 aastock-mvp；使用 docker-compose.yml、docker-compose.staging.yml、docker-compose.mvp-server.yml。
- 发布前备份源码与旧镜像 ID，仅更新 backend/frontend，使用 --no-deps，不运行迁移、down、--remove-orphans 或数据库重建。
- 回滚恢复旧镜像及本次源码增量，再仅更新前后端容器，不回退数据库。真实验收及线上兼容核对完成前，不标记上线验收通过。
