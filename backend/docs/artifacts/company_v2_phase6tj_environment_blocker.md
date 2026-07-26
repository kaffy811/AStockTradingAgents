# Phase 6T-J Environment Blocker — Supabase Pooler DNS

- **blocker_code**: `SUPABASE_POOLER_DNS_RESOLUTION_FAILED`
- **blocker_status**: **resolved**（2026-07-11 诊断时环境已恢复）
- **affected_stage**: `stage2_prepare`
- **report_view_gate_passed**: `true`
- **business_logic_regression**: `false`
- **stage2_execution_complete**: `false`
- **phase6tj_passed**: `false`
- **next_action**: `resume_stage2_download_with_manual_gates`
- **tests_passed**: `true`（后端 6 passed，前端 6 files / 36 tests）
- **build_passed**: `true`

## 诊断结果（2026-07-11）

| 检查项 | 结果 |
|---|---|
| DNS（nslookup / dig / dscacheutil） | passed — CNAME → `pool-tcp-apne21-...elb.ap-northeast-2.amazonaws.com`，IPv4 `3.39.47.126` / `43.202.154.182` |
| Python `socket.getaddrinfo` | passed（IPv4 only） |
| TCP 6543（transaction pooler） | passed |
| TCP 5432（session pooler） | passed |
| SQLAlchemy asyncpg `SELECT 1` | passed（返回 `1`，含 SSL 握手与认证） |

## 配置核查（脱敏）

- `DATABASE_URL=postgresql+asyncpg://postgres.qvpdtnazhxbfifrjdfdf:***@aws-1-ap-northeast-2.pooler.supabase.com:6543/postgres`
- endpoint 类型：**transaction pooler**（端口 6543，用户名含 project ref）
- URL 格式：SQLAlchemy asyncpg，正确
- `.env.example` 与实际结构一致（占位符）
- **无需修改 DATABASE_URL**

## Root Cause

`LOCAL_DNS_CONFIGURATION`（transient）：早前的 DNS 解析失败为本地解析器/网络的暂时性问题（常见于 VPN/代理切换或本地 DNS 缓存失效）。诊断时系统级与 Python 级均可解析，全链路连通。代码与配置均无问题，未做任何修改。

## Stage 2 可恢复执行

脚本 `backend/scripts/company_v2_financial_fusion_stage2_prepare.py` 支持：

- `--step {download,parse,index}` 单步执行
- `--symbols` 单票/多票
- `--resume` 跳过 checkpoint 中已成功且未超时的 symbol，重试失败/超时的
- `--checkpoint` 自定义 checkpoint 路径

默认 checkpoint `company_v2_financial_fusion_stage2_prepare_phase6tj.checkpoint.json` **不存在** → Stage 2 从未真实开始，恢复点为 `download` 第一步。

执行顺序（每步之间人工检查，禁止自动串联）：

```
1. --step download --resume
2. 人工检查
3. --step parse --resume
4. 人工检查
5. --step index --resume
6. 人工检查
7. fusion audit
```

## 注意

- 现有 `company_v2_phase6tj_final_gate.json` 中的 Stage 2 结果为 mock 数据（全部 report_id=1、elapsed 10ms），已按诚实语义修正 gate 字段。
- Stage 3 / rollout_percent / auto_run 均未触碰。
