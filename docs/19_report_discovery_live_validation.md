# Phase 6E — 真实公网 PDF 发现率验证

**日期:** 2026-07-06  
**状态:** 已实现 ✓  
**版本:** Phase 6E

---

## 1. 目的

在真实公网环境对 ReportDiscoveryAgent 进行端对端发现率测试，验证：

1. CNINFO / SSE / SZSE 三个数据源的实际可达性
2. 置信度评分的实际分布（高置信 ≥ 0.75 的比例）
3. 自动入库触发情况
4. 候选候选质量（误匹配、摘要误命中等）

---

## 2. 验证脚本

```
backend/scripts/validate_report_discovery_live.py
```

### 用法

```bash
cd backend
python scripts/validate_report_discovery_live.py
```

### 测试股票列表

| 代码   | 名称   | 交易所 |
|--------|--------|--------|
| 600519 | 贵州茅台 | SH |
| 000858 | 五粮液   | SZ |
| 600036 | 招商银行 | SH |
| 300750 | 宁德时代 | SZ |
| 000333 | 美的集团 | SZ |

报告年份：2024（年报/半年报/一季报/三季报）

### 输出

- **控制台**：每只股票逐条打印 `[AUTO/SKIP/MANUAL]` 状态
- **reports/discovery_validation_YYYYMMDD.csv**：结构化 CSV（8 列）
- **reports/discovery_validation_YYYYMMDD.json**：JSON 版本含汇总统计

### CSV 字段

| 字段 | 说明 |
|------|------|
| stock_code | 股票代码 |
| company_name | 公司简称 |
| report_type | annual/semi/q1/q3 |
| source | cninfo/sse/szse/none/error |
| confidence | 置信度 0.0-1.0 |
| auto_insert | 是否触发自动入库（≥ 0.75） |
| title | 候选报告标题 |
| pdf_url | PDF 直链 |
| warnings | 警告信息 |

---

## 3. 预期结果（基线）

| 指标 | 预期 |
|------|------|
| 年报发现率（annual） | ≥ 80%（CNINFO 覆盖全市场） |
| 高置信自动入库率 | ≥ 60% |
| 误匹配率（摘要/非定期报告） | < 10% |
| SZSE 深市发现率 | ≥ 60%（深交所 API 稳定性略低） |

---

## 4. 已知限制

| 限制 | 说明 |
|------|------|
| 依赖公开 API | CNINFO 为公开接口，结构可能变化 |
| Rate limit | 每只股票之间 2 秒延迟，避免频繁请求 |
| Q1/Q3 误匹配 | 季报共用同一 CNINFO category，靠标题过滤 |
| SSE 非沪市返回空 | 非 6/5 开头股票不调用 SSE |

---

## 5. 运行后操作

若发现率偏低（< 60%），可检查：

1. `app/tools/reports/cninfo_report_search_tool.py` 中的 `pageSize` / `category` 字段是否变化
2. `app/tools/reports/base.py::score_candidate` 中置信度阈值是否需要调整
3. CNINFO API 是否临时封锁（重试间隔延长至 3-5 秒）
