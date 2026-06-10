# i18n 实现说明

## 一、两套语言设置的边界

TradingAgents 中存在两套独立的语言控制机制：

| 设置 | 存储键 | 作用范围 | 选择入口 |
|------|--------|----------|---------|
| `settings.language` | localStorage `tradingagents:settings:v1` | 界面固定文案（导航栏、按钮、标签、空状态、提示语等） | ProfileSettingsPanel → "界面语言" |
| `settings.report_language` | 同上 | AI 分析报告正文语言（LLM 生成内容） | ProfileSettingsPanel → "报告输出语言" |

两者完全独立，用户可以自由组合（如：中文 UI + 英文报告）。

---

## 二、UI 语言（settings.language）实现

### 技术方案

- 自定义 `src/utils/i18n.js`：单例 `_locale = ref('zh-CN')`
- 6 个 locale 文件：`zh-CN.js` / `en-US.js` / `zh-TW.js` / `ja-JP.js` / `ko-KR.js` / `es-ES.js`
- `useI18n()` 返回 `{ t, locale, LOCALES }`
- `t(key, vars)` 支持插值（`{count}` / `{n}` 等）
- 切换时写入 localStorage，`main.js` 启动时同步读取（防 FOUC）
- fallback：未翻译的键返回 zh-CN 值

### 覆盖范围（M34 + M35）

| 模块 | 覆盖阶段 |
|------|---------|
| AppHeader / BottomTabBar | M34 |
| ComprehensiveAnalysisView（分析页） | M34 |
| ProfileView + ProfileSettingsPanel | M34 |
| HistoryView + ReportListCard / ReportFilterPanel / ReportCenterStats | M35 |
| WatchlistView + WatchlistStockCard / WatchlistToolbar / WatchlistStats | M35 |
| IndustryHotView + 全部 Industry 组件 | M35 |
| StockCompareView + 全部 Compare 组件 | M35 |

### locale 键命名规则

- 导航：`nav_*` / `tab_*`
- 报告页：`rpt_*`
- 自选股：`wl_*`
- 行业：`ind_*`
- 对比：`cmp_*`
- 设置页：`psp_*`
- Badge 短标签：`badge_*`
- 语言标签：`lang_*`

---

## 三、报告输出语言（settings.report_language）实现

### 流程

```
ProfileSettingsPanel 选择 report_language
  → settings.js 存储
  → ComprehensiveAnalysisView 读取 reportLanguage.value
  → createAnalysisRun / runComprehensiveAnalysisV2 request body: { output_language }
  → backend AnalysisRunRequest / ComprehensiveV2Request field_validator 校验
  → create_run(output_language=...) 写入 AnalysisRun dataclass
  → realtime_runner / langgraph_realtime_runner 透传至 synthesis 方法
  → _build_synthesis_prompt() 追加【输出语言】指令
  → LLM 以目标语言生成报告
  → result metadata["output_language"] 写入
  → createReport() 保存至 DB output_language 列
  → ReportListCard / ReportDetailHeader badge 显示
```

### 支持语言

| 代码 | 名称 | 级别 |
|------|------|------|
| zh-CN | 简体中文 | 默认，完全支持 |
| en-US | English (US) | synthesis 报告完整；single-agent wrapper 已翻译 |
| zh-TW | 繁體中文 | synthesis 报告完整；single-agent wrapper 已翻译 |
| ja-JP | 日本語 | synthesis 报告完整；single-agent wrapper 已翻译 |
| ko-KR | 한국어 | synthesis 报告完整；single-agent wrapper 已翻译 |
| es-ES | Español | synthesis 报告完整；single-agent wrapper 已翻译 |

### Single-agent 报告语言完整度（M37 后完整支持）

| 报告类型 | wrapper 标题/摘要/风险提示 | Agent 主体内容（M37 后） |
|----------|--------------------------|------------------------|
| technical_only | ✅ 目标语言（_SINGLE_AGENT_STRINGS） | ✅ LLM 收到语言指令，主体尽量目标语言 |
| fundamental_only | ✅ 目标语言 | ✅ LLM 收到语言指令 |
| peer_only | ✅ 目标语言 | ✅ LLM 收到语言指令 |
| news_only | ✅ 目标语言 | ✅ LLM 收到语言指令（新闻标题/原文保留原文） |

> **M37 实现**：在四个 Agent 的 `analyze()` / `analyze_async()` 中新增 `output_language` 参数，通过 `language_utils.build_output_language_instruction()` 在 user prompt 末尾追加【输出语言要求】块。zh-CN 时空字符串（零 token），非 zh-CN 时注入语言指令。

> **保留原文规则**：股票名称、股票代码、公司专有名词、新闻标题、财务指标缩写（PE、PB、ROE、MACD、RSI、MA5 等）允许保留原文，其余解释、章节标题、摘要、风险提示使用目标语言。

> **向后兼容**：所有旧调用 `analyze(market, symbol)` 不传 output_language 时默认 zh-CN，行为与 M37 前完全一致。

### DB 持久化

- 列：`analysis_reports.output_language VARCHAR(16) NOT NULL DEFAULT 'zh-CN'`
- Migration：c5e9f12a3b87
- 旧报告自动 fallback zh-CN（server_default 保证）
- 不出现 null 值

---

## 四、Backend prompt 注入方式

在 synthesis prompt 的**用户消息末尾**追加语言指令（非 system prompt），减少对现有约束的干扰：

```
【输出语言】
请使用 {language_label} 撰写本次分析报告。
除股票名称、代码、公司专有名词、新闻标题、财务字段名称可保留原文外，
其余解释、章节标题、摘要、风险提示均应使用 {language_label}。
```

- `zh-CN` 时不追加（默认行为，不引入不必要的 token）
- 指令追加到 `_build_synthesis_prompt()` 和 `_synthesize_tech_fundamental()` 返回值末尾

---

## 五、Frontend badge 设计

| 语言 | ReportListCard badge | ReportDetailHeader badge |
|------|---------------------|------------------------|
| zh-CN | 不显示（默认） | 不显示 |
| en-US | `EN` | `EN` |
| zh-TW | `繁中` | `繁中` |
| ja-JP | `JA` | `JA` |
| ko-KR | `KO` | `KO` |
| es-ES | `ES` | `ES` |
| 未知代码 | fallback 显示原 code | 同左 |

Badge 样式：黄色警示色（`--status-warn-*`），区别于 scope badge（蓝色）和 auto_saved tag（灰色）。

---

## 六、Agent-level 语言指令注入（M37）

### language_utils.py

新建 `backend/app/agents/language_utils.py`，提供：

```python
def build_output_language_instruction(output_language: str | None) -> str:
    # zh-CN → ""  （不引入额外 token）
    # 其他 → 【输出语言要求】块
```

注入策略：
- 追加到 user prompt **末尾**（非 system prompt），减少对已有安全约束的干扰
- system prompt 中的禁止词、分析准则、输出格式保持原样
- 语言指令只说"用 X 语言写"，不修改任何约束逻辑

### 四个 Agent 签名变更

| Agent | 旧签名 | 新签名（向后兼容） |
|-------|--------|-----------------|
| TechnicalAnalystAgent | analyze(market, symbol) | analyze(market, symbol, output_language="zh-CN") |
| FundamentalAnalystAgent | analyze(market, symbol) | analyze(market, symbol, output_language="zh-CN") |
| PeerComparisonAnalystAgent | analyze(market, symbol) / analyze_async(db, market, symbol) | 各加 output_language="zh-CN" |
| NewsAnalystAgent | analyze(market, symbol, hours_back, limit) | analyze(market, symbol, hours_back, limit, output_language="zh-CN") |

### 透传链路

```
settings.report_language
  → ComprehensiveAnalysisView (reportLanguage.value)
  → createAnalysisRun / runComprehensiveAnalysisV2 (output_language 字段)
  → AnalysisRun.output_language (registry)
  → RealtimeAnalysisRunner._do_run → _run_named_agent(output_language)
     → TechnicalAnalystAgent.analyze(output_language)
     → FundamentalAnalystAgent.analyze(output_language)
     → PeerComparisonAnalystAgent.analyze_async(output_language)
     → NewsAnalystAgent.analyze(output_language)
  → synthesis (_build_synthesis_prompt / _synthesize_tech_fundamental)
  → metadata["output_language"] + full_result["output_language"]
  → createReport → DB output_language 列
  → ReportListCard / ReportDetailHeader badge
```

LangGraph 路径：`initial_state["output_language"]` → `_technical/fundamental/peer/news_node` → `state.get("output_language")` → Agent

---

## 七、报告 Markdown 格式统一（M38）

### Agent 子章节标准格式

四个 Agent（Technical / Fundamental / Peer / News）的【输出格式】统一为：
- 移除 Agent 自带的顶级 `# ` 或 `## ` 标题行
- 子章节统一使用三级标题 `### `（如 `### 一、行情概览`）

这样在 single-agent wrapper 结构内形成整洁的三级层次：
```
# 报告标题          ← wrapper 提供
## 一、摘要         ← wrapper 二级节
## 三、核心观察     ← wrapper 二级节
### 一、行情概览    ← Agent 子章节（三级）
### 二、均线与趋势  ← Agent 子章节（三级）
## 四、数据边界     ← wrapper 二级节
```

### REPORT_SECTION_LABELS（language_utils.py）

13 个标签键（6 语言）供 exportMarkdown.js / PrintReportView.vue 使用：

| 键 | 用途 |
|---|---|
| `scope_comprehensive` / `scope_technical_only` / ... | Scope 报告标题 |
| `section_technical` / `section_fundamental` / ... | 子报告 section 标题 |
| `agent_status` / `data_quality` / `no_warnings` | 导出/打印 metadata 文字 |

`report_label(output_language, key)` → fallback to zh-CN。

### extractSummary() 多语言匹配（M38）

新增非 zh-CN 报告摘要节匹配（优先级顺序）：
1. `一、摘要` / `一、核心摘要`（zh-CN / zh-TW）
2. `I. Summary` / `I. Core Summary`（en-US）
3. `I. 要約`（ja-JP）
4. `I. 요약` / `I. 핵심 요약`（ko-KR）
5. `I. Resumen`（es-ES）
6. `二、核心结论`（legacy zh-CN pre-M29）

stop-pattern 改为 `\n#{2,3}\s+`，适配任意语言二 / 三级标题。

## 八、构建状态

- `npm run build`: ✓ 195 modules，0 errors
- `python -m compileall app -q`: ✓ 0 errors
- `alembic current`: ✓ c5e9f12a3b87 (head)
