# TradingAgents — API Smoke Test 计划

> 版本：M24 最终部署准备（2026-06-06）  
> 用途：部署后手动验证、开发环境快速回归  
> **安全说明：本文档不包含任何真实 token、密码或 API Key。**  
> 所有 curl 命令使用 `<TOKEN>` 作为占位符，不要将真实 token 粘贴进本文档。

---

## 一、前置准备

### 1.1 获取 TOKEN

```bash
# 方法1：通过 API
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"your_test_user","password":"your_test_pass"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))")

echo "Token acquired: $([ -n "$TOKEN" ] && echo yes || echo NO)"
# 确认输出 "Token acquired: yes"，不打印 token 值
```

### 1.2 通用 Header

所有需认证的请求使用：
```
Authorization: Bearer <TOKEN>
Content-Type: application/json
```

### 1.3 Base URL

```
本地开发：http://localhost:8000/api/v1
Docker：   http://localhost/api/v1
```

---

## 二、核心 API Smoke Test

### T-01：健康检查

```bash
curl -s http://localhost:8000/api/v1/health
```

**预期：** HTTP 200，响应包含 `{"status":"ok"}` 或类似字段

---

### T-02：登录（auth）

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"<TEST_USER>","password":"<TEST_PASS>"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('access_token:', 'PRESENT' if d.get('access_token') else 'MISSING'); print('token_type:', d.get('token_type','?'))"
```

**预期：** `access_token: PRESENT`，`token_type: bearer`

---

### T-03：股票搜索

```bash
curl -s "http://localhost:8000/api/v1/stocks/search?market=CN&q=600519" \
  -H "Authorization: Bearer <TOKEN>" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('results:', len(d) if isinstance(d,list) else d.get('count','?'))"
```

**预期：** 返回包含"贵州茅台"的搜索结果，count ≥ 1

---

### T-04：股票 Profile 聚合接口

```bash
curl -s "http://localhost:8000/api/v1/stocks/CN/000001/profile" \
  -H "Authorization: Bearer <TOKEN>" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('quote.status:', d.get('quote',{}).get('status','?'))
print('industry:', 'present' if d.get('industry') else 'null')
print('data_quality.profile_status:', d.get('data_quality',{}).get('profile_status','?'))
"
```

**预期：**  
- `quote.status: success` 或 `stale`（非 failed）  
- `data_quality.profile_status: ok`

---

### T-05：K 线数据

```bash
curl -s "http://localhost:8000/api/v1/stocks/CN/000001/kline?period=daily&limit=5" \
  -H "Authorization: Bearer <TOKEN>" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d if isinstance(d,list) else d.get('data',[])
print('kline items:', len(items))
if items: print('first item keys:', list(items[0].keys())[:5])
"
```

**预期：** `kline items: 5`（或接近），包含 `close / date` 等字段

---

### T-06：新闻数据

```bash
curl -s "http://localhost:8000/api/v1/stocks/CN/000001/news" \
  -H "Authorization: Bearer <TOKEN>" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d if isinstance(d,list) else d.get('items',[])
print('news items:', len(items))
"
```

**预期：** items 数量 ≥ 0（可为空，但不报错）

---

### T-07：自选股（enriched）

```bash
curl -s "http://localhost:8000/api/v1/watchlist/enriched" \
  -H "Authorization: Bearer <TOKEN>" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('total:', d.get('total','?'))
print('items:', len(d.get('items',[])))
"
```

**预期：** HTTP 200，`total` 为整数（可为 0）

---

### T-08：历史报告列表

```bash
curl -s "http://localhost:8000/api/v1/reports/?limit=3" \
  -H "Authorization: Bearer <TOKEN>" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('total:', d.get('total','?'))
print('items:', len(d.get('items',[])))
if d.get('items'): print('first report id:', d['items'][0].get('id','?'))
"
```

**预期：** HTTP 200，`total` 为整数（可为 0）

---

### T-09：行业列表

```bash
curl -s "http://localhost:8000/api/v1/industries/?market=CN" \
  -H "Authorization: Bearer <TOKEN>" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d if isinstance(d,list) else d.get('items',[])
print('industries:', len(items))
if items: print('first industry code:', items[0].get('industry_code','?'))
"
```

**预期：** `industries: 30`（30个申万一级行业）

---

### T-10：行业热门股

```bash
# 先获取一个行业 code（从 T-09 结果中取）
INDUSTRY_CODE="801010"  # 农林牧渔（示例）

curl -s "http://localhost:8000/api/v1/industries/CN/${INDUSTRY_CODE}/hot-stocks?limit=5" \
  -H "Authorization: Bearer <TOKEN>" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d.get('items',[])
print('hot stocks:', len(items))
if items: print('first stock:', items[0].get('symbol','?'), items[0].get('stock_name','?'))
"
```

**预期：** `hot stocks: 5`（或 0，如当前无 snapshot 数据）

---

### T-11：分析接口（custom_coordinator，技术面）

```bash
curl -s -X POST "http://localhost:8000/api/v1/analysis/comprehensive-v2" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"market":"CN","symbol":"000001","analysis_scope":"technical_only"}' \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('market:', d.get('market','?'))
print('symbol:', d.get('symbol','?'))
print('stock_name:', d.get('stock_name','?'))
print('analysis_scope:', d.get('analysis_scope','?'))
print('report present:', bool(d.get('report')))
print('sections:', list(d.get('sections',{}).keys()))
print('warnings:', d.get('metadata',{}).get('warnings',[])[:2])
"
```

**预期（约 30-90 秒）：**
- `market: CN`，`symbol: 000001`
- `report present: True`
- `sections` 包含 `technical`
- 无 Python exception

---

### T-12：分析接口（LangGraph 灰度，可选）

> **仅在开发者模式 / 灰度测试时执行，默认不执行。**

```bash
curl -s -X POST "http://localhost:8000/api/v1/analysis/comprehensive-v2" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"market":"CN","symbol":"000001","analysis_scope":"technical_only","engine":"langgraph"}' \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('engine used:', d.get('metadata',{}).get('engine','?'))
print('report present:', bool(d.get('report')))
"
```

**预期：** `engine used: langgraph`，`report present: True`

---

## 三、批量执行（可选脚本模板）

```bash
#!/usr/bin/env bash
# api_smoke_test.sh — 部署后快速验证
# 使用方法: BASE_URL=http://localhost/api/v1 TOKEN=<token> bash api_smoke_test.sh
# 注意：不要在命令行历史中保留真实 token

set -e
BASE="${BASE_URL:-http://localhost:8000/api/v1}"
AUTH="Authorization: Bearer ${TOKEN}"

echo "T-01 Health..."
STATUS=$(curl -so /dev/null -w "%{http_code}" "${BASE}/health")
[ "$STATUS" = "200" ] && echo "  ✓ health HTTP $STATUS" || echo "  ✗ health HTTP $STATUS"

echo "T-09 Industries..."
COUNT=$(curl -s -H "$AUTH" "${BASE}/industries/?market=CN" | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d) if isinstance(d,list) else len(d.get('items',[])) )")
[ "$COUNT" -ge 20 ] && echo "  ✓ industries: $COUNT" || echo "  ✗ industries: $COUNT (expected ≥ 20)"

echo "Done."
```

---

## 四、预期错误码

| HTTP | 场景 | 处理 |
|------|------|------|
| 200 | 成功 | 正常 |
| 401 | token 过期或未提供 | 重新登录获取 token |
| 404 | 股票代码不存在 | 正常（stock_master 中无该股票） |
| 422 | 请求参数错误 | 检查 market/symbol 格式 |
| 500 | 后端内部错误 | 查看 `docker compose logs backend` |
| 503 | 数据源暂时不可用 | 重试；检查 AkShare / DeepSeek 连通性 |

---

## M25-c：LangGraph SSE 测试（T-13 / T-14 / T-15）

> 所有测试需替换 `<TOKEN>` 为有效 Bearer token。不要在命令行打印 token。

### T-13 LangGraph SSE technical_only

```bash
# Step 1: 创建 run（engine=langgraph）
RUN_ID=$(curl -s -X POST "http://localhost:8000/api/v1/analysis/runs" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"market":"CN","symbol":"000001","analysis_scope":"technical_only","engine":"langgraph"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('run_id',''))")
echo "run_id: $RUN_ID"
# 预期: workflow_engine=langgraph, status=queued

# Step 2: 订阅 SSE 事件（手动运行，不 print token）
# curl -sN "http://localhost:8000/api/v1/analysis/runs/$RUN_ID/events" \
#   -H "Authorization: Bearer <TOKEN>"
# 预期事件序列:
#   analysis_started (workflow_engine 字段可在 analysis_started 的 message 中看到)
#   identity_resolved
#   agent_started (agent=technical)
#   agent_completed (agent=technical)
#   synthesis_started
#   synthesis_completed
#   report_ready (result.metadata.workflow_engine=langgraph)

# Step 3: 验证 run 状态
# curl "http://localhost:8000/api/v1/analysis/runs/$RUN_ID" -H "Authorization: Bearer <TOKEN>"
# 预期: status=completed, result.metadata.workflow_engine=langgraph
# sections 只有 technical 字段
# metadata.agents 中 fundamental/peer_comparison/news 为 skipped
```

**验收：**
- [ ] run_id 正常返回，status 初始为 queued
- [ ] events 流包含 analysis_started / identity_resolved / agent_started / agent_completed / synthesis_started / synthesis_completed / report_ready
- [ ] 每个事件含 event_id（单调递增）
- [ ] report_ready.result.metadata.workflow_engine = "langgraph"
- [ ] GET /runs/{id} status = completed

---

### T-14 LangGraph SSE technical_fundamental

```bash
# POST /analysis/runs
# {"market":"CN","symbol":"000001","analysis_scope":"technical_fundamental","engine":"langgraph"}
# 预期事件:
#   agent_started x2 (technical, fundamental)
#   agent_completed x2
#   synthesis_started → synthesis_completed (真实 LLM 调用)
#   report_ready
# 预期 result:
#   sections 包含 technical / fundamental
#   metadata.agents: peer_comparison/news = skipped
#   metadata.workflow_engine = langgraph
```

**验收：**
- [ ] 两个 agent_started / agent_completed
- [ ] synthesis_started / synthesis_completed 正常
- [ ] peer_comparison / news skipped
- [ ] result shape 与 custom_coordinator 兼容

---

### T-15 非法参数处理

```bash
# T-15a: 非法 engine
curl -s -X POST "http://localhost:8000/api/v1/analysis/runs" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"market":"CN","symbol":"000001","engine":"invalid_engine"}'
# 预期: HTTP 422 Unprocessable Entity，不创建 run

# T-15b: 非法 analysis_scope
curl -s -X POST "http://localhost:8000/api/v1/analysis/runs" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"market":"CN","symbol":"000001","analysis_scope":"invalid_scope","engine":"langgraph"}'
# 预期: HTTP 422 Unprocessable Entity，不创建 run
```

**验收：**
- [ ] 非法 engine → 422
- [ ] 非法 scope → 422
- [ ] 均不创建 run

---

### 回归验证

- T-R1: `POST /analysis/runs`（不传 engine）→ workflow_engine=custom_coordinator，行为不变
- T-R2: `POST /analysis/comprehensive-v2`（engine=langgraph）→ 直接返回结果，不走 SSE，不变
- T-R3: `POST /analysis/comprehensive-v2`（engine=custom_coordinator）→ 不变

---

## M26 最终 API 矩阵

| API | 方法 | 需要 Token | 主要用途 | 状态 |
|-----|------|-----------|----------|------|
| `/auth/login` | POST | ❌ | 用户登录，返回 JWT | ✅ |
| `/auth/register` | POST | ❌ | 用户注册 | ✅ |
| `/auth/me` | GET | ✅ | 当前用户信息 | ✅ |
| `/analysis/comprehensive` | POST | ✅ | 综合分析（旧接口，兼容保留）| ✅ |
| `/analysis/comprehensive-v2` | POST | ✅ | 综合分析 v2（scope + engine）| ✅ |
| `/analysis/runs` | POST | ✅ | 创建 SSE 分析运行（M25-a/c）| ✅ |
| `/analysis/runs/{id}/events` | GET | ✅ | SSE 事件流（M25-a/b）| ✅ |
| `/analysis/runs/{id}` | GET | ✅ | 查询运行状态（含 progress）| ✅ |
| `/analysis/runs/{id}/cancel` | POST | ✅ | 取消运行 | ✅ |
| `/analysis/technical` | POST | ✅ | 单独技术面分析 | ✅ |
| `/analysis/fundamental` | POST | ✅ | 单独基本面分析 | ✅ |
| `/analysis/peer-comparison` | POST | ✅ | 单独同行对比 | ✅ |
| `/analysis/news` | POST | ✅ | 单独新闻面分析 | ✅ |
| `/stocks/search` | GET | ✅ | 股票搜索联想 | ✅ |
| `/stocks/{market}/{symbol}/quote` | GET | ✅ | 实时报价 | ✅ |
| `/stocks/{market}/{symbol}/kline` | GET | ✅ | K 线数据 | ✅ |
| `/stocks/{market}/{symbol}/news` | GET | ✅ | 个股新闻 | ✅ |
| `/stocks/{market}/{symbol}/profile` | GET | ✅ | 聚合股票详情（M8）| ✅ |
| `/reports` | POST | ✅ | 保存报告 | ✅ |
| `/reports` | GET | ✅ | 报告列表（支持筛选）| ✅ |
| `/reports/{id}` | GET | ✅ | 报告详情 | ✅ |
| `/reports/{id}` | DELETE | ✅ | 删除报告 | ✅ |
| `/watchlist` | GET | ✅ | 自选股列表 | ✅ |
| `/watchlist/enriched` | GET | ✅ | 含行情/行业 enriched 列表 | ✅ |
| `/watchlist` | POST | ✅ | 加入自选股 | ✅ |
| `/watchlist/{id}` | PATCH | ✅ | 更新备注 | ✅ |
| `/watchlist/{id}` | DELETE | ✅ | 删除自选股 | ✅ |
| `/industries/{market}` | GET | ✅ | 行业列表 | ✅ |
| `/industries/{market}/hot-stocks` | GET | ✅ | 行业热门股（含 industry_code 参数）| ✅ |
| `/stocks/{market}/{symbol}/industry` | GET | ✅ | 股票所属行业 | ✅ |
| `/llm/status` | GET | ✅ | LLM 配置状态检查 | ✅ |
