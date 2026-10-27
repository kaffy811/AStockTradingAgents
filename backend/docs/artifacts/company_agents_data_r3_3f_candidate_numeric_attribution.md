# Phase 6W-R3.3F — Candidate Runtime Numeric Attribution

Date: 2026-08-28 (America/New_York)

Decision: `ROOT_CAUSE_NOT_READY`

Traffic: `HOLD_1_PERCENT`

## Outcome

The clean `79323b7ff7665b556bb7eed038f56f167f5dd788` candidate passed the isolated empty-database runtime gate and completed 15 unique, serial Report Chat requests against a newly ingested official CNINFO 2024 annual report for `600519.SH`. Durable traces contain 15 headers and 128 stage rows. Six unsupported-token occurrences were classified from their stored sentences, first-observed stages, retrieved evidence, raw structured LLM results, and official PDF chunks.

No code, validator, RAG, agent, prompt, cache, timeout, migration, Docker/dependency/warmup file, release branch, deployment, traffic, production database, production Redis, or production container was changed.

## Candidate image and clean source

- Branch/worktree: clean `r33e-pgvector-portability` worktree at full SHA `79323b7ff7665b556bb7eed038f56f167f5dd788`.
- Tag: `tradingagents-backend:rc-79323b7`.
- Image ID and local RepoDigest: `sha256:39b440b6a68c658b9a9ac03dda1afa73913fef35f90b2ca453b247c5be817542`.
- OCI revision: `79323b7ff7665b556bb7eed038f56f167f5dd788`.
- Candidate container: `r33f-backend`, ID `403ab7a2199e7a8e3d6ab9b856d404087d5e7de6b31a2ff4f234bcac198b9806`, restart count 0.
- Source bind mounts: none.
- Health: `GET http://127.0.0.1:18001/health` returned `{"status":"ok"}`.

## Database, Redis, network, and port isolation

| Resource | Identity | Isolation evidence |
|---|---|---|
| Network | `tradingagents-r33f_net`, ID `611593f92b074cff62dd9ea08bd68171d45777d83929a73db716f02470b99a50` | Dedicated bridge containing only the three `r33f-*` containers |
| PostgreSQL | `r33f-postgres`, ID `10e6cb885e0782e7b4346cc35b3ade235cbc138b81b215159d7787502f7613b3` | `pgvector/pgvector:pg16`; anonymous dedicated data volume; no host port |
| Redis | `r33f-redis`, ID `8cac16efed1bd0dbc116f7d1709c102bbc8a5fe783bb2f70820060c9704184f4` | `redis:7-alpine`; anonymous dedicated data volume; no host port; isolated DB size 9 after the run |
| Backend | `r33f-backend` | Only `127.0.0.1:18001 -> 8000`; no user-facing binding and no source mount |

PostgreSQL has extension `vector 0.8.6`. Both `uv run alembic current` and `uv run alembic heads`, plus direct `alembic_version`, returned `q5r6s7t8u9v0`. The backend wrote and read both trace header and stage tables.

## Official CNINFO ingestion

The only report was acquired through the real discovery/download/parse/index HTTP path recorded in backend access logs. No production report copy, manual SQL seed, fake chunk, or synthetic report was used.

| Field | Evidence |
|---|---|
| Stock/report | `600519.SH`, 2024 annual, period end `2024-12-31` |
| Title | 贵州茅台：贵州茅台2024年年度报告 |
| Source | `cninfo` |
| CNINFO announcement | `1222993920` |
| Official PDF | `https://static.cninfo.com.cn/finalpage/2025-04-03/1222993920.PDF` |
| PDF SHA-256 | `5299f4940e2ce4e91084b73dc457d558b9d335fa76fbfee6227e4254eb7f4a30` |
| File size | 3,626,217 bytes |
| Download/parse | `downloaded` / `parsed` |
| Company V2 index | status `indexed`, active index 1, generation 1 |
| Parsed/indexed size | 143 pages, 208 chunks |
| Indexed at | `2026-08-28 00:41:04.053052` UTC |

The legacy `report_documents.rag_status` remains `pending`, but the runtime path uses `company_v2_report_rag_documents`, whose authoritative record is `indexed`; all 15 S2 rows identify provider `company_v2_report_rag` and hybrid retrieval.

## Fifteen serial requests and trace coverage

All questions used report ID 1/year 2024 and unique session hashes. Database timing proves zero overlap and a minimum gap of `10.005034` seconds after the previous request completed. Exactly 15 request headers and 15 access-log POSTs exist, with no extra retry trace. All S2 rows show a newly written retrieval cache entry rather than a hit. The runner requested `force_refresh=true`; however, the durable S0 completion payload overwrote the S0 start payload, so the flag itself is not retained in the final S0 row. This is reported as a trace-contract limitation, not silently inferred.

| # | Request | Topic | Final | S0–S8 | Numeric/citation result |
|---:|---|---|---|---|---|
| 1 | `2ef547d7` | 营收 | completed | 9/9 | valid / citation valid |
| 2 | `2f143a3c` | 净利润 | completed | 9/9 | valid / citation valid |
| 3 | `a15bd034` | 经营现金流 | partial_success | 8/9 | S6 synthesis empty; S7 absent |
| 4 | `b8d8c581` | ROE | partial_success | 8/9 | S6 timeout; S7 absent |
| 5 | `6c84c0b5` | EPS | partial_success | 9/9 | numeric invalid: `6` |
| 6 | `14176618` | 毛利率/净利率 | partial_success | 9/9 | numeric invalid: `6` |
| 7 | `91ef7054` | 资产负债 | partial_success | 9/9 | numeric invalid: `6` |
| 8 | `29ec92da` | 费用 | partial_success | 8/9 | S6 synthesis empty; S7 absent |
| 9 | `8b9c3e7d` | 分红 | partial_success | 8/9 | S6 timeout; S7 absent |
| 10 | `d17a92d2` | 盈利质量 | partial_success | 8/9 | S6 timeout; S7 absent |
| 11 | `bd1271d0` | 营收质量 | completed | 9/9 | valid / citation valid |
| 12 | `dab052e3` | 投资现金流 | partial_success | 8/9 | S6 timeout; S7 absent |
| 13 | `2c1b6d77` | 筹资现金流 | partial_success | 9/9 | numeric invalid: `121.78`, `20.7%` |
| 14 | `38130dd3` | 风险 | partial_success | 9/9 | numeric invalid: `37.98%`; duplicate `E2` citation |
| 15 | `894d5b5f` | 综合总结 | partial_success | 8/9 | S6 timeout; S7 absent |

Coverage is S0–S6 and S8 `15/15`, S7 `8/15`, complete S0–S8 `8/15`, and explicit S6-failure-to-S8 closure `7/15`. Trace persistence failures are `0/15`. The seven absent S7 rows are expected failure endpoints after S6; they are not claimed as complete traces.

### Structured financial field durability limitation

The S6 start call contains `structured_financial_data`, but the S6 finish upsert replaces its payload with `raw_llm_result`, `citation_fields`, and `error`. Consequently the requested structured fields cannot be read durably for any of the 15 requests. The raw LLM results say fields were empty for EPS, margin, and balance-sheet samples; the financing-cash-flow result says its source raw text contained the two reported net cash-flow values; the risk result says only revenue was structured. These are model-side statements, not a preserved canonical structured-field snapshot. Therefore no D6 attribution is confirmed.

## Unsupported-token attribution matrix

| Request | Token | Complete answer sentence | First observed | Evidence finding | Classification |
|---|---|---|---|---|---|
| `6c84c0b5` | `6` | “已接入的6条年报证据片段中未包含EPS数据。” | S1 | Count of retrieved snippets, not a financial number | `D7_OTHER_NON_FINANCIAL_METADATA` |
| `14176618` | `6` | “但本次结构化财务字段为空，已接入的6条证据片段主要涉及子公司关系、关联交易、术语释义及内部控制等内容，未包含利润表相关财务指标。” | S1 | Count of retrieved snippets, not a financial number | `D7_OTHER_NON_FINANCIAL_METADATA` |
| `91ef7054` | `6` | “已接入的 6 条财报片段主要涉及关联交易、存贷款业务、董监高人员信息及报酬说明，未包含资产总额、负债总额、流动资产、流动负债等资产负债表结构信息。” | S1 | Count of retrieved snippets, not a financial number | `D7_OTHER_NON_FINANCIAL_METADATA` |
| `2c1b6d77` | `121.78` | “净流出变动额：约增加121.78亿元” | S6 | Chunk 10 contains the two net-flow values but not this calculated difference | `D4_UNSUPPORTED_FINANCIAL_CLAIM` |
| `2c1b6d77` | `20.7%` | “按绝对值计算，净流出扩大约20.7%” | S6 | Chunk 10 explicitly gives the change field as “不适用”; token absent from all 208 chunks | `D4_UNSUPPORTED_FINANCIAL_CLAIM` |
| `38130dd3` | `37.98%` | “交易性金融资产期末余额248,513,280.00元，较上年下降37.98%，主要因控股子公司财务公司上期债务工具投资到期收回。” | S6 | Retrieved chunk 18 has `%` in the column header and signed value `-37.98`; answer uses unsigned semantic decline | `D5_DATE_PERIOD_UNIT_OR_FORMAT_MISMATCH` |

Counts: D4 2, D5 1, D7 3; D1/D2/D3/D6/UNCONFIRMED 0. The exact machine-readable evidence IDs, sentences, statuses, and classifications are in `company_agents_data_r3_3f_candidate_numeric_matrix.json`.

The three S1 values for token `6` must not be interpreted as true causal creation at report selection. `numeric_token_provenance()` performs raw substring search over serialized stage payloads; the digit occurs incidentally in S1 report metadata. The concrete non-financial count is introduced to the model by `ReportChatCopilotAgent` through `len(compacted_chunks)` and appears in S6 output. This staging ambiguity prevents treating the three samples as satisfying the repair-authorization gate.

## D3 regression

Of the eight requests that reached S7, `citation_metadata_leak=false` for all eight. No token is classified D3. Request `38130dd3` failed citation validation because `E2` was duplicated twice; it still had no raw chunk-ID leak and therefore is a citation-validity regression, not `D3_CITATION_METADATA_LEAK`. Seven S6 failures never reached the D3 gate and are reported as not evaluated, not as passes.

## Root-cause gate

`ROOT_CAUSE_NOT_READY`.

- D7 has three independent samples and a concrete prompt/fallback count contract, but the durable first-observed stage is demonstrably ambiguous because it uses substring matching over metadata.
- D4 has two token occurrences but only one independent runtime sample.
- D5 has one sample.
- Canonical structured financial fields were not retained durably, preventing a D6 comparison.

No category simultaneously has two independent samples, reliable first-appearance staging, a complete concrete function/data-contract location, and a demonstrated minimal repair that preserves the overall numeric guard. No next-phase code fix is authorized by this run.

## Production preservation

The production backend identity after the run is unchanged from the recorded pre-phase identity:

- Container: `tradingagents-backend-1`.
- ID: `c9567bfdfec4892823d7a5febd09d1cba2e4fac2ba6dd300082f74bfd0140bee`.
- Image: `sha256:48a50ce2435e379c46f0ed0afa1878a5f9c8e9f223dcb418bb4bbc1a944987db`.
- Created: `2026-08-23T01:34:13.297204344Z`.
- Started: `2026-08-23T01:34:14.117434553Z`.
- State: running; restart count 0; no bind mounts.
- Network: `tradingagents_internal`, not the candidate network.

It was not stopped, restarted, replaced, mounted, attached to the candidate network, or sent candidate traffic. Production DB and Redis were not connected or written.

Final decision: `ROOT_CAUSE_NOT_READY` / `HOLD_1_PERCENT`.
