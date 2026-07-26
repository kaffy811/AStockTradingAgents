# TradingAgents Frontend

## 快速启动

### Mock 模式（不需要后端）

```bash
cd frontend
npm install
VITE_USE_MOCK=true npm run dev
```

打开 http://localhost:3000，无需后端即可体验完整 UI。

### API 模式（需要后端运行）

```bash
# 1. 启动后端
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8080

# 2. 启动前端
cd frontend
VITE_API_BASE_URL=http://localhost:8080 npm run dev
```

或新建 `frontend/.env.local`：
```
VITE_USE_MOCK=false
VITE_API_BASE_URL=http://localhost:8080
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VITE_USE_MOCK` | `false` | `true` 时读取 `frontend/mock/fundamentals/*.json` |
| `VITE_API_BASE_URL` | `''` | 后端 API 根 URL，空则使用相对路径 |

## 财务数据（公司 Tab）

### mock 数据更新
```bash
cd backend
python scripts/generate_frontend_mocks.py
```

### 联调注意事项

**TUSHARE_TOKEN 未配置**
后端返回 503，前端显示"数据源暂不可用"错误横幅。
在 `backend/.env` 中设置 `TUSHARE_TOKEN=your_token`。

**后端 500**
检查后端日志。常见原因：数据库连接失败、alembic migration 未执行。

**CORS 错误**
确认 `backend/app/main.py` CORS origins 包含 `http://localhost:3000`。

**模块返回 partial=true**
部分字段获取失败，数据仍可用但不完整。前端显示黄色提示条，属正常现象。

**analyst_ratings 数据有限**
Tushare 业绩预告数据不等同于机构评级，前端已注明口径说明，这是设计意图。

**industry_rank 返回 partial**
需先执行 ETL 数据同步：
```bash
cd backend
python scripts/run_fundamental_etl.py stock_basic
python scripts/run_fundamental_etl.py daily_basic --trade-date YYYYMMDD
python scripts/run_fundamental_etl.py fina_indicator --end-date YYYYMMDD
python scripts/run_fundamental_etl.py industry_rank --trade-date YYYYMMDD --end-date YYYYMMDD
```

## 联调命令示例

```bash
# 获取模块列表
curl http://localhost:8080/api/v1/modules | python -m json.tool

# 获取贵州茅台概览
curl http://localhost:8080/api/v1/stock/600519/overview | python -m json.tool

# 获取估值分位
curl http://localhost:8080/api/v1/stock/600519/modules/valuation | python -m json.tool

# 获取成长性（带参数）
curl "http://localhost:8080/api/v1/stock/600519/modules/growth?period=annual&limit=8"
```

## 数据导出

### CSV 导出
- 范围：当前分组中已加载的模块（有行数据的模块）
- 格式：UTF-8 with BOM（兼容 Excel 直接打开）
- 触发：工具栏 "↓ CSV" 按钮，或模块卡片 "↓" 按钮

### Excel (.xlsx) 导出
- **导出当前模块**：点击模块卡片的 "XLS" 按钮
- **导出当前分组**：工具栏 "↓ Excel" → "导出当前分组"（一个工作簿，每个模块一个 Sheet）
- **导出全部已加载**：工具栏 "↓ Excel" → "导出全部已加载"（仅导出已缓存模块，不触发新请求）
- **加载全部后导出**：工具栏 "↓ Excel" → "加载全部后导出"（先请求所有可用模块，再全量导出）

导出规则：
- `null`/`undefined` → 空单元格（不输出"—"字符串）
- 每个 Sheet 顶部包含元数据（更新时间、数据来源、partial/stale 状态）
- 使用 `field_labels` 作为列标题
- `目录` Sheet 列出所有导出模块及状态
- Planned 模块不包含在导出中

**故障排查：**

**stale=true（黄色提示）**
数据来自后端缓存，非最新行情。可点击模块卡片 "↻" 刷新单个模块，或工具栏 "↻" 刷新当前分组。

**partial=true（橙色提示）**
部分字段获取失败，数据不完整但仍可用。通常因 Tushare 配额不足或接口返回不完整，属正常现象，导出的 Excel 中对应字段为空单元格。

## Build

```bash
npm run build   # 生产构建
npm run dev     # 开发服务器
```

注意：ECharts 约 1MB，xlsx（SheetJS）约 800KB，生产构建后 StockDetailView chunk 约 1.2MB（gzip 400KB），属正常现象。xlsx 通过动态 import 懒加载，不影响首屏性能。
