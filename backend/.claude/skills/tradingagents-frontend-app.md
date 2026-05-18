# Skill: tradingagents-frontend-app
你是 TradingAgents APP 的 UniApp + Vue3 前端工程师。

## 页面清单
login/index.vue      → 邮箱+密码，登录/注册tab，成功存token跳首页
home/index.vue       → 大号输入框，A股/港股选择，开始分析按钮，近3条历史
analysis/progress.vue → SSE驱动的Agent时间轴（5个节点状态+耗时）
analysis/report.vue  → 4个Tab（基本面/技术面/新闻/综合），Markdown渲染，底部合规声明
history/index.vue    → 列表（股票名、时间、市场标签），点击进报告页

## SSE 接入（sse.js）
H5环境用原生 EventSource
小程序环境降级为轮询 /analysis/{taskId}/status
解析 type: agent_start/agent_done/final/heartbeat/agent_error

## Markdown 渲染
marked.js + DOMPurify，v-html 渲染，引入 github-markdown-css

## 合规声明（每个报告页底部必须包含，不可隐藏）
"⚠️ 本报告由 AI 多智能体系统自动生成，仅供学习研究参考，不构成任何投资建议。"

## Token 管理
统一通过 utils/token.js 的 uni.setStorageSync/getStorageSync 存取
不存 URL 参数，不存明文密码

## 禁止
报告页不得出现买入/卖出操作按钮
不直接调用数据源 API
