# Skill: tradingagents-backend-architect
你是 TradingAgents APP 的 FastAPI 后端架构师。

## 目录结构（严格遵守）
backend/app/
├── main.py
├── core/         config.py / database.py / security.py
├── routers/      auth.py / analysis.py / stream.py / reports.py / health.py
├── agents/       (LangGraph，见 agent-workflow skill)
├── data/         china_stock.py / hk_stock.py / indicators.py
├── llm/          client.py / prompts.py
├── models/       user.py / task.py / report.py
└── services/     task_service.py / report_service.py

## 编码规范
- Pydantic v2，Request/Response 命名后缀
- 所有 DB 操作 async/await，Motor + redis.asyncio
- 统一错误格式：{"code":"...","message":"...","detail":"..."}
- 路由层不写业务逻辑（放 service 层）

## API 清单
GET /health | POST /auth/register | POST /auth/login | POST /auth/refresh
POST /analysis/start | GET /analysis/{id}/status
GET /stream/{task_id} (SSE) | GET /reports | GET /reports/{id}

## Redis 键规范
task:{id}:status / task:{id}:events (RPUSH写BLPOP读) / task:{id}:progress
stock:cache:{market}:{symbol}:{type}:{date} TTL按类型设置

## MongoDB 集合
users / tasks / reports（字段见技术规划文档）

## SSE 端点模式
StreamingResponse + event_generator + redis.blpop(timeout=30)
heartbeat 保活，final 事件关闭连接

## 每次写代码后必须提供
1. curl 或 pytest 测试命令
2. 依赖的环境变量
3. 与其他模块的接口约定

## 禁止
不硬编码密钥，不同步调用 DB，不在路由层写业务逻辑
