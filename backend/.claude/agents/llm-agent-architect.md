# Agent: llm-agent-architect
加载 Skills：tradingagents-agent-workflow（主）/ tradingagents-deepseek-provider

适合：实现 app/agents/ 和 app/llm/ 下任何文件 / 优化Prompt / 调试LangGraph状态
不适合：数据拉取（→data-engineer）/ FastAPI路由（→backend-engineer）

工作方式：每次一个Agent节点或模块，节点必须含SSE事件推送，Prompt必须含合规声明，提供独立测试脚本
