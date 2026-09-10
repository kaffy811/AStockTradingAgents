---
目前完成的工作汇总：

已完成

1. 真实 Tushare EOD 数值链路归因
- 从 `98c111b…` 创建隔离分支和 worktree，使用一次限时、无 Provider 重试的真实 probe 核对 `600519.SH` 响应形状。
- 确认日线/估值日期、财务报告期、PE/PB/ROE 单位与精度正确；未记录 Token、请求头或 Provider 原始 body。

2. 首个根因与最小修复
- 定位到 EOD 回答混入 CNINFO 公告标题年份，标题中的 `2026` 没有 stock-EOD evidence ID，导致 validator 正确 fail-closed。
- 将 stock EOD 路由与公告/Report 路径解耦；没有关闭、跳过或放宽 numeric validator。
- 增加 metric/module 的严格单位契约，错误单位无法生成请求级 evidence。

3. 脱敏 fixture 与回归测试
- 新增真实 Provider 标准化形状 fixture，覆盖收盘价、PE、PB、ROE、报告期、不同精度和 `600519.SH` 代码映射。
- 两个目标问题均为 `fulfilled`，`numeric_validation.valid=true`、18/18 claims 有 evidence、unsupported tokens 为空。
- exact Q4 仍为 `unavailable / NO_APPROVED_INDUSTRY_NEWS_SOURCE`，LLM 与所有 Provider 调用为 0。

4. 前端状态一致性
- 保持 `fulfilled`、`partial`、`unavailable` 的既有真实状态映射；相关前端测试通过，production build 通过。

---
下一步：你需要操作

第一步：Owner 审阅本提交的路由解耦边界，确认 EOD 请求不再附带 CNINFO 公告标题，公告研究继续使用原有专用路由。

第二步：审阅脱敏 runtime JSON 中 live probe 与 controlled replay 的明确区分，不把 fixture 回放写成额外 live Provider 验收。

第三步：Owner 批准后再进入独立 merge/deploy 阶段；当前不 push、不 merge、不部署、不 migration、不扩流。
