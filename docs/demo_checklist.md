# TradingAgents — 演示检查清单

---

## 演示前检查（5 分钟，演示开始前完成）

### 后端服务

- [ ] Redis 已启动：`redis-cli ping` → `PONG`
- [ ] 后端已启动：`uvicorn app.main:app --port 8000`（或 4-worker 版）
- [ ] 后端健康检查：`curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] alembic current 为 head：`alembic current` → `c5e9f12a3b87 (head)`
- [ ] compileall 通过：`python -m compileall app/ -q` → 无输出

### 前端

- [ ] npm run build 通过：`npm run build` → `✓ 195 modules transformed`
- [ ] 前端已启动：`npm run dev` → `http://localhost:3001`（或 dist 已部署）
- [ ] 浏览器缓存已清理（Cmd+Shift+R / 硬刷新）

### 数据库与配置

- [ ] PostgreSQL 可连接（`DATABASE_URL` 正确）
- [ ] LLM API key 有效（`DEEPSEEK_API_KEY` 或对应 key）
- [ ] `ANALYSIS_RUN_REGISTRY` 当前值（memory / redis）：`___________`
- [ ] `DEFAULT_ANALYSIS_ENGINE` 当前值（custom_coordinator / langgraph）：`___________`
- [ ] 测试账号已创建（演示用）
- [ ] 测试账号已登录，token 有效（JWT 60min，注意时效）

### 演示环境

- [ ] dev mode 开关状态已确认（演示 EngineSelector 时需开启）
  - 开启方法：浏览器 Console → `localStorage.setItem('tradingagents:dev_mode','true')`; 刷新
  - 关闭方法：`localStorage.removeItem('tradingagents:dev_mode')`; 刷新
- [ ] 演示股票行情数据可拉取（CN/000001 平安银行，测试一次）
- [ ] 浏览器窗口尺寸确认（演示宽屏时 ≥1024px；演示移动端时 ≤640px）

---

## 5 分钟演示 Checklist（演示过程中逐项打勾）

### 第一步：首页（~40s）

- [ ] 展示 HomeDashboardPanel 6 个区块（近期报告 / 自选快跳 / 最近搜索 / 行业热门 / 对比入口 / 系统说明）
- [ ] 切换主题：light-holo → dark-dive → paper-lilac（说明 CSS 变量无 FOUC）
- [ ] 切换 UI 语言：zh-CN → en-US（说明 i18n 独立于报告语言）

### 第二步：股票搜索与详情（~30s）

- [ ] 搜索 "000001"，确认 StockIdentityCard 显示"平安银行"
- [ ] 进入股票详情页，指向 StockDashboardPanel（行情 + 行业 + 数据质量）
- [ ] 快速浏览 K 线图（切换 3 月 / 1 年）

### 第三步：综合分析 + SSE 进度（~90s）

- [ ] 点击"开始综合分析"，选择 `technical_only` scope
- [ ] 确认 SSE 进度条启动，`analysis_started` 事件显示
- [ ] 看到 `agent_started` × 1（technical_only 只跑 1 个 agent）
- [ ] 等待 `report_ready`，报告渲染
- [ ] 指向 `metadata.workflow_engine`（应为 `custom_coordinator`）

### 第四步：多语言报告（~20s）

- [ ] 在分析页选择 `output_language = en-US`，重新发起分析
- [ ] 报告生成后确认内容为英文（UI 保持 zh-CN）
- [ ] 说明 output_language 与 UI language 解耦

### 第五步：报告操作（~20s）

- [ ] 点击"保存报告"
- [ ] 进入报告中心，确认报告出现在列表
- [ ] 点击 FilterPanel，演示 scope / 时间范围筛选

### 第六步：双 engine 演示（~20s）

- [ ] 确认 dev mode 已开启（EngineSelector 可见）
- [ ] 切换 engine → langgraph，发起分析
- [ ] 报告生成后确认 `metadata.workflow_engine = "langgraph"`
- [ ] 说明两种 engine shape 100% 兼容，前端无需 if/else

### 第七步：自选股 + 对比（~20s）

- [ ] 进入自选股工作台，展示 4 统计卡 + 筛选
- [ ] 点击"对比"按钮进入 StockCompareView，展示迷你趋势图

---

## 常见翻车点与预防措施

| 风险 | 症状 | 预防 / 恢复 |
|------|------|------------|
| Redis 未启动 | `ANALYSIS_RUN_REGISTRY=redis` 时 HTTP 503 | 演示前 `redis-cli ping` 验证；或改用 memory 模式 |
| LLM API key 失效 | 分析卡在 `agent_started`，最终 `analysis_failed` | 演示前用 `curl` 测试一次 API key 有效性 |
| 数据源超时（AkShare/Sina）| agent 报 timeout，报告降级 | 演示前先跑一次 CN/000001 technical_only 预热缓存 |
| SSE 被代理缓冲 | 进度更新延迟，像卡顿 | 本地演示无 Nginx 缓冲；生产注意 `proxy_buffering off` |
| JWT 过期 | 所有请求 401 | JWT 有效期 60 分钟；演示前重新登录 |
| DB migration 未执行 | 列不存在的 500 错误 | `alembic current` 确认为 head |
| CORS | 前端无法请求后端 | 确认 `ALLOWED_ORIGINS` 包含前端 origin |
| Docker env 未配置 | 服务启动但功能异常 | 检查 `.env` 文件，对照 `docker-compose.yml` 注释条目 |
| dev mode 未开启 | EngineSelector 不显示 | `localStorage.setItem('tradingagents:dev_mode','true')` + 刷新 |
| output_language 未显示在报告 | 报告始终 zh-CN | 检查 Agent LLM 调用是否传入 output_language 参数 |

---

## 演示后快速重置

```bash
# 清除测试报告（如需）
curl -X DELETE http://localhost:8000/api/v1/reports/{report_id} \
  -H "Authorization: Bearer $TOKEN"

# 重置 dev mode
# 浏览器 Console: localStorage.removeItem('tradingagents:dev_mode')

# 重置主题到默认
# 浏览器 Console: document.documentElement.setAttribute('data-theme','light-holo')

# 重启后端（清除内存 registry）
# Ctrl+C → uvicorn app.main:app --reload --port 8000
```
