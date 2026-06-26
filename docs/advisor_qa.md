# TradingAgents — 导师技术问答

**版本：** Phase C11  
**日期：** 2026-06-20  
**面向：** 导师 / 技术评审 / 面试官

---

## Q1：为什么说这是 Agent，而不是普通 Chatbot？

**回答要点：**

普通 Chatbot 收到消息后直接生成文本回复。TradingAgents Chat Copilot 具备 Agentic AI 的完整特征：

**1. 工具注册表（Tool Registry）**
系统有 9 只可独立调用的原子工具（`get_quote_tool`、`get_kline_summary_tool`、`get_latest_news_tool` 等）。Agent 根据意图自动选择工具，用户不需要手动指定。

**2. 技能注册表（Skill Registry）**
6 只金融研究技能封装了多工具调用链（如 `StockAnomalySkill` = resolve + quote + kline + news）。每个技能有声明式 SkillSpec JSON（enabled / required_tools / permission_level / safety_rules）。

**3. 受控规划器（Controlled Planner）**
`RuleBasedPlanner` 检测复合意图，输出有序 PlanStep 列表。`PlannerExecutor` 顺序执行，最多 5 步。这是 Agentic AI 的 "plan then execute" 模式。

**4. 动作确认（Action Confirmation）**
写操作（加入自选、生成报告、创建对比）经过 ConfirmationManager 二阶段确认才执行，防止 Agent 自动执行用户不知情的写操作。

**5. 结构化记忆（Structured Memory）**
session memory 记录 recent_symbols / recent_queries / flagged_topics，跨消息保持上下文。

**6. 审计追踪（Audit Trail）**
每次工具调用记录 `duration_ms` / `started_at` / `permission_level`，OrchestratorResult 携带 `tools_used` / `safety_flags` / `skill_spec_version`。

**7. 安全护栏（Safety Guardrails）**
交易指令拦截、Prompt Injection 防护、外部数据隔离 —— 这是 Agentic AI 在高风险场景的必要安全层。

**8. 能力评估（Agent Evaluation）**
30 golden tasks 覆盖全部 6 层能力，能力白皮书机器可读（`capability_manifest.json`），评测脚本可复现。

**总结：** 普通 Chatbot = 输入 → LLM → 输出。TradingAgents = 意图 → 安全检查 → 规划 → 技能选择 → 工具调用 → 确认执行 → 记忆写入 → 审计。这是完整的 Agentic AI 工程实践。

---

## Q2：OpenClaw 的思想体现在哪里？

**回答要点：**

[OpenClaw](https://github.com/openclawai/openclaw) 定义了一套 Agentic AI 框架的七层架构。TradingAgents 对每一层都有对应实现：

| OpenClaw 层 | TradingAgents 实现 |
|-------------|-------------------|
| Chat Channel | `/chat` 路由 + ChatCopilotView.vue + ChatContextPanel |
| Tools | `ToolRegistry`（9 只只读金融工具），每工具独立注册 |
| Skills | `SkillRegistry`（6 只技能），SkillSpec JSON 声明式配置 |
| Memory | `chat_memory.py`，session_metadata JSONB，fire-and-forget 写入 |
| Actions | `ActionTools` + `ConfirmationManager`（3 类写操作，二阶段确认） |
| Safety | `_TRADING_PATTERN` + `chat_safety.py`（injection guard + forbidden phrases） |
| Audit | `ToolResult.duration_ms/started_at` + `OrchestratorResult.metadata` |
| Skill Discovery | `SkillSpec JSON` + `GET /chat/skills`（c9_v1，可发现可校验） |

**重要区别：** 我们没有直接使用 OpenClaw 库，而是参考其架构思想，针对 A 股金融研究场景做了从零设计的实现。这样做的原因是：
1. 金融场景有特殊的安全约束（不能输出投资建议）；
2. 需要与已有的 FastAPI / PostgreSQL / AkShare 技术栈集成；
3. 意图分类使用规则引擎而非 LLM，降低延迟和成本。

---

## Q3：为什么不直接让 LLM 自由调用工具（Tool Use / Function Calling）？

**回答要点：**

LLM 自由 Tool Use（如 OpenAI Function Calling）在通用场景很强大，但在金融研究场景有几个问题：

**1. 金融场景风险高**
LLM 可能生成听起来专业但实际错误的投资建议，或将外部数据中的注入指令当作指令执行。

**2. 受控 Planner 更可预测**
`RuleBasedPlanner` 基于正则规则，行为完全确定。相同输入永远输出相同计划，便于测试（30 golden tasks 可验证）。

**3. 工具白名单**
所有工具在 `ToolRegistry` 显式注册。SkillSpec 声明 `required_tools`，Skill 只能访问白名单内的工具。

**4. 写操作必须确认**
即使 LLM 决策 "加入自选"，也必须经过 ConfirmationManager 二阶段。用户永远有机会取消。

**5. 禁止交易建议**
`_TRADING_PATTERN` 在 Orchestrator 入口拦截，任何 LLM 生成的 "买入建议" 都不会到达用户。

**未来扩展：** C11 后的路线图包含 "LLM-assisted Planner"，用 LLM 理解复杂意图，但执行层（ToolRegistry + SkillRegistry + ConfirmationManager）保持规则控制。

---

## Q4：如何防止 Agent 乱操作？

**回答要点：**

系统有五层防护：

**Layer 1：Safety Guard（入口拦截）**
```python
# chat_orchestrator.py
if _match_trading_request(msg):
    return _handle_trading_request(...)  # 拒绝，不调用任何工具
```
拦截买入/卖出/持有/目标价/价格预测等请求。

**Layer 2：Permission Level（权限分级）**
- SkillSpec 声明 `permission_level`：`read_only` / `research_action`
- 只读工具永远不写数据库
- 写操作工具只在 Action 流程中被调用，不在 Skill 内部调用

**Layer 3：ConfirmationManager（二阶段确认）**
```
用户请求写操作
  → Orchestrator 返回 confirmation card（answer=""）
  → 用户点击确认
  → POST /chat/{session}/confirm → 执行
```
用户未确认前，写操作永远不执行。

**Layer 4：Disabled Skill Gate（技能禁用）**
SkillSpec `enabled=false` 或 required_tools 缺失 → `select_skill()` 返回 None → 技能不执行。运行时可调用 `SkillRegistry.set_skill_enabled(name, False)` 动态禁用。

**Layer 5：Audit Metadata**
每次操作记录在 `OrchestratorResult.metadata` 中，包含 `tools_used` / `safety_flags` / `permission_level`。可通过日志回溯任意会话的操作链。

**跨用户隔离：**
- `get_watchlist_tool` 按 `user_id` 过滤
- `get_recent_reports_tool` 按 `user_id` 过滤
- Session memory 按 `session_id` 隔离

---

## Q5：如何证明系统稳定？

**回答要点：**

TradingAgents 有三层稳定性证明：

**Layer 1：单元 + 集成测试（389/389 PASS）**
```bash
cd backend && pytest tests/ -q
# 389 passed, 7 warnings
```
覆盖 C4（工具）→ C5（动作）→ C6（技能）→ C7（规划器）→ C8（记忆审计）→ C9（SkillSpec）→ C10（Golden Tasks）全部阶段。

**Layer 2：Golden Task Evaluation（30/30 PASS）**
```bash
cd backend && python scripts/evaluate_chat_agent.py --suite all
```
30 golden tasks 覆盖 6 个能力类别，全部通过代表每个能力层的核心路径可用。见 `docs/chat_agent_evaluation_report.md`。

**Layer 3：Capability Manifest（机器可读能力白皮书）**
`docs/chat_agent_capability_manifest.json` 声明：
- `tools.count = 9`（可验证 vs `_build_registry()`）
- `skills.count = 6`（可验证 vs `specs/*.json`）
- `planner.compound_intent_count = 6`（可验证 vs `rule_based_planner.py`）
- `test_c10_capability_manifest.py` 自动验证 manifest 与代码库对齐

**额外证明：**
- `compileall app -q` → 0 syntax errors
- `alembic current` → d7e3a9b5c2f8（head，无未应用 migration）
- `npm run build` → 0 errors

---

## Q6：系统当前的限制是什么？

**回答要点（诚实说明，不回避）：**

**架构限制：**
1. **无长期向量记忆** — session memory 仅限当次会话，用户重新登录后 recent_symbols 重置
2. **Planner 是规则引擎** — `RuleBasedPlanner` 基于正则，不理解语义；新型复合意图需手动添加规则
3. **意图路由覆盖有限** — 不匹配规则的查询进入 `_handle_default()` 返回通用回复
4. **MAX_STEPS = 5** — 超过 5 步的复合任务需要用户分次输入

**数据限制：**
1. **中文 / CN 市场为主** — A 股工具（AkShare）成熟，HK/US 工具 fallback 覆盖有限
2. **实时行情延迟** — AkShare 数据有 15-60 分钟延迟，非实时交易级行情
3. **新闻仅中文来源** — `get_latest_news_tool` 暂不覆盖英文财经新闻

**安全边界（不会改变的限制）：**
1. **不接交易系统** — 这是设计决策，不是技术限制
2. **不输出投资建议** — `_TRADING_PATTERN` 拦截，永久边界

**后续优化方向：** 见 `docs/advisor_demo_package.md` 第 9 节。

---

## Q7：这个系统如何体现工程质量？

**回答要点：**

**1. 分层架构** — Safety → Planner → Skill → Tool → Action → Memory → Audit，每层单一职责，层间接口清晰。

**2. 声明式配置** — SkillSpec JSON 外置技能元数据，新增技能不需修改路由代码，只需新增 spec 文件 + 实现类。

**3. 可测试设计** — 所有异步函数可 mock，`_registry` / `_skill_registry` 模块级变量可被 `patch()` 替换，无全局副作用。

**4. 渐进式交付** — C1→C10 每阶段独立交付，不破坏前序 tests。C6 完成时 C4 测试仍全通，C9 完成时 C6 测试仍全通。

**5. 文档驱动** — capability_manifest.md/.json / evaluation_report.md / readiness_checklist.md 构成可交付的能力证明体系。

**6. 零新依赖原则（C6-C10）** — C6-C10 所有实现使用 stdlib（`json`、`re`、`dataclasses`），无新 pip 包依赖。

**7. 前端零侵入** — 后端能力升级（C6→C10）前端无需对应修改，Chat UI 通过 API 消费能力，架构解耦。
