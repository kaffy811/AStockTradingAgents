# TradingAgents — Release Candidate 总结

> 版本：RC（Phase M43 收口）  
> 日期：2026-06-09  
> 状态：✅ Release Candidate — 关键链路全验证通过

---

## 1. RC 版本范围

本 RC 版本覆盖 Phase M1 至 M44，以 M43 多 worker 压测通过为里程碑，标志项目进入可部署状态。

**不包含**：生产环境线上部署（无真实域名/线上地址）。

---

## 2. 已完成功能清单

### 后端 API

| 功能 | 路由 | 状态 |
|------|------|------|
| 用户注册/登录 | `POST /auth/register`, `/auth/login` | ✅ |
| JWT 认证 | `GET /auth/me` | ✅ |
| 股票搜索 | `GET /stocks/search` | ✅ |
| 股票行情 + 详情 | `GET /stocks/{market}/{symbol}/profile` | ✅ |
| K 线数据 | `GET /stocks/{market}/{symbol}/kline` | ✅ |
| 行业热门股 | `GET /industries/hot` | ✅ |
| 自选股 CRUD | `GET/POST/DELETE /watchlist` | ✅ |
| 综合分析（阻塞） | `POST /analysis/comprehensive-v2` | ✅ |
| 分析 Run 创建 | `POST /analysis/runs` | ✅ |
| SSE 事件流 | `GET /analysis/runs/{id}/events` | ✅ |
| Run 取消 | `POST /analysis/runs/{id}/cancel` | ✅ |
| 报告保存 | `POST /reports/` | ✅ |
| 报告列表 | `GET /reports/` | ✅ |
| 报告详情 | `GET /reports/{id}` | ✅ |
| 报告删除 | `DELETE /reports/{id}` | ✅ |
| 股票对比数据 | `GET /stocks/compare` | ✅ |

### 前端页面

| 页面 | 路由 | 状态 |
|------|------|------|
| 首页研究仪表盘 | `/` | ✅ |
| 综合分析页 | `/analysis` | ✅ |
| 股票详情页 | `/stocks/:market/:symbol` | ✅ |
| 自选股工作台 | `/watchlist` | ✅ |
| 行业热度研究 | `/industry` | ✅ |
| 报告中心 | `/history` | ✅ |
| 报告详情 | `/history/:id` | ✅ |
| 我的研究中心 | `/profile` | ✅ |
| 股票对比 | `/compare` | ✅ |
| 打印报告 | `/print/:id` | ✅ |

### 系统能力

| 能力 | 状态 | 说明 |
|------|------|------|
| SSE 实时分析进度 | ✅ | event_id 单调递增，断线 replay |
| custom_coordinator 引擎 | ✅ | 默认，稳定基线 |
| LangGraph 引擎 | ✅ | env 灰度（G2），shape 100% 兼容 |
| Memory Run Registry | ✅ | 单 worker dev 默认 |
| Redis Run Registry | ✅ | 多 worker 生产，M43 16/16 PASS |
| 6 种 UI 语言 | ✅ | zh-CN / zh-TW / en-US / ja-JP / ko-KR / de-DE |
| 6 种报告语言 | ✅ | output_language 独立，Agent-level 透传 |
| 3 套 UI 主题 | ✅ | light-holo / dark-dive / paper-lilac |
| 移动端 PWA 风格 | ✅ | BottomTabBar，≤640px 响应式 |
| Docker Compose 部署 | ✅ | 4 服务，Nginx 反向代理 |

---

## 3. 核心架构能力

```
1. AnalysisRunRegistry 抽象层（ABC）
   Memory → 单 worker / dev
   Redis  → 多 worker / 生产（4键/run: Hash, List, INCR, PubSub）

2. 双 engine 灰度
   explicit body.engine > DEFAULT_ANALYSIS_ENGINE > "custom_coordinator"
   非法 env fallback，服务不崩

3. SSE 可靠性
   asyncio.shield 心跳防止 generator 提前关闭
   event_id replay 支持断线恢复

4. output_language 解耦
   UI i18n 与 AI report 语言独立，Agent-level prompt 透传

5. 多 Agent 并行
   4 个专项 Agent + synthesis LLM
   asyncio.gather（CC）/ Send API fan-out（LG）
```

---

## 4. 验证结果摘要

| 验证项 | 结果 |
|--------|------|
| 14 项运行时回归（M40-c）| ✅ 14/14 PASS |
| 6 case LangGraph 灰度决策（M41）| ✅ 6/6 PASS，ratio 0.97x |
| 8 case env 灰度矩阵（M42）| ✅ 8/8 PASS |
| 4-worker 并发压测 × CC（M43）| ✅ 8/8 PASS |
| 4-worker 并发压测 × LG（M43）| ✅ 8/8 PASS |
| 报告保存全链路（M43-7）| ✅ PASS |
| npm run build（M43-8）| ✅ 195 modules |

---

## 5. 多 worker 压测结果

| 配置 | workers | runs | concurrency | terminal_event | event_id dedup | result |
|------|---------|------|-------------|----------------|----------------|--------|
| Redis + custom_coordinator | 4 | 8 | 4 | 全为 report_ready | 无重复 | **PASS** |
| Redis + langgraph | 4 | 8 | 4 | 全为 report_ready | 无重复 | **PASS** |

脚本：`backend/scripts/smoke_multi_worker_runs.py`

---

## 6. 已知限制

| 限制 | 影响 | 说明 |
|------|------|------|
| 分析耗时 20-180s | 用户体验 | LLM 速度绑定；SSE 进度缓解等待感 |
| asyncio.to_thread 不可强制取消 | 取消语义 | "停止等待"，非中断；后台线程自然结束 |
| 港股 stock_master 约 30 只 | 港股覆盖 | 主流港股已覆盖；长尾 fallback AkShare |
| Redis event_maxlen 淘汰 | 极长分析 replay | 默认 500 事件；可通过 env 调大 |
| AkShare/Sina 接口稳定性 | 数据时效 | 第三方接口；超时已有降级路径 |
| LangGraph Send API 版本耦合 | 升级风险 | 升级时需验证 fan-out 行为 |

---

## 7. 推荐部署配置

### 生产多 worker

```yaml
# docker-compose.yml backend environment:
- REDIS_URL=redis://redis:6379
- ANALYSIS_RUN_REGISTRY=redis
- APP_ENV=production
- DEBUG=false
# DEFAULT_ANALYSIS_ENGINE=custom_coordinator  # 默认不需要设置
```

```bash
# 后端启动（4 worker）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### staging 灰度 LangGraph

```yaml
- DEFAULT_ANALYSIS_ENGINE=langgraph
```

### 单 worker 开发

```bash
uvicorn app.main:app --reload --port 8000
# ANALYSIS_RUN_REGISTRY 不设置，默认 memory
```

---

## 8. 推荐演示配置

```bash
# 单 worker 演示（最简单）
uvicorn app.main:app --port 8000

# 多 worker 演示（展示 Registry 设计）
ANALYSIS_RUN_REGISTRY=redis uvicorn app.main:app --workers 4 --port 8000

# LangGraph 演示
DEFAULT_ANALYSIS_ENGINE=langgraph uvicorn app.main:app --port 8000
# 或 dev_mode + EngineSelector 手动切换
```

演示流程参见 [`docs/demo_walkthrough.md`](demo_walkthrough.md)  
演示检查清单参见 [`docs/demo_checklist.md`](demo_checklist.md)

---

## 9. Post-RC Roadmap — OpenClaw-inspired Chat Copilot（2026-06-18 更新）

### 下一代产品方向

RC 完成后，项目进入 **Phase C 系列（Chat Copilot）**，在现有工作台基础上构建 OpenClaw-inspired 金融智能 Agents 系统。

**核心价值：** 从"用户自己找功能"变成"用户提出研究目标，Agent 调用工具完成任务"。Chat Copilot 是金融垂直场景的 Agent Orchestrator，工作台页面成为 Agent 的数据基座和结果落地层。

**阶段规划（已完成 + 规划中）：**

| 阶段 | 内容 | 状态 | OpenClaw 层级 |
|------|------|------|--------------|
| C1 | PRD + 架构设计（6 文档）| ✅ 完成 | 设计 |
| C2 | Chat UI MVP（`/chat`，8 组件，6 语言，213 modules）| ✅ 完成 | Chat Channel |
| C3 | Chat API（session + messages，DB migration d7e3a9b5c2f8，6 端点）| ✅ 完成 | Chat Channel |
| C4 | Tool Registry（9 只只读工具，BaseTool→ToolResult→ToolRegistry，11/11 PASS）| ✅ 完成 | Tools 工具层 |
| C5 | Action Tools + ConfirmationManager 真实执行 | ✅ 完成 | Action 执行层 |
| C6 | Financial Skills Layer（6 只金融研究技能）| 规划中 | Skills 技能层 |
| C7 | Planner + 多步骤任务编排（最多 5 步）| 规划中 | Planner 任务规划 |
| C8 | Memory + Audit Hardening | 规划中 | Memory + Audit 层 |
| C9 | OpenClaw-style Skill Registry（可扩展框架）| 规划中 | 全层整合 |

**安全要求（永久）：**
- 不输出买入/卖出/持有/目标价
- 所有写操作需用户确认
- 不支持真实交易

**相关文档：**
- `docs/chat_agent_prd.md` / `docs/chat_agent_architecture.md`
- `docs/chat_agent_tool_spec.md` / `docs/chat_agent_build_plan.md`
- `docs/chat_agent_skills.md`（6 只 Financial Skills 完整规范）
- `docs/openclaw_inspired_roadmap.md`（导师版技术路线图）

---

## 10. 后续低优先级路线

| 优先级 | 项目 | 条件/说明 |
|--------|------|----------|
| G4（低）| LangGraph 升为生产默认 | staging 稳定 1-2 周 + 50 次 comprehensive 无异常 |
| 低 | 港股 stock_master 扩充 | 依赖稳定数据源（付费接口或爬取）|
| 低 | Redis event TTL / maxlen 配置化 | 当前 env 已支持，文档补充即可 |
| 极低 | 实时 WebSocket 行情 | SSE 当前已满足 demo 需求 |
| 极低 | 移动端原生 App | PWA 已覆盖 |
| 极低 | 报告版本对比 | 无具体需求 |
| 极低 | 美股支持 | 需要新数据源 + market 扩展 |

---

## 10. 免责声明

本项目所有报告内容仅供研究参考，不构成任何投资建议。使用者应自行判断投资风险，项目作者不承担因使用本系统而产生的任何投资损失。
