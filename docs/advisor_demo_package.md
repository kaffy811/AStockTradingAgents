# TradingAgents 导师演示与技术交付包

**版本：** Phase C11 完成  
**日期：** 2026-06-20  
**面向读者：** 导师 / 技术评审 / 面试官  
**阅读时间：** 约 10 分钟

---

## 1. 项目一句话定位

**TradingAgents 是一个面向 A 股 / 港股研究场景的 OpenClaw-inspired 金融智能 Agents 系统。**

它不是一个聊天框叠加的股票 dashboard，而是一个具备工具注册表、技能注册表、受控规划器、动作确认机制、结构化会话记忆、审计追踪、安全护栏和能力评估体系的完整 Agentic AI 工程实践。

> 系统所有功能仅供研究辅助，不构成投资建议，不接入任何交易系统。

---

## 2. 为什么不是普通股票分析网站

### 传统股票 Dashboard（页面驱动）

```
用户 → 点击菜单 → 跳转页面 → 看数据
```

用户必须知道去哪里找信息，系统只展示数据。

### TradingAgents Chat Copilot（Agent 驱动）

```
用户 → 自然语言研究目标
    → Agent 自动选择工具 / 技能 / 规划步骤
    → 工具调用链可见（Tool Trace）
    → 写操作需要用户确认（Confirmation Card）
    → 结果落地到报告 / 自选股 / 对比页 / 行业页
    → 全过程可审计（metadata / audit trail）
    → 安全护栏拦截交易指令
```

**关键差异：**

| 维度 | 传统 Dashboard | TradingAgents Agent |
|------|---------------|---------------------|
| 交互方式 | 页面导航 | 自然语言意图 |
| 工具选择 | 用户手动 | Agent 自动路由 |
| 复合任务 | 多页操作 | Planner 自动拆步 |
| 写操作 | 按钮直接执行 | 确认卡 → 执行 |
| 过程可见性 | 无 | Tool Trace 全链路 |
| 安全边界 | 无 | 交易指令拦截 + Prompt Injection 防护 |
| 能力证明 | 无 | 30 golden tasks + capability manifest |

---

## 3. OpenClaw-inspired 架构映射

[OpenClaw](https://github.com/openclawai/openclaw) 是一个开源的 Agentic AI 框架，定义了 Channel / Tools / Skills / Memory / Actions / Audit / Safety 七层架构。

TradingAgents Chat Copilot 参考该架构，针对金融研究场景做了完整实现：

```
OpenClaw 概念          TradingAgents 实现
─────────────────────────────────────────────────────
Chat Channel      →   /chat 路由 + ChatCopilotView.vue
Tool Registry     →   ToolRegistry（9 只只读金融工具）
Skill Registry    →   SkillRegistry（6 只 SkillSpec JSON 技能）
Controlled Planner→   RuleBasedPlanner + PlannerExecutor（6 种复合意图）
Memory            →   chat_memory.py（session_metadata JSONB，fire-and-forget）
Action Execution  →   ActionTools + ConfirmationManager（3 类真实写操作）
Audit Trail       →   ToolResult.duration_ms/started_at + OrchestratorResult.metadata
Safety Guardrails →   _TRADING_PATTERN + injection guard + chat_safety.py
Skill Discovery   →   SkillSpec JSON + GET /chat/skills API（c9_v1）
Evaluation        →   30 golden tasks + capability_manifest.json + evaluate_chat_agent.py
```

---

## 4. 当前核心能力

### 4.1 研究技能（Financial Skills）

| 技能 | 触发词示例 | 底层工具 |
|------|-----------|---------|
| 股票异动分析 | "为什么688146涨那么多" | resolve + quote + kline + news |
| 风险优先研究 | "688146的风险有哪些" | resolve + kline + news + reports |
| 新闻催化拆解 | "688146最近有什么重大新闻" | resolve + news + quote |
| 自选股巡检 | "帮我看看自选股" | watchlist + quote |
| 行业热点研究 | "哪些行业最热" | industry_hot + industry_stocks |
| 报告解释 | "帮我解释我的历史报告" | recent_reports + report_detail |

### 4.2 复合规划（Controlled Planner）

| 场景 | 输入示例 | 规划步骤 |
|------|---------|---------|
| 异动 + 风险 | "为什么688146涨，然后重点看风险" | anomaly_skill → risk_skill |
| 报告 + 风险 | "解释报告，并告诉我最大风险" | report_skill → risk_skill |
| 自选股巡检 | "自选股里有没有波动大的" | watchlist → kline_summary |
| 行业 + 股票 | "哪些行业热，每个挑几个股票" | industry_hot → stock_lookup |
| 研究 + 行动 | "分析688146，如果可以加入自选" | anomaly_skill → add_watchlist |
| 对比 + 报告 | "比较宁德时代和紫金矿业，然后生成报告" | compare → report_gen |

### 4.3 动作确认（Action Tools）

| 动作 | 触发词 | 确认方式 |
|------|--------|---------|
| 加入自选 | "把688146加入自选" | 确认卡 → POST /confirm |
| 生成研究报告 | "帮我生成688146的综合报告" | 确认卡 → POST /confirm |
| 创建对比 | "对比688146和600519" | 确认卡 → POST /confirm |

### 4.4 工具层（9 只只读工具）

`resolve_stock` / `get_quote` / `get_kline_summary` / `get_latest_news` / `get_recent_reports` / `get_report_detail` / `get_watchlist` / `get_industry_hot` / `get_industry_stocks`

### 4.5 系统能力

- **SkillSpec 技能发现：** GET /chat/skills 返回 JSON spec 元数据（enabled/available/required_tools/safety_rules）
- **结构化记忆：** GET /chat/{session}/memory — recent_symbols / recent_queries / flagged_topics
- **审计追踪：** 每次工具调用记录 duration_ms / started_at / permission_level
- **安全护栏：** 买入/卖出/持有/目标价/价格预测拦截；Prompt Injection 检测；外部内容标记
- **Agent Evaluation：** 30 golden tasks (A:Tools B:Skills C:Planner D:Actions E:Memory F:Safety)

---

## 5. 推荐 5 分钟演示路径

**准备：** 登录系统，打开 /chat，ChatContextPanel 中确认 Agent 技能列表可见。

### Step 1：股票异动分析（约 1.5 分钟）

**操作：** 输入
```
中船特气最近为什么涨这么多？
```

**讲解重点：**
- Tool Trace 展开：Agent 自动调用 resolve_stock → get_quote → get_kline_summary → get_latest_news
- 无需用户指定工具，意图路由自动匹配 `StockAnomalySkill`
- 结果包含技术面摘要 + 新闻催化 + 风险提示
- 底部有免责声明：_仅供研究参考，不构成投资建议_

### Step 2：多步骤 Planner（约 1.5 分钟）

**操作：** 输入
```
帮我分析中船特气为什么涨，然后重点看风险
```

**讲解重点：**
- `然后` 触发 RuleBasedPlanner：检测到 anomaly + risk 复合意图
- Planner 输出 2-step 计划：StockAnomalySkill → RiskFirstSkill
- PlannerExecutor 顺序执行，聚合结果
- 最终答案包含两层研究：异动归因 + 风险梳理

### Step 3：动作确认（约 1 分钟）

**操作：** 输入
```
把中船特气加入自选
```

**讲解重点：**
- 确认卡出现：显示股票信息 + "是否确认加入自选股？"
- **不立即执行**，需要用户明确点击确认
- 点击确认后执行 POST /watchlist，返回 watchlist_action card
- 说明：写操作永远需要确认，这是安全边界

### Step 4：技能发现（约 1 分钟）

**操作：** 展开 ChatContextPanel → 查看 Agent 技能区域

**讲解重点：**
- 技能列表来自 GET /chat/skills，每个技能有 spec 元数据
- 技能不是前端硬编码的按钮，而是后端可注册、可禁用、可审计的能力
- 每个 SkillSpec JSON 声明：name / enabled / required_tools / permission_level / safety_rules / version

---

## 6. 推荐 10 分钟技术讲解路径

### Layer 1：Safety Guard（0:00 - 1:00）

> "系统的第一层是安全护栏，在任何工具调用之前执行。"

- 演示：输入 `帮我买入688146`
- 结果：安全拒绝，不调用任何工具
- 代码指向：`chat_orchestrator.py` → `_TRADING_PATTERN` → `_handle_trading_request()`

### Layer 2：Controlled Planner（1:00 - 3:00）

> "复合任务由纯规则 Planner 分解，不依赖 LLM，零延迟零成本。"

- 演示：输入 `帮我分析中船特气，然后重点看风险`
- 展示 Planner steps（PlannerResult.steps）
- 代码指向：`rule_based_planner.py` → `_COMPOUND_RE` + `_ANOMALY_SIG + _RISK_SIG`

### Layer 3：Skill Registry（3:00 - 5:00）

> "意图匹配后路由到对应 Skill，每个 Skill 有声明式 SkillSpec 元数据。"

- 展示 `specs/stock_anomaly.json`：enabled / required_tools / safety_rules / version=c9_v1
- 调用链：`SkillRegistry.run()` → `select_skill()` → `skill.run(context)` → 注入 metadata
- 代码指向：`registry.py` → `spec_loader.py`

### Layer 4：Tool Registry（5:00 - 7:00）

> "Skill 内部通过 ToolRegistry 调用原子工具，每次调用记录 duration_ms 和 started_at。"

- 展示 Tool Trace：5 次工具调用，各含延迟和状态
- 代码指向：`chat_tools/registry.py` → `call()` → 注入 audit 字段

### Layer 5：Memory + Action（7:00 - 9:00）

> "系统有结构化会话记忆，写操作永远需要用户确认。"

- 展示 GET /chat/{session}/memory 返回 recent_symbols / recent_queries
- 演示加入自选确认卡
- 代码指向：`chat_memory.py` + `action_tools.py` + `ConfirmationManager`

### Layer 6：Evaluation（9:00 - 10:00）

> "系统能力有 30 golden tasks 验收，能力白皮书机器可读。"

- 展示 `docs/chat_agent_capability_manifest.json`
- 展示 `docs/chat_agent_evaluation_report.md`
- 运行：`python scripts/evaluate_chat_agent.py --suite all`

---

## 7. 测试与稳定性证明

| 指标 | 数值 |
|------|------|
| 总测试数 | **389** |
| 通过率 | **100%（389/389）** |
| Golden Tasks | **30/30 PASS** |
| 覆盖层 | C4 Tools + C5 Actions + C6 Skills + C7 Planner + C8 Memory + C9 SkillSpec + C10 Evaluation |
| Migration | 1（d7e3a9b5c2f8，C3 chat tables） |
| 新依赖 | 0（C6-C10 全部使用 stdlib） |

**运行 Golden Task 评测：**
```bash
cd backend
python scripts/evaluate_chat_agent.py --suite all
```

**运行全量测试：**
```bash
cd backend
pytest tests/ -q
```

---

## 8. 安全与合规边界

**系统永久边界（硬编码，不可配置）：**

1. **不提供投资建议** — 所有答案结尾附 `_仅供研究参考，不构成投资建议。_`
2. **不接交易系统** — ActionTools 只写入 app 内部数据库，无任何券商 API 调用
3. **写操作必须确认** — ConfirmationManager 强制 pending → confirmed 二阶段，10分钟超时
4. **交易指令拦截** — `_TRADING_PATTERN` 拦截：买入/卖出/清仓/建仓/目标价/价格预测
5. **Prompt Injection 防护** — `chat_safety.py` 检测注入模式，外部数据标记 `[EXTERNAL DATA]`
6. **跨用户隔离** — 所有数据操作按 user_id 过滤，session memory 按 session_id 隔离
7. **权限分级** — SkillSpec permission_level：`read_only` / `research_action`，拒绝 `sensitive/admin`

---

## 9. 后续扩展方向

| 方向 | 说明 | 优先级 |
|------|------|--------|
| LLM-assisted Planner | 将 RuleBasedPlanner 升级为 LLM 意图理解，保留 PlannerExecutor 执行层 | 高 |
| 更多 SkillSpec | 新增港股技能、ETF 技能、宏观经济技能 | 高 |
| 跨 session 向量记忆 | 用 Redis/pgvector 实现长期用户研究偏好 | 中 |
| 港股数据增强 | HK 市场 quote/kline/news 覆盖扩展 | 中 |
| 研究任务自动巡检 | Cron 触发自选股异动分析，推送到 Chat | 中 |
| Skill 热加载 | SkillSpec JSON 支持运行时新增 Skill 无需重启 | 低 |
| Multi-agent 协作 | 多 Agent 分工并行研究，结果汇总 | 低 |

---

## 附录：关键代码路径

| 功能 | 文件 |
|------|------|
| 主 Orchestrator | `backend/app/agents/chat_orchestrator.py` |
| 工具注册表 | `backend/app/agents/chat_tools/registry.py` |
| 技能注册表 | `backend/app/agents/chat_skills/registry.py` |
| SkillSpec 加载 | `backend/app/agents/chat_skills/spec_loader.py` |
| SkillSpec JSON | `backend/app/agents/chat_skills/specs/*.json` |
| 规划器 | `backend/app/agents/chat_planner/rule_based_planner.py` |
| 执行器 | `backend/app/agents/chat_planner/executor.py` |
| 动作工具 | `backend/app/agents/chat_tools/action_tools.py` |
| 会话记忆 | `backend/app/agents/chat_memory.py` |
| 安全守卫 | `backend/app/agents/chat_safety.py` |
| Chat API 路由 | `backend/app/routers/chat.py` |
| 能力白皮书 | `docs/chat_agent_capability_manifest.json` |
| Golden Tasks | `backend/tests/test_c10_agent_golden_tasks.py` |
| 评测脚本 | `backend/scripts/evaluate_chat_agent.py` |
| 演示路径 | `docs/demo_walkthrough.md` |
