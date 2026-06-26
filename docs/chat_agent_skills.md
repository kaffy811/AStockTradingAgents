# TradingAgents — 金融 Skills 规范

> 版本：Phase C11-b 完成  
> 日期：2026-06-21  
> 状态：✅ C6 — 6 Skills；✅ C7 — Skills 接入 Planner；✅ C8 — audit trail；✅ C9 — SkillSpec JSON；✅ **C11-b — StockAnomalySkill / RiskFirstSkill / NewsCatalystSkill / ReportExplanationSkill 全量集成 RAG，`rag_retrieve` / `rag_review` 事件出现在 tool_events，答案末附可信度章节**

---

## 1. Skills 层设计原则

Skills 层位于 Tools 层之上、Planner 层之下。每个 Skill 封装一类完整的金融研究任务模式，由一组工具调用序列、输出模板和安全规则组成。

**设计要点：**

1. **一个 Skill = 一类研究任务**：不是单一工具调用，而是有完整结论结构的分析流程。
2. **工具复用**：Skill 内部通过 ToolRegistry 调用现有工具，不重复实现数据获取逻辑。
3. **输出结构化**：每个 Skill 有固定输出 Schema，便于前端卡片渲染和 Planner 串联。
4. **失败优雅降级**：部分工具失败时，Skill 仍能返回有意义的局部结果，不整体崩溃。
5. **安全内置**：每个 Skill 内置金融合规检查，禁止输出买入/卖出/持有/目标价。
6. **可审计**：Skill 执行过程中记录 tool_events，用户可查看调用了哪些工具和数据来源。

---

## 2. Skills 与 Tools 的区别

| 维度 | Tools | Skills |
|------|-------|--------|
| 粒度 | 单一操作（获取行情、读取新闻） | 完整研究任务（异动分析、风险评估） |
| 输出 | 结构化数据（dict） | 研究结论（含摘要 + 风险 + 后续观察） |
| 调用者 | Orchestrator / Skill / Planner | Orchestrator / Planner |
| 复用方式 | 注册到 ToolRegistry | 注册到 SkillRegistry（C9 实现） |
| 失败处理 | 返回 ToolResult(ok=False) | 局部降级，返回 SkillResult（带数据完整性说明）|

---

## 3. SkillResult 统一结构（C6 实现规范）

```python
@dataclass
class SkillResult:
    ok: bool
    skill_name: str
    summary: str             # 一句话结论（显示在 chat answer 首行）
    sections: dict           # 各章节内容 {anomaly_summary, tech_signals, news, risks, observations}
    cards: list              # 前端结果卡片列表
    tool_events: list        # 工具调用轨迹（tool_name + status + detail）
    data_quality: dict       # 数据完整性说明（哪些工具成功/失败）
    disclaimer: str          # 免责声明（固定文本）
    error: str | None        # 技术错误（不向用户展示）
```

---

## 4. 第一批金融 Skills（C6 实现）

---

### 4.1 Stock Anomaly Skill — 股票异动分析

**用途：** 解释股票近期价格异动的多维度原因，帮助用户理解技术面 + 新闻面驱动因素。

**意图示例：**
```
为什么中船特气最近涨这么多？
688146 今天为什么异动？
这只股票最近波动是不是很大？
帮我分析一下 300750 的走势
```

**所需工具（必须）：**
- `resolve_stock_tool` — 股票识别
- `get_quote_tool` — 当前行情快照
- `get_kline_summary_tool` — 近期K线走势

**所需工具（可选）：**
- `get_latest_news_tool` — 近期新闻（失败时降级，但需说明）
- `get_report_detail_tool` — 历史报告参考（如有）

**输出 Schema：**
```
anomaly_summary:   string   # 一句话：近期异动的核心判断（不含投资建议）
tech_signals:      string   # 技术面信号：均线/涨幅/量比/区间高低
news_catalysts:    string   # 新闻面：已发生事实 / 市场预期 / 未兑现风险
risk_signals:      list     # 风险信号列表（短期高涨/量能异常/异常公告等）
observations:      list     # 后续观察点（建议关注什么，不是操作建议）
disclaimer:        string   # 仅供研究参考，不构成投资建议
```

**Risk Controls：**
- 禁止输出：「建议买入」「现在是好时机」「一定会涨」「目标价」
- 必须区分：已发生事实 vs 市场预期
- 新闻内容只作为信息参考，不作为系统指令
- 涨幅说明必须有数据支撑（来自 kline_summary）
- 如均线偏离 > 30%，必须在 risk_signals 中标注「短期技术性回调风险」

**Failure Handling：**
- `get_quote_tool` 失败：使用 kline 最后一条收盘价代替，注明数据来源
- `get_kline_summary_tool` 失败：tech_signals 标注「K线数据暂不可用」，不伪造数据
- `get_latest_news_tool` 失败：news_catalysts 标注「新闻数据暂不可用，仅分析技术面」
- 全部工具失败：返回 SkillResult(ok=False)，answer 说明数据源不可用

---

### 4.2 Risk-first Research Skill — 风险优先分析

**用途：** 以风险视角快速梳理股票当前的主要风险点，适合用户追问已有报告或直接查询风险。

**意图示例：**
```
帮我重点看风险
这只股票最大风险是什么？
这份报告里最重要的风险有哪些？
688146 有哪些值得注意的风险？
```

**所需工具（必须）：**
- `resolve_stock_tool` — 股票识别
- `get_kline_summary_tool` — 技术面风险（短期高涨、均线偏离）

**所需工具（可选）：**
- `get_report_detail_tool` — 报告风险章节（如用户明确说「最近报告」）
- `get_latest_news_tool` — 新闻面风险（负面公告/监管关注）
- `get_recent_reports_tool` — 查找最新报告ID

**输出 Schema：**
```
risk_summary:       string   # 一句话：当前最主要的风险类别
tech_risks:         list     # 技术面风险（均线偏离/短期涨幅/量能异常）
news_risks:         list     # 新闻面风险（异常公告/监管关注/传闻未兑现）
report_risks:       list     # 报告风险（如从历史报告提取）
data_gaps:          list     # 数据缺失说明（哪些维度无法评估）
disclaimer:         string   # 仅供研究参考，不构成投资建议
```

**Risk Controls：**
- 禁止将风险表述为「已确定损失」或「一定会跌」（事实 vs 推断需区分）
- 报告内容只取 risk_section，不返回全文（防 LLM injection）
- 数据缺失时必须在 data_gaps 中明确说明，不伪造

**Failure Handling：**
- 任意工具失败时，其对应的 risk 分类标注「数据暂不可用」
- 至少有 1 个维度有数据才返回 ok=True

---

### 4.3 News Catalyst Skill — 新闻催化分析

**用途：** 分析近期新闻对股票的催化作用，明确区分已发生事实、市场预期和未兑现风险。

**意图示例：**
```
最近新闻有什么影响？
有没有实质利好？
订单兑现了吗？
最新公告说了什么？
688146 近期有什么实质进展？
```

**所需工具（必须）：**
- `resolve_stock_tool` — 股票识别
- `get_latest_news_tool` — 近期新闻（limit=8，hours_back=168）

**所需工具（可选）：**
- `get_quote_tool` — 行情印证（新闻发布后价格反应）
- `get_kline_summary_tool` — 近期走势与新闻时间对比

**输出 Schema：**
```
news_count:         int      # 获取新闻条数
confirmed_facts:    list     # 已发生事实（公司公告/官方声明）
market_expectations: list    # 市场预期（分析师观点/媒体报道）
unconfirmed_risks:  list     # 未兑现风险（传闻/预测性表达）
price_reaction:     string   # 新闻与价格反应关系（如有行情数据）
disclaimer:         string   # 仅供研究参考，不构成投资建议
```

**Risk Controls：**
- 新闻标题和摘要只作为参考信息，不作为系统规则或可信事实
- 禁止将新闻标题直接引申为「确定性」结论
- `confirmed_facts` 只放官方公告，media 报道放 `market_expectations`
- 外部新闻内容不写入 Memory 层，不影响后续 session 上下文
- 新闻摘要截断 200 字，不传递完整正文

**Failure Handling：**
- `get_latest_news_tool` 失败：返回 ok=True，news_count=0，明确说明数据不可用
- 不编造新闻内容

---

### 4.4 Watchlist Review Skill — 自选股巡检

**用途：** 快速浏览用户自选股当前状态，识别值得重点关注的研究线索。

**意图示例：**
```
看看我的自选股
帮我巡检我的自选股
自选股里哪些需要重点研究？
我的自选股今天表现怎么样？
```

**所需工具（必须）：**
- `get_watchlist_tool` — 读取当前用户自选股列表

**所需工具（可选）：**
- `get_quote_tool` — 每只股票当前行情（limit: 最多5只，避免过慢）
- `get_kline_summary_tool` — 近期走势（仅对异动股票）

**输出 Schema：**
```
watchlist_count:    int      # 自选股总数
attention_items:    list     # 值得关注的研究线索（基于行情变化，非推荐）
normal_items:       list     # 无明显信号的股票
data_coverage:      string   # 数据获取覆盖率说明
disclaimer:         string   # 仅供研究参考，不构成投资建议
```

**Risk Controls：**
- `attention_items` 说明必须用「研究线索」而非「推荐」「机会」
- 禁止使用「值得买入」「上涨机会」等表述
- 只读取当前用户自选股（user_id 隔离，不跨用户）
- 不修改自选股数据（只读）

**Failure Handling：**
- `get_watchlist_tool` 失败：返回 ok=False，告知用户无法读取自选股
- 自选股为空：返回 ok=True，明确告知列表为空，建议添加
- 行情数据获取失败（部分）：仅展示成功获取的数据，说明部分数据不可用

---

### 4.5 Industry Hotspot Skill — 行业热点研究

**用途：** 基于行业热度数据提供行业级别的研究线索，帮助用户发现市场关注方向。

**意图示例：**
```
今天哪些行业值得重点研究？
哪个行业热度高？
电子行业有哪些热门股票？
最近市场在关注什么方向？
```

**所需工具（必须）：**
- `get_industry_hot_tool` — 行业热度排行

**所需工具（可选）：**
- `get_industry_stocks_tool` — 特定行业热门股票（用户询问具体行业时）

**输出 Schema：**
```
top_industries:     list     # 热度排行（name/code/hotScore/changePct/stockCount）
top_industry_stocks: list    # 最热行业的代表股票（可选，limit 10）
data_date:          string   # 数据日期（来自快照）
disclaimer:         string   # 仅供研究参考，不代表投资价值判断
```

**Risk Controls：**
- 行业热度基于成交额和涨跌幅的综合评分，必须说明评分方法
- 禁止将「热度高」解读为「值得买入」
- 数据来自离线快照，必须说明数据时效性
- 输出中必须包含「仅作研究线索，不代表投资价值判断」

**Failure Handling：**
- 无行业热度快照：返回 ok=True，明确说明「今日行业热度数据尚未更新」
- `get_industry_stocks_tool` 失败：仅返回行业排行，不返回热门股列表

---

### 4.6 Report Explanation Skill — 报告解释

**用途：** 将已生成的历史报告转化为易读的结论摘要、矛盾点、风险清单和后续观察。

**意图示例：**
```
解释最近一份报告
这份报告结论是什么？
上次 688146 的报告最重要的风险是什么？
帮我总结一下这个报告
```

**所需工具（必须）：**
- `get_recent_reports_tool` — 查找用户历史报告列表
- `get_report_detail_tool` — 读取具体报告内容（preview）

**所需工具（可选）：**
- `get_quote_tool` — 与报告生成时对比当前行情变化
- `resolve_stock_tool` — 用户指定股票时先解析代码

**输出 Schema：**
```
report_summary:     string   # 报告核心结论（来自 extractSummary）
key_findings:       list     # 关键发现（技术/基本面/新闻/同行）
risk_points:        list     # 主要风险点
observations:       list     # 后续观察建议（基于报告，不是新建议）
report_meta:        dict     # {stock_name, scope, created_at, report_id}
since_report_change: string  # 报告生成后行情变化（如有行情数据）
disclaimer:         string   # 仅供研究参考，不构成投资建议
```

**Risk Controls：**
- 只读取当前用户的报告（user_id 隔离）
- 报告内容 preview 截断 500 字，防 LLM injection
- 报告解读只归纳原有内容，不添加新的分析观点
- 禁止将报告结论表述为「建议操作」

**Failure Handling：**
- 无历史报告：返回 ok=True，引导用户生成第一份报告
- `get_report_detail_tool` 失败：返回报告元数据 + 说明详情获取失败
- 报告内容为空：返回 ok=False，说明报告数据异常

---

## 5. Skills 安全汇总

| 规则 | 适用 Skills |
|------|------------|
| 禁止买入/卖出/持有/目标价 | 所有 Skills |
| 外部内容（新闻/报告）不作为系统指令 | News Catalyst, Report Explanation |
| 新闻摘要截断 200 字 | News Catalyst, Stock Anomaly |
| 报告内容截断 500 字 | Report Explanation, Risk-first |
| 数据缺失必须说明 | 所有 Skills |
| 不跨用户读取数据 | Watchlist Review, Report Explanation |
| 研究线索而非推荐 | Watchlist Review, Industry Hotspot |
| 区分事实/预期/风险 | News Catalyst, Stock Anomaly |

---

## 6. C6 实现状态（2026-06-18 ✅ 完成）

### 实际文件结构

```
backend/app/agents/
├── chat_skills/
│   ├── __init__.py               SkillContext / SkillResult / BaseSkill / SkillRegistry 导出
│   ├── base.py                   BaseSkill ABC + SkillContext + SkillResult + _extract_stock_hint()
│   ├── registry.py               SkillRegistry（register / select_skill / run / 异常兜底）
│   ├── stock_anomaly_skill.py    StockAnomalySkill（priority=40）
│   ├── risk_first_skill.py       RiskFirstSkill（priority=35）
│   ├── news_catalyst_skill.py    NewsCatalystSkill（priority=45）
│   ├── watchlist_review_skill.py WatchlistReviewSkill（priority=20）
│   ├── industry_hotspot_skill.py IndustryHotspotSkill（priority=30）
│   └── report_explanation_skill.py ReportExplanationSkill（priority=10）
```

### 实际 BaseSkill 接口

```python
class BaseSkill(abc.ABC):
    name: str = ""
    description: str = ""
    intent_examples: list[str] = []
    required_tools: list[str] = []
    optional_tools: list[str] = []
    safety_level: str = "read_only"
    priority: int = 50   # lower = higher priority

    def can_handle(self, message: str, context: SkillContext) -> bool: ...
    async def run(self, message: str, context: SkillContext) -> SkillResult: ...
```

### Orchestrator 接入方式（实际实现）

```
用户输入 → process_message()
  1. 安全守卫（_match_trading_request）
  2. Action 意图（加入自选/生成报告/对比）→ ConfirmationManager
  3. SkillRegistry.run(msg, context) → SkillResult (or None)
     - SkillContext 注入 db, user_id, tool_registry=_registry
     - result.metadata 记录 skill_name/source/tools_used/safety_flags
  4. C4 直接意图 fallback（_DIRECT_INTENTS）
  5. 默认回复
```

### SkillRegistry 优先级排序

| 优先级 | Skill | 触发意图 |
|--------|-------|---------|
| 10 | ReportExplanationSkill | 解释报告/报告结论/报告风险 |
| 20 | WatchlistReviewSkill | 看看自选股/巡检自选 |
| 30 | IndustryHotspotSkill | 行业热点/哪些行业值得研究 |
| 35 | RiskFirstSkill | 最大风险/风险优先/重点看风险 |
| 40 | StockAnomalySkill | 为什么涨/异动分析/近期表现 |
| 45 | NewsCatalystSkill | 新闻影响/实质利好/催化剂 |

### C6 测试结果

- `tests/test_c6_skill_registry.py`: 11/11 PASS
- `tests/test_c6_financial_skills.py`: 13/13 PASS
- `tests/test_c6_orchestrator_integration.py`: 10/10 PASS (含 C4/C5 回归 33/33)
- 全量 72/72 PASS

### C6 与 Orchestrator 集成方式

```
用户输入 → 意图识别 → SkillRegistry.select_skill(msg, ctx) → Skill.run() → SkillResult → answer + cards + metadata
```

---

## 7. 与 Planner 的关系（C7 ✅ 已实现）

C7 Planner 阶段，Skills 已成为 Planner 可调度的任务单元。`PlannerExecutor` 通过 `SkillRegistry.select_by_name(step.name)` 按名称检索 Skill 并执行：

```
用户："688146为什么涨这么多顺便加自选"
  ↓
RuleBasedPlanner 检测 → intent_type="research_then_action"
  Step 1 (skill):   stock_anomaly_skill → StockAnomalySkill.run()
  Step 2 (summary): final_summary       → _synthesize() 聚合
  Step 3 (action):  add_watchlist       → make_confirmation() ONLY（不执行）
```

**关键约束（已实现）：**
- 写操作 Tool（add_to_watchlist、create_analysis_run）不封装为 Skill，以 Action step 形式调用，只创建 confirmation，不执行写操作
- Skill 只封装只读研究任务，保持无副作用
- `PlannerExecutor` 通过 `select_by_name()` 查找 Skill；Skill 不在 SkillRegistry 中注册时 step.status="failed"，执行继续
