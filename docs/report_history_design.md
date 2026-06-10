# 报告历史功能设计文档

**日期：** 2026-05-26  
**目标：** 设计"报告历史"功能，让用户生成综合分析后可以保存报告，并在历史列表中查看

---

## 实现状态

| 阶段 | 状态 | 完成内容 |
|------|------|---------|
| **Phase 1 后端** | ✅ 已完成 | `analysis_reports` 表（`create_all` 自动建表）；`POST /api/v1/reports/`、`GET /api/v1/reports/`、`GET /api/v1/reports/{id}`、`DELETE /api/v1/reports/{id}`；权限校验（user_id 过滤 + 404）；curl 全部通过 |
| **Phase 1 前端** | ✅ 已完成 | `src/api/reports.js`（字段映射封装）；`baseFetch` 支持 204 No Content；综合分析页"保存报告"按钮（idle→saving→saved/error 状态机）；`/history` 历史列表页（筛选 + 分页 + 删除）；`/history/:id` 详情页（零修改复用 AgentStatusBar / WarningPanel / MarkdownReport / SectionAccordion）；顶部导航新增"历史报告"入口 |
| **Phase 2** | ⬜ 待开发 | 分析完成后自动弹出"是否保存"提示；自定义确认弹窗（替换 `confirm()`/`alert()`）；Router 导航守卫；分页优化（keyset pagination） |
| **Phase 3** | ⬜ 待开发 | PDF / Markdown 导出；收藏报告（`is_starred` 字段）；报告对比；报告分享链接 |

---

## 1. 功能目标

| # | 目标 | 说明 |
|---|------|------|
| 1 | 每次综合分析完成后保存一份报告 | Phase 1 为用户手动点击保存；Phase 2 自动提示保存 |
| 2 | 用户可以查看自己的历史报告列表 | `/history` 路由，列表形式展示 |
| 3 | 用户可以点击历史报告查看详情 | 与综合分析结果页面格式一致 |
| 4 | 支持按 market / symbol / created_at 查询 | 列表页提供筛选和排序 |
| 5 | 后续支持删除、收藏、导出 | Phase 2 / Phase 3 迭代 |

**非目标（当前阶段）：**
- 不支持报告对比
- 不支持公开分享链接
- 不支持跨账号查看

---

## 2. 数据库表设计

### 2.1 表结构

```sql
CREATE TABLE analysis_reports (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    market       TEXT NOT NULL,                          -- 'CN' | 'HK'
    symbol       TEXT NOT NULL,                          -- '600519' | '700'
    report_type  TEXT NOT NULL DEFAULT 'comprehensive',  -- 预留扩展
    report_md    TEXT NOT NULL,                          -- 综合报告 Markdown
    sections     JSONB NOT NULL DEFAULT '{}',            -- 四个子报告
    metadata     JSONB NOT NULL DEFAULT '{}',            -- generated_at 等
    warnings     JSONB NOT NULL DEFAULT '[]',            -- warning string[]
    agents       JSONB NOT NULL DEFAULT '{}',            -- agent status 字典
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 常用查询索引
CREATE INDEX idx_reports_user_id       ON analysis_reports(user_id);
CREATE INDEX idx_reports_user_created  ON analysis_reports(user_id, created_at DESC);
CREATE INDEX idx_reports_user_symbol   ON analysis_reports(user_id, symbol);
```

### 2.2 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键，自动生成 |
| `user_id` | UUID | 外键关联 `app_users.id`，每条报告归属唯一用户 |
| `market` | text | `'CN'` 或 `'HK'` |
| `symbol` | text | 股票代码，如 `'600519'` |
| `report_type` | text | 当前固定 `'comprehensive'`，预留多报告类型扩展 |
| `report_md` | text | 综合报告原始 Markdown 文本 |
| `sections` | jsonb | `{ technical: str, fundamental: str, peer_comparison: str, news: str }` |
| `metadata` | jsonb | `{ generated_at: str, ... }` |
| `warnings` | jsonb | `["hk_fundamental_limited", ...]` |
| `agents` | jsonb | `{ technical: { status: "success", message: "" }, ... }` |
| `created_at` | timestamptz | 报告创建时间（UTC） |
| `updated_at` | timestamptz | 最后更新时间（保留字段，Phase 1 暂不使用） |

### 2.3 SQLAlchemy Model 草案

```python
# backend/app/models/analysis_report.py
import uuid
from datetime import datetime
from sqlalchemy import Column, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMPTZ
from app.db.base import Base

class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    market      = Column(Text, nullable=False)
    symbol      = Column(Text, nullable=False)
    report_type = Column(Text, nullable=False, default="comprehensive")
    report_md   = Column(Text, nullable=False)
    sections    = Column(JSONB, nullable=False, default=dict)
    metadata_   = Column("metadata", JSONB, nullable=False, default=dict)
    warnings    = Column(JSONB, nullable=False, default=list)
    agents      = Column(JSONB, nullable=False, default=dict)
    created_at  = Column(TIMESTAMPTZ, nullable=False, default=datetime.utcnow)
    updated_at  = Column(TIMESTAMPTZ, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

---

## 3. 后端接口设计

### 3.1 POST `/api/v1/reports` — 保存报告

**Request：**
```json
POST /api/v1/reports
Authorization: Bearer <token>
Content-Type: application/json

{
  "market": "CN",
  "symbol": "600519",
  "report_type": "comprehensive",
  "report_md": "## 综合分析报告\n...",
  "sections": {
    "technical": "...",
    "fundamental": "...",
    "peer_comparison": "...",
    "news": "..."
  },
  "metadata": {
    "generated_at": "2026-05-26T10:30:00+08:00"
  },
  "warnings": ["valuation_fields_missing"],
  "agents": {
    "technical": { "status": "success", "message": "" },
    "fundamental": { "status": "success", "message": "" },
    "peer_comparison": { "status": "degraded", "message": "No peers configured" },
    "news": { "status": "success", "message": "" }
  }
}
```

**Response（201）：**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-05-26T10:30:05.123456Z"
}
```

---

### 3.2 GET `/api/v1/reports` — 查询历史报告列表

**Request：**
```
GET /api/v1/reports?market=CN&symbol=600519&limit=20&offset=0
Authorization: Bearer <token>
```

Query 参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `market` | string | 否 | 筛选市场（CN / HK） |
| `symbol` | string | 否 | 筛选股票代码 |
| `limit` | int | 否 | 每页数量，默认 20，最大 50 |
| `offset` | int | 否 | 分页偏移，默认 0 |

**Response（200）：**
```json
{
  "total": 5,
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "market": "CN",
      "symbol": "600519",
      "report_type": "comprehensive",
      "warnings": ["valuation_fields_missing"],
      "agents": { "technical": { "status": "success" }, "..." : "..." },
      "created_at": "2026-05-26T10:30:05.123456Z"
    }
  ]
}
```

> 列表不返回 `report_md` 和 `sections`（大字段），仅用于列表展示。

---

### 3.3 GET `/api/v1/reports/{report_id}` — 查看单份报告详情

**Request：**
```
GET /api/v1/reports/550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer <token>
```

**Response（200）：**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "market": "CN",
  "symbol": "600519",
  "report_type": "comprehensive",
  "report_md": "## 综合分析报告\n...",
  "sections": {
    "technical": "...",
    "fundamental": "...",
    "peer_comparison": "...",
    "news": "..."
  },
  "metadata": { "generated_at": "2026-05-26T10:30:00+08:00" },
  "warnings": ["valuation_fields_missing"],
  "agents": { "technical": { "status": "success", "message": "" }, "...": "..." },
  "created_at": "2026-05-26T10:30:05.123456Z"
}
```

**权限校验：** 若 `report.user_id ≠ current_user.id`，返回 404（不暴露其他用户报告的存在）。

---

### 3.4 DELETE `/api/v1/reports/{report_id}` — 删除报告

**Request：**
```
DELETE /api/v1/reports/550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer <token>
```

**Response（204 No Content）**

**权限校验：** 若 `report.user_id ≠ current_user.id`，返回 404。

---

## 4. 与综合分析接口的关系

### 方案 A — 前端主动保存（推荐）

综合分析接口只负责返回报告，前端在获得结果后独立调用 `POST /reports`。

```
前端                             后端
  |                               |
  |  POST /analysis/comprehensive |
  |------------------------------>|
  |  { report, sections, ... }    |
  |<------------------------------|
  |                               |
  |  [用户点击"保存报告"]           |
  |                               |
  |  POST /reports                |
  |------------------------------>|
  |  { id, created_at }           |
  |<------------------------------|
```

**优点：**
- `ComprehensiveAnalysisCoordinator` 无需修改
- 保存是可选操作，用户可以选择不保存
- 保存失败不影响分析结果的展示
- 接口职责单一，便于独立测试

**缺点：**
- 前端需要维护额外的"保存"状态和错误处理
- 用户可能忘记保存（Phase 2 可改为自动提示）

---

### 方案 B — 后端自动保存（不推荐，当前阶段）

综合分析接口增加 `save=true` 参数，后端在返回报告时自动写入数据库。

**缺点：**
- 必须修改 `ComprehensiveAnalysisCoordinator` 以注入数据库操作
- 分析失败时可能触发部分写入
- 强制所有分析都保存，无法"只看不存"
- 与数据访问层（SQLAlchemy）耦合到 LLM 协调层，职责混乱

**结论：Phase 1 采用方案 A（前端主动保存）。** 方案 B 可在 Phase 3 作为"自动保存"高级功能讨论，但仍建议用 background task（FastAPI `BackgroundTasks`）实现，而非直接在协调器中同步写入。

---

## 5. 前端页面设计

### 5.1 路由规划

```
/            → ComprehensiveAnalysisView（现有）
/history     → HistoryView（新增）
/history/:id → HistoryDetailView（新增）
```

### 5.2 `/history` — 报告列表页

**布局：**

```
┌─────────────────────────────────────────────────┐
│  [返回分析页]            TradingAgents 报告历史   │
├─────────────────────────────────────────────────┤
│  筛选：[market ▼]  [symbol 输入]  [查询]          │
│  排序：最新在前                                   │
├─────────────────────────────────────────────────┤
│  CN / 600519    贵州茅台                          │
│  2026-05-26 10:30  ✅ 4个Agent成功  [查看] [删除] │
├─────────────────────────────────────────────────┤
│  HK / 700       腾讯控股                          │
│  2026-05-25 18:15  ⚠ 3条警告     [查看] [删除]   │
└─────────────────────────────────────────────────┘
```

**功能要点：**
- 默认展示当前登录用户的所有报告，按 `created_at` 降序排列
- market / symbol 筛选（可组合）
- 每条记录显示：market、symbol、created_at、warning 数量、Agent 状态概览
- [查看] → 跳转 `/history/:id`
- [删除] → 二次确认 → `DELETE /reports/:id` → 列表刷新
- 空状态：显示"暂无历史报告，去分析一支股票吧"

### 5.3 `/history/:id` — 报告详情页

**布局与 `ComprehensiveAnalysisView` 完全复用：**
- `AgentStatusBar`（metadata + market + symbol）
- `WarningPanel`（warnings）
- `MarkdownReport`（report_md）
- `SectionAccordion`（sections）
- 顶部添加"返回历史列表"按钮

**数据来源：** `GET /api/v1/reports/:id`，响应结构与综合分析接口一致，可直接复用相同的展示组件。

---

## 6. 权限设计

| 规则 | 实现方式 |
|------|---------|
| 用户只能看自己的报告 | 所有 SQL 查询加 `WHERE user_id = current_user.id` |
| 所有接口必须鉴权 | 依赖 `get_current_user` 依赖注入（与现有 auth 路由一致） |
| 查看他人报告返回 404 | 不返回 403，避免暴露报告 ID 是否存在 |
| 删除他人报告返回 404 | 同上 |
| user_id 由后端写入 | `POST /reports` 请求体不含 `user_id`，后端从 JWT 中读取 |

```python
# 查询示例（伪代码）
def get_report(report_id: UUID, current_user: AppUser, db: Session):
    report = db.query(AnalysisReport).filter(
        AnalysisReport.id == report_id,
        AnalysisReport.user_id == current_user.id  # 权限校验
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report
```

---

## 7. 存储内容边界

**保存内容：**

| 字段 | 说明 |
|------|------|
| `report_md` | 综合报告 Markdown 全文 |
| `sections` | 四个子报告（technical / fundamental / peer_comparison / news） |
| `metadata` | `generated_at` 等元信息 |
| `warnings` | warning key 列表 |
| `agents` | 每个 Agent 的 status / message |

**不保存内容：**

| 字段 | 原因 |
|------|------|
| JWT token | 安全风险；token 有过期时间，保存无意义 |
| 用户密码 | 绝对禁止 |
| 第三方 API key | 不应落库（AkShare、Claude API key 等） |
| K线原始数据 | 体积过大，且可重新获取 |
| LLM 原始响应（非 Markdown） | 无需保存中间产物 |

---

## 8. 开发阶段划分

### Phase 1 — 核心 CRUD（✅ 已完成）

**后端：**
- [x] 创建 `analysis_reports` 表（`create_all` 自动建表，无需 migration）
- [x] 创建 `AnalysisReport` SQLAlchemy model（`Mapped[T]` + `mapped_column` 风格，`report_metadata` 规避保留名）
- [x] 实现 4 个 REST 接口（POST / GET list / GET detail / DELETE）
- [x] 权限校验（user_id 过滤，他人报告返回 404）

**前端：**
- [x] `src/api/reports.js`：封装 4 个接口调用，含字段映射（`report_md` ↔ `report`，`report_metadata` ↔ `metadata`）
- [x] `src/api/http.js`：`baseFetch` 支持 204 No Content（`return null`）
- [x] `src/views/HistoryView.vue`：报告列表页（筛选 + 分页 + 删除）
- [x] `src/views/HistoryDetailView.vue`：报告详情页（零修改复用现有组件）
- [x] `src/router/index.js`：添加 `/history` 和 `/history/:id` 路由（lazy import）
- [x] `src/views/ComprehensiveAnalysisView.vue`：分析完成后显示"保存报告"按钮（4 态状态机）
- [x] `src/components/AppHeader.vue`：顶部导航添加"历史报告"入口

**验收：** 分析完成 → 点击保存 → 进入 `/history` 列表 → 点击查看详情 → 结果与原始分析一致（浏览器验证待完成）

### Phase 2 — 体验优化

- [ ] 分析完成后自动弹出"是否保存？"提示（而非静默按钮）
- [ ] 自定义确认弹窗（替换浏览器原生 `confirm()`/`alert()`，与深色主题一致）
- [x] market / symbol 筛选功能（已在 Phase 1 实现）
- [x] 报告列表分页（已在 Phase 1 实现，limit/offset）
- [ ] Router 导航守卫（`beforeEach`，未登录时重定向到登录页）

### Phase 3 — 高级功能

- [ ] PDF / Markdown 导出
- [ ] 报告对比（两份报告并列显示）
- [ ] 收藏报告（新增 `is_starred` 字段）
- [ ] 报告分享（生成公开只读链接，需要额外权限模型）

---

## 附录：数据流图

```
用户点击"保存报告"
        │
        ▼
前端调用 POST /api/v1/reports
  body: { market, symbol, report_md, sections,
          metadata, warnings, agents }
        │
        ▼
后端 reports router
  1. 从 JWT 读取 current_user.id
  2. 创建 AnalysisReport 记录（user_id = current_user.id）
  3. INSERT INTO analysis_reports
  4. 返回 { id, created_at }
        │
        ▼
前端显示"保存成功"提示
  [查看历史] 按钮出现
        │
        ▼
用户访问 /history
  GET /api/v1/reports?limit=20
  WHERE user_id = current_user.id
  ORDER BY created_at DESC
        │
        ▼
用户点击某条报告 → /history/:id
  GET /api/v1/reports/:id
  WHERE user_id = current_user.id  ← 权限校验
  复用 AgentStatusBar / WarningPanel / MarkdownReport / SectionAccordion 展示
```
