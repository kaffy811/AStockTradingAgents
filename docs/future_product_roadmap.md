# TradingAgents — 后续产品路线图

**基准版本：** MVP v0.7（2026-05-29）  
**文档用途：** 后续开发方向规划，面试/展示时的"未来展望"部分

---

## 路线图总览

```
当前状态（MVP v0.7）
│
├── Phase L1  LangGraph 工作流重构           （架构层）
├── Phase D1  Docker 容器化 + 正式部署        （基础设施层）
├── Phase P1  产品能力增强                    （功能层）
├── Phase M1  微信小程序适配                  （端层）
└── Phase A1  App 化                         （端层）
```

各 Phase 可并行推进；Phase D1 是 M1/A1 的前置（需要稳定的后端服务地址）。

---

## Phase L1 — LangGraph 工作流重构

### 背景

当前 `ComprehensiveAnalysisCoordinator` 是**自定义多 Agent Coordinator**，通过 `asyncio.gather` 并发执行 4 个分析 Agent，实现了基本的并行化。但该架构存在以下局限：

- Agent 执行状态不可持久化（请求结束即销毁）
- 无法基于中间结果做条件跳转（例如：技术面信号极弱时跳过加深分析）
- 单个 Agent 失败后无标准化的断点续跑机制
- 无法实现 Human-in-the-loop（例如数据质量差时暂停等待用户确认）

### 目标

将固定流程 Coordinator 升级为基于 LangGraph `StateGraph` 的可状态追踪、可条件分支、可中断恢复的 Agent Workflow。

### 核心概念映射

| 当前自定义概念 | LangGraph 对应 |
|--------------|--------------|
| `analyze_async()` 主流程 | `StateGraph` |
| 每个 `Agent.analyze()` | `Node` |
| Agent 输出传递给综合报告 | `Edge` |
| 基于 Agent 状态决定下一步 | `Conditional Edge` |
| `{report, sections, metadata}` 中间结果 | `State`（TypedDict） |
| 断点恢复 / 部分重跑 | `Checkpoint`（`MemorySaver` / `PostgresSaver`） |
| 基本面数据质量差暂停确认 | `Human-in-the-loop`（`interrupt_before/after`） |

### 实施步骤

| 子阶段 | 内容 | 交付物 |
|--------|------|--------|
| L1-a | 将 4 个 Agent 包装为 LangGraph Node；定义 `AnalysisState` TypedDict（复用当前 metadata dict 结构） | `agents/workflow/comprehensive_graph.py` |
| L1-b | 添加 `MemorySaver` Checkpoint；验证断点恢复行为 | smoke test 验证断点续跑 |
| L1-c | 添加第一个 Conditional Edge（技术面信号强度 → 决定是否触发加深分析节点） | 新增 `DeepTechnicalNode` |
| L1-d | 新增 `POST /api/v1/analysis/comprehensive-v2` 接口；旧接口保留不动 | 双接口并行运行，A/B 对比 |
| L1-e | 前端流量逐步切换；监控稳定后弃用旧接口 | 旧接口下线 |

### 迁移策略

**核心原则：不直接替换旧接口。**

```
# 保留（不动）
POST /api/v1/analysis/comprehensive        ← 自定义 Coordinator

# 新增（LangGraph）
POST /api/v1/analysis/comprehensive-v2    ← LangGraph StateGraph
```

新旧接口并行运行期间，可在前端 Feature Flag 中切换，便于 A/B 验证和快速回滚。

---

## Phase D1 — Docker 容器化 + 正式部署

### 背景

当前项目运行在本地开发环境，无法对外提供稳定服务地址，是 Phase M1/A1 的硬性前置。

### 目标

将 FastAPI 后端 + Vue 前端 + Redis 打包为 Docker Compose 服务，部署到云服务器（阿里云 / 腾讯云 / AWS），配置 HTTPS 和域名，使项目可通过公网访问。

### 技术方案

```yaml
# docker-compose.yml（示意）
services:
  backend:
    build: ./backend
    image: trading-agents-backend
    env_file: .env.prod
    depends_on: [db, redis]
    ports: ["8000:8000"]

  frontend:
    build: ./frontend
    image: trading-agents-frontend
    # Nginx 静态文件服务 + API 反代

  redis:
    image: redis:7-alpine
    volumes: [redis_data:/data]

  # Supabase PostgreSQL 保持云端，不自托管
```

### 部署清单

| 项目 | 内容 |
|------|------|
| 域名 + HTTPS | 注册域名，Let's Encrypt 自动续期 SSL |
| Nginx 反代 | 前端静态文件服务 + `/api/` 反代到 FastAPI |
| 环境变量隔离 | `.env.dev` / `.env.prod` 分离；密钥走环境变量注入，不进 git |
| Redis 持久化 | AOF 持久化，防容器重启缓存清零 |
| 健康检查 | `/health` 接口 + Docker healthcheck |
| CI/CD | GitHub Actions：push to main → build → deploy（可选） |

### 安全注意事项

- Supabase 连接串、Anthropic API Key、JWT Secret 走 Docker secret 或环境变量，绝不硬编码
- CORS 白名单限制为正式域名（移除 `*`）
- FastAPI 关闭 `/docs` 和 `/redoc`（生产环境）

---

## Phase P1 — 产品能力增强

### P1-a 技术面图表

- 使用 `lightweight-charts`（TradingView 开源库）或 `ECharts` 渲染 K线图
- 在报告详情页/分析页展示：K线（OHLCV）+ MA5/MA20/MA60 叠加 + MACD 副图 + RSI 副图
- 数据来源：复用已有 `StockDataService` kline 数据，无需新接口

### P1-b 行业热门榜

- 前端新增"行业热门"页面（`/industry-hot`）
- 展示各申万一级行业 Top 5 热门股（基于已有 `industry_hot_stock_snapshot` 表）
- 支持按行业筛选、按 Hot Score 排序、一键进入综合分析

### P1-c 每日摘要

- 定时任务（Celery Beat / APScheduler）每日收盘后触发
- 对用户自选股列表中的股票自动生成轻量摘要（行情变化 + 最近新闻 headline）
- 摘要存储到新表 `daily_digest`，用户进入自选股页时展示

### P1-d 异动提醒

- 监控自选股列表中的股票价格/成交量异动（涨跌幅 >±5%，成交量 >2× 均值）
- 生成 in-app 通知（前端 badge + 弹出卡片）
- Phase M1/A1 后可扩展为微信推送 / App 推送

### P1-e 报告对比

- 允许用户选择同一股票的两份历史报告并排对比
- 高亮差异段落（基于 Agent 状态变化 / warnings 变化）
- 前端复用已有 `HistoryDetailView`，新增 `CompareView`

---

## Phase M1 — 微信小程序适配

### 前置条件

- Phase D1 完成（需要稳定的 HTTPS API 地址）
- 完成微信小程序开发者账号注册

### 技术方案

| 方向 | 方案 |
|------|------|
| 框架 | uni-app（一套代码同时编译微信小程序 + H5 + App） |
| 认证 | 微信一键登录（`wx.login` → 后端换 session_key → 生成 JWT），替代或兼容当前 email/password 登录 |
| API 复用 | 100% 复用已有 FastAPI 后端，无需改后端接口 |
| 页面优先级 | 自选股 → 综合分析 → 历史报告（三个核心页先行，其他页面后续迭代） |

### 小程序特有注意事项

- 微信小程序限制使用的第三方 CSS/JS（DOMPurify 可能需要验证兼容性）
- 小程序无 DOM API，Markdown 渲染需改用 `towxml` 或 `mp-html` 等小程序适配库
- 单包大小限制 2MB，需分包（主包 + 分析详情包 + 历史报告包）

---

## Phase A1 — App 化

### 技术方案

| 方向 | 方案 |
|------|------|
| 框架 | uni-app（M1 同一套代码，编译 iOS/Android App） |
| 推送 | Apple APNs + Firebase FCM，用于异动提醒（Phase P1-d） |
| 本地缓存 | SQLite 缓存最近 20 条报告，离线可查看 |
| 认证 | Sign in with Apple（iOS）/ Google Sign-In（Android），兼容当前 JWT 方案 |

### M1/A1 统一注意事项

- 后端 API 结构**无需改动**，所有端共享同一套 REST API
- uni-app 开发时建议先完成 H5 版本验证，再编译小程序/App，减少平台适配工作量
- 第一版小程序/App 不追求功能完整性，以"自选股 + 一键分析 + 历史报告"为核心体验

---

## 各 Phase 依赖关系

```
MVP v0.7
    │
    ├─── P1-a（技术面图表）      独立，随时可做
    ├─── P1-b（行业热门榜）      独立，随时可做
    ├─── L1（LangGraph 重构）    独立，不依赖部署
    │
    └─── D1（Docker 部署）
              │
              ├─── P1-c（每日摘要）      需要定时任务 + 稳定部署
              ├─── P1-d（异动提醒）      需要稳定部署 + 推送通道
              │
              ├─── M1（微信小程序）      需要 HTTPS API 地址
              └─── A1（App）             需要 HTTPS API 地址 + 推送配置
```

---

*文档更新于 2026-05-29*
