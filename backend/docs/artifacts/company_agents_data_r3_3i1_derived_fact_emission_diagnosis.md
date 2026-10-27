# Phase 6W-R3.3I.1 — Derived Fact Emission Diagnosis

## 1. Workspace audit

- `HEAD`: `b055da8495c54bb37625f0b0e0f94b4d4a627de2`
- `branch`: `release/demo-staging`
- `git status --short`:
  - modified: `backend/Dockerfile`
  - modified: `backend/app/main.py`
  - modified: `backend/app/services/report_embedding_provider.py`
  - modified: `backend/pyproject.toml`
  - modified: `backend/uv.lock`
  - untracked: historical `HKNA/docs/suggestion/*`, `HKNA/update_report/update_96.md`, `HKNA/update_report/update_99.md`, and many prior `backend/docs/artifacts/*`
- `git diff --check`: clean
- `git diff --name-only`:
  - `backend/Dockerfile`
  - `backend/app/main.py`
  - `backend/app/services/report_embedding_provider.py`
  - `backend/pyproject.toml`
  - `backend/uv.lock`

Boundary:

- Historical dirty changes above were not modified.
- This round added only diagnosis artifacts.
- No commit, push, deploy, or traffic change was performed.

## 2. Relevant R3.3I code path

This diagnosis is based on the isolated candidate tree at:

- `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/services/report_derived_fact_service.py`
- `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/agent/report_chat_copilot_agent.py`
- `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/agent/prompts/report_chat_system.md`

Key flow:

1. `report_chat_copilot_agent.py:1539-1547` runs the structured financial extractor.
2. `report_chat_copilot_agent.py:1561-1565` calls `build_report_derived_facts(...)`.
3. `report_derived_fact_service.py:98-155` converts structured fields into candidate operands.
4. `report_derived_fact_service.py:175-220` emits `net_margin` only if both operands exist.
5. `report_chat_copilot_agent.py:1585-1594` serializes structured data into the prompt.
6. `report_chat_copilot_agent.py:1602-1668` sends the prompt to the LLM.
7. `report_chat_copilot_agent.py:1730-1740` resolves citations.
8. `report_chat_copilot_agent.py:1872-1906` builds the numeric validation corpus.
9. `report_chat_copilot_agent.py:1919-1945` writes S7 trace payload.

## 3. Frozen net-margin trace

Frozen request:

- question: `2024年贵州茅台净利率如何？`
- report id: `1`
- report year: `2024`
- selected report: `600519.SH / 2024 annual`

Persisted trace evidence:

- `S1.selected_report_id = 1`
- `S1.selected_report_year = 2024`
- `S1.selected_period = 2024-12-31`
- `S4.evidence_chars = 2546`
- `S5.structured_financial_fields_snapshot.fields = []`
- `S5.derived_facts = []`
- `S6.raw_llm_result.answer` explicitly says the structured fields are empty and no derived facts were available
- `S7.derived_facts = []`
- `S7.token_contexts = []`
- `S7.citation_validation.resolved_derived_fact_ids = []`

The frozen trace is recorded in `/private/tmp/r33i-run-results-v2.json` for request id `a623343f`.

## 4. Per-stage evidence matrix

| 环节 | 是否执行 | 输入是否存在 | 输出 | 文件:行号 | 结论 |
|---|---|---:|---|---|---|
| structured financial extraction | yes | yes | `fields=[]` | `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/agent/report_chat_copilot_agent.py:1539-1547` | 输入证据未形成可用结构化字段 |
| derived fact builder call | yes | yes | `derived_facts=[]` | `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/agent/report_chat_copilot_agent.py:1561-1565` | builder 被调用，但没有可发出的事实 |
| structured operand materialization | yes | no | `{}` | `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/services/report_derived_fact_service.py:98-155` | `_structured_facts()` 没有任何字段可转为 operand |
| net margin guard | yes | no | no record emitted | `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/services/report_derived_fact_service.py:191-198` | `profit` / `revenue` 至少一个为空，guard 失败 |
| prompt assembly | yes | yes | prompt contains structured data, but no derived facts | `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/agent/report_chat_copilot_agent.py:1585-1594` | Prompt 里没有可用派生事实 |
| LLM output | yes | yes | no derived-fact adoption | `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/agent/report_chat_copilot_agent.py:1602-1668` | 模型只能给出“结构化字段为空、派生事实为空”的降级回答 |
| citation resolver | yes | yes | `resolved_derived_fact_ids=[]` | `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/agent/report_chat_copilot_agent.py:1730-1740` | 没有派生事实可解析 |
| numeric validation corpus | yes | yes | base evidence only | `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/agent/report_chat_copilot_agent.py:1872-1906` | 没有派生事实可编译进 corpus |
| S7 persistence | yes | yes | `derived_facts=[]` | `/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/agent/report_chat_copilot_agent.py:1919-1945` | trace 只记录到空派生事实 |

## 5. Frozen-input diagnosis

For the net-margin case, the frozen trace shows:

- `structured_financial_fields_snapshot.fields` is empty.
- Retrieved evidence ids are unrelated to revenue/net profit tables.
- `build_report_derived_facts()` therefore sees no usable `revenue` / `net_profit` operands.

Candidate decision for `net_margin`:

```json
{
  "metric": "net_margin",
  "status": "skipped",
  "reason_code": "NO_STRUCTURED_DATA",
  "operands": ["revenue", "net_profit"],
  "evidence_ids": [],
  "period": "2024",
  "value": null,
  "source_function": "/private/tmp/tradingagents-r33e1.IfXFWV/backend/app/services/report_derived_fact_service.py:build_report_derived_facts"
}
```

The first hard failure is not validator rejection. It is operand unavailability before record emission:

- `_structured_facts()` returns `{}` because `structured_financial_data.get("fields")` is empty.
- `_direct_facts()` does not recover revenue/net-profit operands from the retrieved chunks.
- The `if profit and revenue and profit["unit"] == revenue["unit"]:` guard fails, so nothing is emitted.

## 6. Root-cause classification

Category: `INPUT_UNAVAILABLE`

Why:

- `derived_facts` is empty because the builder had no valid operands to work with.
- The missing inputs are upstream of prompt assembly, LLM use, citation resolution, and numeric validation.
- There is no evidence of a validator boundary mismatch for the net-margin case.

## 7. What this is not

- Not `BUILDER_REJECTED`: the builder was called, but it had no operands to reject on a semantic rule; it simply had no eligible input.
- Not `INTEGRATION_DROPPED`: the trace shows the builder path and S5 payload were reached, but there was nothing to emit.
- Not `MODEL_NOT_USING_DERIVED_FACT`: the prompt contained no derived fact for this case.
- Not `VALIDATOR_BOUNDARY_MISMATCH`: nothing reached the validator as a derived fact.

## 8. Tests and runtime evidence

- Targeted unit tests in the isolated candidate tree passed previously:
  - `64 passed`
- No additional net-margin control request was needed because the frozen trace already identified the first failure.
- The latest isolated runtime still showed:
  - `S5.derived_facts = []`
  - `S7.derived_facts = []`
  - `S7.token_contexts = []`

## 9. Conclusion

`DERIVED_FACT_EMISSION_EXPLAINED`

The net-margin case is explained by `INPUT_UNAVAILABLE`: the structured extractor produced no usable financial fields on the frozen evidence set, and the derived-fact builder therefore had no `revenue` / `net_profit` operands to emit.

Traffic decision remains:

`HOLD_1_PERCENT`
