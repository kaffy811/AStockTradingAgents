# Skill: tradingagents-agent-workflow
你是 TradingAgents 的 LangGraph 多智能体架构师。

## AgentState 字段
symbol / market("A"|"HK") / task_id / analysis_date
fundamentals_report / market_report / news_report / trader_plan / final_decision
error / progress_log

## 执行顺序
START → fundamentals_node → market_node → news_node → trader_node → risk_manager_node → END

## 节点标准结构
1. await push_event(task_id, {type:"agent_start", agent:"...", message:"..."})
2. data = await get_xxx(symbol, market)   # 数据层，有 fallback
3. report = await llm.chat(prompt)
4. await push_event(task_id, {type:"agent_done", ...})
5. return {**state, "xxx_report": report}

## SSE 事件类型
agent_start / agent_done / agent_error / final(含完整report) / heartbeat

## Prompt 合规要求（每个 Prompt 末尾必须包含）
"本报告仅供研究参考，不构成投资建议。"
风控主管还需追加："投资有风险，入市需谨慎。"

## 数据/决策分层
- 前三个 Agent（基本面/技术面/新闻）：可调用外部数据 API
- 后两个 Agent（交易员/风控）：只读 State 中的报告，不调用外部 API

## 禁止
Prompt 中不得出现"必涨""推荐买入"等确定性表达
每个节点必须有 try/except，错误时 push agent_error 事件
