# AI Agent 设计文档（Phase 3 / Phase 3B）

## 1. 架构概述

财报 AI 分析采用三层 Agent 架构：

```
FundamentalAIOrchestrator
        │
        ├── [1] FundamentalDataAgent      — 确定性数据收集（无 LLM）
        │         ↓
        │     data_pack（compressed_facts / module_summaries / data_quality）
        │
        ├── [2] FundamentalAnalysisAgent  — LLM 结构化分析（DeepSeek / OpenAI）
        │         ↓
        │     raw_analysis（JSON：summary / dimensions / highlights / risks / …）
        │
        └── [3] FundamentalReviewAgent    — 规则审核层（不依赖 LLM）
                  ↓
              final_analysis（已审核 JSON + review_status + review_notes）
```

关键原则：
- **Data Agent** 仅使用确定性 API（Tushare / AkShare）；不调用任何 LLM。
- **Analysis Agent** 调用 LLM，输出严格受 Schema 约束的结构化 JSON。
- **Review Agent** 是最后防线；永不调用 LLM；只做规则检查和文本替换。
- **Orchestrator** 负责 Redis 缓存、降级与错误隔离；**永不抛出异常**。

---

## 2. AI Provider 配置

### 环境变量

| 变量名              | 默认值         | 说明                                     |
|---------------------|----------------|------------------------------------------|
| `AI_PROVIDER`       | `deepseek`     | 使用的 AI 提供商（deepseek / openai）    |
| `AI_ENABLED`        | `true`         | 主开关；false 时 ai_analysis 返回 partial |
| `DEEPSEEK_API_KEY`  | —              | DeepSeek API 密钥                         |
| `OPENAI_API_KEY`    | —              | OpenAI API 密钥（未来支持）               |

### 代码读取

```python
# app/core/config.py
ai_provider: str = "deepseek"
ai_enabled: bool = True

@property
def ai_api_key(self) -> str | None:
    if self.ai_provider == "deepseek":
        return self.deepseek_api_key
    if self.ai_provider == "openai":
        return self.openai_api_key
    return None
```

Analysis Agent 使用 `settings.ai_api_key`，与具体 provider 解耦。

### 无 Key 时的行为

- `ai_api_key` 为 None → Analysis Agent 抛出 `RuntimeError("AI API Key 未配置，AI 分析暂不可用")`
- Orchestrator 捕获 RuntimeError → 尝试返回 stale 缓存 → 否则返回 `partial=true`
- 前端收到 `partial=true` 时展示占位条，不影响其他确定性模块

---

## 3. summary / full 双模式

| 参数          | summary              | full                 |
|---------------|----------------------|----------------------|
| facts_limit   | 30 条                | 60 条                |
| 用途          | 顶部摘要条           | AI 分析完整页        |
| 缓存 key      | 含 `mode=summary`    | 含 `mode=full`       |
| 缓存 TTL      | 86400s（24h）        | 86400s（24h）        |
| 前端组件      | `AiSummaryStrip`     | `AiAnalysisCard`     |

前端策略：
1. Company Tab 挂载时并行请求 `mode=summary`，结果显示在顶部摘要条。
2. 用户点击"查看完整 AI 分析"时切换到 AI 分析分组，触发 `mode=full` 请求。
3. 若 `summary` 请求失败，摘要条显示占位，其他模块不受影响。

---

## 4. Review Agent 审核规则

### 4.1 严重违规（→ rejected）

输出 `SAFE_PLACEHOLDER`，不缓存。

| 检查类型 | 示例触发词 |
|---|---|
| 投资建议禁词 | 买入、卖出、加仓、减仓、目标价、保证收益、推荐买入 … |
| 机构评级误导 | 机构一致推荐买入、完整机构一致推荐、机构全面推荐 |
| 结构不完整 | 缺少 summary / overall_score / dimensions / … |

### 4.2 轻微违规（→ revised）

保留内容，做文本替换，加入 review_notes。

| 检查类型 | 处理方式 |
|---|---|
| 轻微措辞 | 短期会涨→短期走势不确定；上涨空间→估值弹性 … |
| source_fact_ids 不存在 | 在 data_limitations 中注记 |
| source_modules 缺失 | 在 review_notes 中记录 |
| 数字无法溯源 | 在 review_notes 中加轻量警告 |

### 4.3 Disclaimer 自动补充

无论 approved / revised，`_ensure_disclaimer()` 始终运行：
- 若输出中无 `"不构成投资建议"`，自动添加标准免责声明。

### 4.4 review_notes 字段结构

```json
[
  {
    "type": "mild_phrase_rewritten",
    "message": "已改写措辞：短期会涨"
  },
  {
    "type": "source_modules_missing",
    "message": "部分证据缺少 source_modules：…"
  }
]
```

可能的 type 值：
- `investment_advice_blocked`
- `analyst_ratings_misuse`
- `structure_error`
- `mild_phrase_rewritten`
- `fact_id_warning`
- `source_modules_missing`
- `numeric_unverified`
- `review_error`（审核层自身异常时）

---

## 5. 前端：AiSummaryStrip 与完整 AI 分析页

### AiSummaryStrip

- 位置：Company Tab 内，CompanyOverviewCards 下方，Toolbar 上方
- 始终渲染；AI 不可用时显示轻量占位，不影响其他模块
- 可折叠；展开后显示：
  - 综合评分 badge（绿 ≥80 / 橙 ≥60 / 红 <60）
  - summary 文本
  - top-2 highlights（绿色列表）
  - top-2 risks（红色列表）
  - 审核状态 badge（已审核 / 已修订 / 审核未通过）
  - 免责声明
  - "查看完整 AI 分析 →" 按钮

### AiAnalysisCard（完整页）

- 位置：AI 分析分组（section key = `ai`）
- 展示：完整 5 维雷达图、dimensions 详情、highlights、risks、watch_items、review 折叠面板

### 缓存复用

CompanyFundamentalsPanel 在 `onMounted` 时并行请求 `mode=summary`，结果存入 `aiSummaryEnvelope`。
同时预填充 `moduleData['ai_analysis']`，避免切换到完整页时重复请求（若已有则直接复用）。

---

## 6. DataEnvelope source 字段

```json
{
  "source": {
    "primary": "deepseek",
    "fallback": null,
    "actual": "deepseek"
  }
}
```

- `primary`：来自 `settings.ai_provider`（非硬编码）
- `actual`：正常时与 primary 相同；stale 缓存时为 `"cache"`
- 前端不展示具体模型名

---

## 7. 安全边界

1. AI **不得**输出买入、卖出、目标价、保证上涨等投资建议。
2. AI **必须**在输出中包含"不构成投资建议"免责声明。
3. `review_status=rejected` 的输出**不缓存**，不返回给用户，仅返回 `SAFE_PLACEHOLDER`。
4. Review Agent 不依赖 LLM，不会因 LLM 故障而失效。
5. Orchestrator 捕获所有异常；即使 AI 完全失败，前端 Company Tab 其他模块仍正常工作。
