# 行业热门股与动态同行系统设计文档

**版本：** Phase 1A–1E + Phase 2E-1（截至 2026-05-29）  
**作者：** kaffy811

---

## 1. 背景与目标

### 1.1 问题陈述

TradingAgents MVP v0.1 的同行对比模块依赖 `PEER_MAP`——一个硬编码的字典，将特定股票映射到手动选定的可比公司。这一方案存在根本性局限：

| 问题 | 影响 |
|------|------|
| 覆盖范围极小（约 10 只） | A股 5000+ 只股票中绝大多数无同行数据 |
| 人工维护成本高 | 无法随市场结构变化自适应 |
| 热门分析对象（000001 等）无同行 | 同行对比报告维度空洞，LLM 被迫降级 |

### 1.2 设计目标

1. **零破坏扩展**：PEER_MAP 优先级不变，旧代码路径无修改
2. **自动覆盖 CN 市场**：无 PEER_MAP 配置的 A股股票自动获得行业内热门股作为可比样本
3. **数据驱动而非随机**：同行候选须有客观排序依据（热度、成交量）
4. **透明边界声明**：报告中必须说明动态同行的选取口径和局限性
5. **可扩展架构**：设计上支持未来接入更精细的基本面相似度排序

---

## 2. 为什么是申万行业分类

### 2.1 备选方案对比

| 方案 | 可用性 | 说明 |
|------|--------|------|
| AkShare `sw_index_third_cons`（申万成分接口） | ❌ 不可用 | Phase 0 探针测试验证：返回空 DataFrame，接口已失效 |
| AkShare `stock_board_industry_name_em` | ✅ 可用 | 东方财富行业，可在线拉取行业成分 |
| yfinance sector 字段 | ⚠ 覆盖不全 | 港股/小市值股覆盖差，字段为英文大类 |
| Wind / Bloomberg | ❌ 需付费 | 不在 MVP 技术栈范围 |
| 自定义 LLM 分类 | ❌ 禁止 | 设计约束：禁止使用 LLM 进行行业分类 |

申万一级行业（31 大类）是 A股最广泛使用的行业分类标准，通过东方财富接口可获取成分，再离线映射至申万代码是目前最稳定的方案。

### 2.2 为什么 PEER_MAP 仍是最高优先级

动态同行代表"市场热度相近"，而 PEER_MAP 代表"业务高度可比"。在基本面对比场景下，业务相似性优先于市场热度。例如：

- `600519`（贵州茅台）的 PEER_MAP 包含五粮液、泸州老窖——都是白酒行业，财务结构直接可比
- 如果改用 dynamic_hot，同行可能包含食品饮料行业中当日成交量最大的公司，不一定是白酒企业

PEER_MAP 的人工精选质量高于自动热度排序，因此保持最高优先级。

---

## 3. Hot Score 公式

### 3.1 设计思路

Hot Score 需要回答：**在同一行业内，哪只股票当前最受市场关注？**

两个最直接的市场信号：
- **成交额**（绝对值）：反映资金关注度，流动性越高的股票基本面数据越完整
- **涨跌幅的绝对值**（波动性）：反映市场分歧程度，高波动通常伴随高关注度

### 3.2 公式

```
HotScore = 0.7 × norm(成交额) + 0.3 × norm(|涨跌幅|)
```

其中：

```
norm(x) = (x - min) / (max - min)   [行业内 min-max 归一化]
```

- 当行业内 `max == min`（所有股票成交额相同）时 `norm = 0.0`，避免除零
- **成交额权重 0.7**：确保流动性是主要排序因子，低流动性股票基本面数据通常不完整
- **涨跌幅权重 0.3**：补充市场热度信号，单纯按成交额排序会长期偏向大市值股

### 3.3 过滤规则

- **ST / *ST 股票**：过滤（`name LIKE 'ST%'` 或 `name LIKE '*ST%'`）
- **退市股票**：过滤（`name LIKE '%退%'`）
- **北交所**：当前数据源不覆盖，自然排除

---

## 4. 数据库表结构

### 4.1 `sw_industry_classification`

记录 A股个股的申万一级行业归属。

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `market` | VARCHAR(10) | `CN` |
| `symbol` | VARCHAR(20) | 股票代码（如 `000001`） |
| `sw_level1_code` | VARCHAR(20) | 申万一级行业代码（如 `801780`） |
| `sw_level1_name` | VARCHAR(100) | 申万一级行业名称（如 `银行`） |
| `source` | VARCHAR(50) | 数据来源（如 `eastmoney_board`） |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

索引：`(market, symbol)` 唯一索引

### 4.2 `industry_hot_stocks`

记录每日行业热门股快照和 Hot Score。

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `snapshot_date` | DATE | 快照日期 |
| `market` | VARCHAR(10) | `CN` |
| `industry_code` | VARCHAR(20) | 申万一级行业代码 |
| `industry_name` | VARCHAR(100) | 申万一级行业名称 |
| `symbol` | VARCHAR(20) | 股票代码 |
| `name` | VARCHAR(100) | 股票名称 |
| `hot_score` | FLOAT | Hot Score v1 值（0.0–1.0） |
| `rank` | INTEGER | 行业内排名（1 = 最热） |
| `amount` | FLOAT | 成交额（元） |
| `change_pct` | FLOAT | 涨跌幅（%） |
| `score_factors` | JSONB | `{norm_amount, norm_abs_change}` 中间值 |
| `created_at` | TIMESTAMP | |

索引：`(snapshot_date, market, industry_code, rank)` 组合索引

---

## 5. 服务调用链

```
GET /stocks/{market}/{symbol}/peers/fundamentals
GET /analysis/peer-comparison
GET /analysis/comprehensive
            │
            ▼
  PeerComparisonAnalystAgent.analyze_async(db, market, symbol)
            │
            ▼
  PeerComparisonService.get_peer_fundamentals_dynamic(db, market, symbol)
            │
            ├─ [PEER_MAP 命中] → 直接使用手动同行列表
            │                     peer_source = "manual_map"
            │
            └─ [PEER_MAP 未命中] → DynamicPeerDiscoveryService.discover_peers(db, market, symbol)
                                          │
                                          ├─ CN 市场 → 查 sw_industry_classification → 查 industry_hot_stocks
                                          │            peer_source = "dynamic_hot"
                                          │
                                          └─ 无行业映射 / HK → peers=[], fallback_reason 说明
                                                               peer_source = "none"
```

**ComprehensiveAnalysisCoordinator（Phase 1E）**

```
ComprehensiveAnalysisCoordinator.analyze_async(db, market, symbol)
            │
            ▼
  _run_agents_parallel_async(db, market, symbol)  [asyncio.gather]
            │
            ├─ asyncio.to_thread(TechnicalAnalystAgent.analyze, ...)
            ├─ asyncio.to_thread(FundamentalAnalystAgent.analyze, ...)
            ├─ PeerComparisonAnalystAgent.analyze_async(db, ...)   ← 直接 await（已是协程）
            └─ asyncio.to_thread(NewsAnalystAgent.analyze, ...)
```

---

## 6. API 一览

| 接口 | 方法 | 说明 |
|------|------|------|
| `/industries/{market}/{symbol}/classification` | GET | 个股申万一级行业分类 |
| `/industries/{market}/{industry_code}/hot-stocks` | GET | 指定行业 Hot Score 排行（`?limit=10`） |
| `/industries/stocks/{market}/{symbol}/dynamic-peers` | GET | 个股动态同行发现（`?limit=5`） |
| `/stocks/{market}/{symbol}/peers/fundamentals` | GET | 同行基本面对比（Phase 1D 后接入 dynamic_hot） |
| `/analysis/peer-comparison` | POST | 同行对比分析报告（Phase 1D 后接入 dynamic_hot） |
| `/analysis/comprehensive` | POST | 综合分析（Phase 1E 后 peer_comparison 接入 dynamic_hot） |

**路由注册顺序注意事项：**  
`/industries/stocks/{market}/{symbol}/dynamic-peers` 必须注册在 `/{market}/{industry_code}/...` 之前，否则 FastAPI 会将 `stocks` 匹配为 `industry_code` 路径参数。

---

## 7. 关键测试用例

### 7.1 PEER_MAP 优先级验证

**CN/600519（贵州茅台）**

```bash
GET /industries/stocks/CN/600519/dynamic-peers
```

预期：
- `data_quality.peer_source = "manual_map"`
- `peers` 列表来自 PEER_MAP 手动配置

### 7.2 dynamic_hot 激活

**CN/000001（平安银行）**

```bash
GET /industries/stocks/CN/000001/dynamic-peers?limit=5
```

预期：
- `data_quality.peer_source = "dynamic_hot"`
- `industry.industry_code = "801780"`（银行）
- `peers` 列表非空（≥1 只）
- `peers[0].hot_score` 为浮点数
- `peers` 中不含 ST 股

### 7.3 行业映射未找到降级

**CN/300750（宁德时代）**（申万 SW 映射暂未覆盖）

```bash
GET /industries/stocks/CN/300750/dynamic-peers
```

预期：
- `peers = []`
- `data_quality.peer_source = "none"`
- `data_quality.fallback_reason` 非空，注明原因

### 7.4 dynamic_hot 报告边界声明

```bash
POST /analysis/peer-comparison
{"market": "CN", "symbol": "000001"}
```

预期报告中包含：
- 「对比样本说明」章节注明 Hot Score 口径
- 「基于成交额/涨跌幅，代表市场关注度，不代表基本面质量或投资价值」
- 不出现「更优质」「更值得投资」等强结论

---

## 8. 当前限制

| # | 限制 | 说明 |
|---|------|------|
| 1 | 仅覆盖 CN 市场 | 申万行业分类不覆盖 HK；HK 股票始终 `peer_source="none"` |
| 2 | 创业板/科创板 SW 映射不完整 | 部分 300xxx / 688xxx 股票 `sw_industry_classification` 中无记录 |
| 3 | Hot Score 基于当日快照 | 需要数据库中有对应 `snapshot_date` 的数据；若 `industry_hot_stocks` 表为空则降级 |
| 4 | Hot Score v1 口径较粗 | 成交额 + 涨跌幅权重固定，未考虑市值、换手率、财务相似度 |
| 5 | 同行数量上限 5 只 | 默认 `limit=5`，可调整，但过多同行会增加基本面并发拉取的压力 |
| 6 | 行业分类精度限于申万一级 | 银行行业内 000001 与某农商行同属一级，但业务差异较大 |

---

## 9. 未来升级路径

| 优先级 | 升级项 | 说明 |
|--------|--------|------|
| 高 | 补全创业板/科创板 SW 映射 | 从东方财富行业成分接口拉取 300xxx / 688xxx，写入 `sw_industry_classification` |
| 高 | Hot Score 定时刷新任务 | 添加定时任务（每日收盘后）自动更新 `industry_hot_stocks` 快照 |
| 中 | 接入申万二级行业 | 一级行业粒度较粗；用申万二级分类（约 100 个）提升同行精度 |
| 中 | 基于基本面相似度的 peer ranking | 在 Hot Score 候选集基础上，按市值区间、PE/PB 相似度二次过滤 |
| 低 | HK 市场同行支持 | 探索港交所行业分类（GIC sector）或腾讯/AkShare HK 行业接口 |
| 低 | 向量相似度 peer discovery | 将基本面字段向量化，用余弦相似度替代规则匹配；需向量数据库支持 |

---

## 11. Phase 2E-1 — 全量申万一级行业映射（2026-05-29）

### 11.1 背景

Phase 1A–1E 完成后，`stock_industry_map` 表仅含少量 sample 数据（约 10 只股票），导致大多数 A 股（含 CN/300750 宁德时代）在 `DynamicPeerDiscoveryService` 中找不到行业映射，`peer_source` 降级为 `"none"`。

### 11.2 数据源选型

| 方案 | 结果 |
|------|------|
| legulegu.com（AkShare `sw_index_*_info`） | ❌ 当前 504 Gateway Timeout |
| AkShare `sw_index_third_cons` | ❌ 列数 mismatch（15 列 vs 硬编码 17 列） |
| EastMoney `stock_board_industry_cons_em` | ❌ Clash 代理环境 ProxyError |
| **swsresearch.com 官方 JSON API** | ✅ 选用 |

`index_component_sw(symbol)` 调用路径：

```
AkShare index_component_sw(symbol='801780')
  → GET https://www.swsresearch.com/institute-sw/api/index_publish/details/component_stocks/
      ?swindexcode=801780&page=1&page_size=10000
  → 返回 JSON，直接解析 data.results[].{stockcode, stockname}
```

直接调用底层 API（`verify=False` 绕过 SSL 证书问题）可完全替代 legulegu.com。

### 11.3 生成结果

| 指标 | 值 |
|------|----|
| 覆盖行业数 | 30 / 31 个 SW 2021 L1 行业 |
| 覆盖股票数 | **5,166 只** |
| 801850 美容护理 | 0 成分股（API 返回空，已跳过） |
| source 字段 | `sw_2021_swsresearch` |

关键股票验证：

| symbol | stock_name | industry_code | industry_name |
|--------|-----------|---------------|---------------|
| 600519 | 贵州茅台 | 801120 | 食品饮料 |
| 000001 | 平安银行 | 801780 | 银行 |
| 300750 | 宁德时代 | **801730** | **电力设备** ← 原先未覆盖 |

### 11.4 import_industry_map.py 修复

原脚本 SELECT+INSERT 逐行 ORM 方式在 5,000+ 行时触发两个 bug：

1. **autoflush 触发 statement timeout**：SQLAlchemy 在执行 SELECT 前 autoflush 待提交的 INSERT，Supabase 默认 statement_timeout 中断该 INSERT，导致 `asyncpg.QueryCanceledError`
2. **级联 PendingRollbackError**：第一个 INSERT 失败后，session 进入 broken 状态，后续所有操作报 `This Session's transaction has been rolled back`

修复方案：改用 `INSERT ... ON CONFLICT DO UPDATE`（PostgreSQL native upsert）批量执行：
- 行业主表：一次事务 30 条
- 股票映射表：每批 500 条，共 11 批

导入结果：`industry_master upsert=30, stock_industry_map upsert=5166, errors=0`

### 11.5 hot stocks refresh 结果

```
industry_count   = 30
stocks_loaded    = 5523
snapshot_inserted= 140 (28 新行业 × 5 = 140，食品饮料/银行已有今日数据跳过)
```

**已知问题 — refresh duplicate**：`_upsert_snapshots` 函数先 DELETE 旧快照再批量 INSERT，但当 `scored` 列表中同一 `symbol` 出现多次时（行业数据含重复条目），DELETE 成功后 INSERT 第二条违反 `uq_hot_stock_mid_tsv` 约束（`market, industry_code, trade_date, symbol, score_version`）。本次 2 个行业受影响（食品饮料、银行），均为已有今日快照的行业。修复方案：在 `_upsert_snapshots` 中对 `scored` 按 `symbol` 去重后再插入。**暂缓，不影响 MVP 功能。**

### 11.6 Phase 2E-1 前后变化（CN/300750）

| 项目 | Phase 1D–1E（之前） | Phase 2E-1（之后） |
|------|--------------------|--------------------|
| `stock_industry_map` 中的记录 | 无 | `801730 电力设备` |
| `dynamic-peers` peer_source | `"none"` | **`"dynamic_hot"`** |
| dynamic-peers 返回 | `[]`（空） | 4 只电力设备行业热门股 |
| comprehensive peer_comparison | "industry mapping not found" | 电力设备 dynamic_hot 对比表 |

### 11.7 Phase 2E-2 暂缓说明

Phase 2E-2 原定内容：定期自动同步 + 增量更新 + 历史版本管理。

**暂缓原因**：Phase 2E-1 已将 `stock_industry_map` 从 ~10 只 sample 升级为全量 5,166 只，覆盖 30/31 个 SW L1 行业，满足 MVP 动态同行需求。Phase 2E-2 属于运维自动化（定时任务、增量 diff、数据老化），在功能完整性确认前优先级较低。

---

## 10. 设计约束（禁止事项）

在当前版本及后续迭代中，以下事项明确禁止：

- ❌ 使用 LLM 进行行业分类（过慢、成本高、结果不稳定）
- ❌ 修改 TechnicalAnalystAgent / FundamentalAnalystAgent / NewsAnalystAgent
- ❌ 修改 FundamentalDataService / IndustryHotStockService / DynamicPeerDiscoveryService 已有逻辑（只扩展）
- ❌ 引入 Alembic 以外的数据库迁移工具
- ❌ 引入 LangGraph / RAG（当前阶段）
- ❌ 修改旧同步方法 `analyze()` / `get_peer_fundamentals()`（只新增 async 版本）
- ❌ 在 dynamic_hot 报告中出现「更优质」「行业排名」「更值得投资」等强结论
