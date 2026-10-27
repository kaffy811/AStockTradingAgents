# HKNA 产品验收报告 9

## 1. 本次验收范围

审阅 Phase 7D Company/EOD/stock-research 技术门禁、Tushare 商业使用证据、本地 release 身份、已验证镜像平台及部署/回退边界。

## 2. 已完成内容盘点

- 本地 release 已整合并通过 tree 身份审计。
- Company 匿名公开字段、模块失败隔离、EOD、数值证据和主题 fail-closed 已落地。
- 纯镜像 Q1–Q4 与相关回归已有可追溯证据。
- 部署步骤已收敛为只读预检、镜像导入、后端/前端串行更新和单服务镜像回退。

## 3. 数据验收

### 3.1 新闻数据

- 未批准行业/主题新闻源保持 fail-closed。
- Tushare news 与公开抓取 Provider 不在本发布切片中。
- 当前状态：技术安全边界可用；行业主题新闻产品能力不可用。

### 3.2 股票数据

- 数据内容：Company profile、EOD 日线、估值、财务指标。
- 数据来源：批准范围内的 Tushare EOD；CNINFO 已持久化官方事实用于个股研究。
- 当前状态：技术验证通过，但公开商业使用权未证明。
- 主要问题：积分只证明接口访问，不证明公开展示、缓存、再分发或 AI 摘要授权。

## 4. 功能验收

- Company 页面：已完成并通过公开 DTO/故障隔离门禁；商业上线被数据授权阻塞。
- 个股 EOD 研究：已完成并具备请求级数字证据；商业上线被数据授权阻塞。
- 行业主题研究：受控 unavailable；不会调用未批准 Provider。
- 部署链路：方案已完成，尚未执行；目标服务器 CPU 架构仍需核对。

## 5. 当前产品阶段判断

技术候选与本地 release 已完成，处于商业授权和部署批准前的最终治理阶段。

## 6. 下一步任务部署

- P0：取得 Tushare 对公开展示、缓存/保存、再分发和 AI 摘要的书面授权。
- P0：确认目标服务器为 arm64；若为 amd64，在独立构建机生成并验证对应镜像。
- P1：Owner 分别批准 exact push 与串行部署。
- P2：商业授权后再评估行业新闻数据源，不得复用未批准 Provider。

## 7. 注意事项

- 不能把 Token 可调用或 2100 积分写成商业许可。
- 已验证镜像为 linux/arm64，不能直接导入 x86_64 服务器。
- 1.6GB 服务器禁止现场构建和并行更新。
- 不执行 migration、down、remove-orphans 或卷清理。
- AI 分析不能替代数据来源、as-of、延迟提示与免责声明。

## 8. 当前最建议立即推进的一步

向 Tushare 取得针对 aastock.cloud 具体用途的书面商业授权确认。

## 9. 附录

- Release: `98c111b684cb19de0e0e92cb46e1d675ef3e8d0a`
- Tree: `24a9961639dd7d8388fe8353a6e2e7eb8b955f03`
- 正式审阅：`backend/docs/artifacts/phase7d_p0_10_commercial_and_deploy_review.md`
- 官方协议：`https://tushare.pro/document/1?doc_id=405`
