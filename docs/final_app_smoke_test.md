# TradingAgents — 最终 App 交付测试清单

> 版本：M23 质量收口（2026-06-06）  
> 用途：发布前人工验收、面试演示前检查、移交前回归  
> 说明：本清单以人工测试步骤为主，每项给出预期结果。

---

## 一、环境启动检查

| # | 步骤 | 预期结果 |
|---|------|----------|
| E-1 | `cd backend && uv run uvicorn app.main:app --reload --port 8000` | 后端启动无报错，`http://localhost:8000/docs` 可访问 |
| E-2 | `cd frontend && npm run dev` | 前端启动无报错，`http://localhost:3001` 可访问 |
| E-3 | Redis 运行检查：`redis-cli ping` | 返回 `PONG` |
| E-4 | `uv run alembic current` | 显示当前 revision，无 ERROR |
| E-5 | `npm run build` | exit 0，188 modules，无 WARNING |
| E-6 | `python -m compileall backend/app -q` | 无输出（无 SyntaxError） |

---

## 二、登录流程

| # | 步骤 | 预期结果 |
|---|------|----------|
| L-1 | 打开 `http://localhost:3001`，未登录时访问 `/` | 重定向到 `/login` |
| L-2 | 注册新账号（email + password） | 注册成功，跳转首页 |
| L-3 | 退出登录后重新用已注册账号登录 | 登录成功，JWT 存储，重定向首页 |
| L-4 | 访问受保护路由（/watchlist, /history, /me, /compare）未登录 | 全部重定向 /login |
| L-5 | 登录后直接访问 `/stocks/CN/000001` | 正常渲染股票详情页 |

---

## 三、五大 Tab 测试

### 3.1 首页（/）

| # | 步骤 | 预期结果 |
|---|------|----------|
| H-1 | 打开首页（无历史数据） | HomeHeroPanel + HomeDashboardPanel 显示，无白屏 |
| H-2 | HomeDashboardPanel stats bar | 4 卡均显示（最近报告/自选股/最近搜索/行业热门），loading 时显示 —，无法点击时不报错 |
| H-3 | 自选快跳"填入"按钮 | StockInputPanel 填入对应 market/symbol，不自动触发分析 |
| H-4 | 行业热门某条 → 点击 | 跳转 /stocks/CN/{symbol} |
| H-5 | 最近报告某条 → 点击 | 跳转 /history/{id} |
| H-6 | 最近搜索 chip 内部点击 | StockInputPanel 填入，不自动分析 |
| H-7 | 最近搜索 chip "›" 按钮 | 跳转 /stocks/{market}/{symbol} |
| H-8 | Compare bar 无对比时 | 显示"可从股票详情或自选股批量模式加入对比"引导 |
| H-9 | Compare bar 有对比时 | 显示 chips + "进入对比"按钮，点击跳转 /compare?stocks= |
| H-10 | 开始分析（有 result 后） | HomeDashboardPanel/HomeHeroPanel/RecentSearchList 隐藏，展示分析结果 |
| H-11 | AnalysisModeSelector | 6 个维度可切换，默认 comprehensive |
| H-12 | DiscoveryPanel 推荐股票 → 填入 | StockInputPanel 填入对应 market/symbol |

### 3.2 自选股（/watchlist）

| # | 步骤 | 预期结果 |
|---|------|----------|
| W-1 | 打开 /watchlist（有自选股） | WatchlistStats + WatchlistToolbar + 卡片列表正常渲染 |
| W-2 | 打开 /watchlist（无自选股） | 显示"暂无自选股"空状态，图标和提示文案可见 |
| W-3 | 市场/行业/名称筛选 | filteredItems 实时更新，无 API 调用 |
| W-4 | 进入批量模式 | 每卡出现 checkbox，工具栏变批量模式 |
| W-5 | 批量选 2～4 只 → "对比"按钮 | 按钮可用，点击跳转 /compare?stocks= |
| W-6 | 批量选 <2 或 >4 只 → "对比"按钮 | 按钮 disabled，tooltip 说明原因 |
| W-7 | 批量选多只 → "删除"→ 确认 | 删除成功，列表更新，stats 刷新 |
| W-8 | 单卡"详情"→ | 跳转 /stocks/{market}/{symbol} |
| W-9 | 单卡"分析"→ | 跳转 /?market=&symbol= |
| W-10 | 单卡"历史"→ | 跳转 /history?market=&symbol= |
| W-11 | Note 编辑 → 保存 | 本地保存成功，页面不刷新 |

### 3.3 行业（/industry）

| # | 步骤 | 预期结果 |
|---|------|----------|
| I-1 | 打开 /industry | IndustryToolbar + IndustryOverviewPanel + IndustryHotStats + 股票卡片列表 |
| I-2 | 切换行业下拉 | 重新加载当前行业热门，filters/sortKey 重置 |
| I-3 | 涨跌筛选（上涨/下跌/缺失） | filteredItems 实时更新 |
| I-4 | 快速搜索框选股 | 跳转 /stocks/CN/{symbol} |
| I-5 | 单卡"详情"→ | 跳转 /stocks/{market}/{symbol} |
| I-6 | 单卡"分析"→ | 跳转 /?market=&symbol= |
| I-7 | 单卡"历史"→ | 跳转 /history?market=&symbol= |
| I-8 | 单卡"加自选"→ | 状态变为 added/exists/error，无白屏 |
| I-9 | 行业热门为空 | 显示"暂无行业热门数据"提示 |

### 3.4 报告中心（/history）

| # | 步骤 | 预期结果 |
|---|------|----------|
| R-1 | 打开 /history（有报告） | ReportCenterStats + ReportFilterPanel + ReportListCard 列表 |
| R-2 | 打开 /history（无报告） | 显示"暂无历史报告"空状态 |
| R-3 | 按市场/scope/auto_saved/时间筛选 | 列表即时更新 |
| R-4 | 查看报告 → | 跳转 /history/{id} |
| R-5 | 股票详情 → | 跳转 /stocks/{market}/{symbol} |
| R-6 | 重新分析 → | 跳转 /?market=&symbol=&scope= |
| R-7 | 删除报告 → 确认 | 报告消失，stats 更新 |

### 3.5 我的（/me）

| # | 步骤 | 预期结果 |
|---|------|----------|
| M-1 | 打开 /me | ProfileResearchStats + ProfileActivityPanel + ProfileSettingsPanel + DataSourceNoticePanel |
| M-2 | 最近报告某条 → 点击 | 跳转 /history/{id} |
| M-3 | 最近搜索某条 → 点击 | 跳转 /stocks/{market}/{symbol} |
| M-4 | "查看全部报告"→ | 跳转 /history |
| M-5 | 修改默认市场偏好 → 保存 | 首页默认市场更新 |
| M-6 | 修改默认分析维度 → 保存 | 首页 AnalysisModeSelector 默认值更新 |
| M-7 | 自动保存开关关闭 → 分析 | 分析完成后不自动保存报告 |
| M-8 | 退出登录 | 清除 JWT，重定向 /login |

---

## 四、二级页面测试

### 4.1 股票详情（/stocks/:market/:symbol）

| # | 步骤 | 预期结果 |
|---|------|----------|
| S-1 | 打开 /stocks/CN/000001 | StockDashboardPanel 基本信息正常，无白屏 |
| S-2 | K 线图 tab 切换 1月/3月/6月/1年/周K/月K | 图表重新渲染，MA 均线跟随 |
| S-3 | MA 均线 toggle | 对应均线显示/隐藏 |
| S-4 | TechnicalInsightCard | 均线/MACD/RSI/成交量解读，无投资判断文案 |
| S-5 | NewsTimelinePanel | 新闻列表渲染，分类筛选 chips 有效 |
| S-6 | "加自选"→ 状态变化 | 已加入后按钮变为"已加自选" |
| S-7 | "加入对比"→ | compareStatus 变为 in_list/added，2.5s 后恢复真实状态 |
| S-8 | "去对比页"→ | 跳转 /compare?stocks= 含当前股票 |
| S-9 | 生成分析 → | 跳转 /?market=&symbol= |
| S-10 | 查看历史报告 → | 跳转 /history?market=&symbol= |
| S-11 | 同行业热门股某条 → | 跳转 /stocks/CN/{symbol} |

### 4.2 股票对比（/compare）

| # | 步骤 | 预期结果 |
|---|------|----------|
| C-1 | 打开 /compare（空） | 显示"请在上方搜索并添加 2～4 只股票"空状态 |
| C-2 | 搜索添加 1 只股票 | 显示"请再添加至少 1 只股票以查看完整对比"提示 |
| C-3 | 添加 2～4 只股票 | StockCompareSummary + StockCompareTable 显示 |
| C-4 | StockCompareTable 趋势列 | 每只股票的 StockMiniTrend 渲染（loading → SVG 或 error fallback） |
| C-5 | 某只股票 profile 失败 | 显示"资料暂不可用"而非白屏，其他股票正常 |
| C-6 | 移除某只股票 | URL query 同步更新，profiles 对应移除 |
| C-7 | "清空全部" | URL query 清空，compareStorage 清空 |
| C-8 | 刷新页面（有 URL query） | 重新加载，URL 优先 |
| C-9 | 详情 → | 跳转 /stocks/{market}/{symbol} |
| C-10 | 分析 → | 跳转 /?market=&symbol= |
| C-11 | 历史 → | 跳转 /history?market=&symbol= |

### 4.3 报告详情（/history/:id）

| # | 步骤 | 预期结果 |
|---|------|----------|
| D-1 | 打开已有报告详情 | ReportDetailHeader + ReportMetaSummary + 完整 Markdown 报告渲染 |
| D-2 | ReportMetaSummary | 分析维度/Agent 状态/warnings 正常显示 |
| D-3 | "重新分析"→ | 跳转 /?market=&symbol=&scope= |
| D-4 | "Markdown 下载"→ | 下载 .md 文件 |
| D-5 | "打印/PDF"→ | 跳转 /print/report |

### 4.4 打印页（/print/report）

| # | 步骤 | 预期结果 |
|---|------|----------|
| P-1 | 从报告详情点击"打印"→ | 打印页渲染报告内容，无导航栏 |
| P-2 | 打印页标题 | 包含股票名称 |
| P-3 | 浏览器打印预览 | 内容完整，无截断 |

---

## 五、核心链路测试

| # | 链路 | 步骤 | 预期结果 |
|---|------|------|----------|
| F-1 | 搜索→分析→保存→报告详情 | 首页搜索 CN/000001 → 综合分析 → 分析完成 → 点击保存 → 跳转 /history/{id} | 完整链路无报错，报告可查看 |
| F-2 | 股票详情→对比→对比页 | /stocks/CN/000001 → 加入对比 → 去对比页 → /compare?stocks=CN:000001 | compareStatus 正确，对比页展示数据 |
| F-3 | 自选股批量对比 | /watchlist → 批量模式 → 选 2 只 → 对比 → /compare?stocks= | 对比页正确加载 2 只股票 |
| F-4 | 行业热门→股票详情 | /industry → 某行业 → 某卡片"详情" → /stocks/CN/{symbol} | 股票详情页正常加载 |
| F-5 | 报告中心→重新分析 | /history → 某报告"重新分析" → /?market=&symbol=&scope= | 首页填入对应股票+scope |
| F-6 | 偏好设置→首页生效 | /me → 修改默认市场为 HK → 保存 → 返回首页 | 首页市场下拉默认为 HK |
| F-7 | 比较链路 storage/URL 双向同步 | 详情页加入对比 → 直接打开 /compare（无 URL query） → 显示 storage 内股票 | storage fallback 正常 |
| F-8 | LangGraph 灰度（开发者） | localStorage 设置 tradingagents:dev_mode=true → 首页出现 EngineSelector | 切换 langgraph 后分析正常完成，结果结构兼容 |

---

## 六、移动端测试

### 测试视口

| 视口 | 说明 |
|------|------|
| 375px | iPhone SE / 最小标准视口 |
| 390px | iPhone 14 |
| 430px | iPhone 14 Pro Max |

### 测试清单

| # | 页面 | 检查项 | 预期 |
|---|------|--------|------|
| M-1 | / | body 无横向滚动，HomeDashboardPanel stats 2列，grid 1列 | ✓ |
| M-2 | / | BottomTabBar 不遮挡内容（padding-bottom: calc(72px + safe-area)）| ✓ |
| M-3 | /watchlist | WatchlistStockCard 不溢出，批量 checkbox 可点 | ✓ |
| M-4 | /industry | IndustryStockCard action grid 2×2，hot score/涨跌幅不换行 | ✓ |
| M-5 | /history | ReportListCard 不溢出，badges 可换行 | ✓ |
| M-6 | /me | ProfileView 各 section 单列，设置项不溢出 | ✓ |
| M-7 | /stocks/CN/000001 | K 线图不溢出，tab 可横滑，TechnicalInsightCard 卡片化 | ✓ |
| M-8 | /compare?stocks=CN:000001,CN:600519 | StockCompareTable 切换为移动卡片视图，趋势行可见 | ✓ |
| M-9 | /history/:id | Markdown 报告正常换行，不横向溢出 | ✓ |
| M-10 | AppHeader | 导航链接隐藏（≤640px），只保留 Logo | ✓ |
| M-11 | BottomTabBar | 5个 Tab 均匀分布，active 状态正确 | ✓ |
| M-12 | 长股票名 | 所有场景 ellipsis 截断，不破坏布局 | ✓ |
| M-13 | chips 换行 | hero-chips / filter chips / compare chips 自动换行 | ✓ |

---

## 七、文案安全检查

### 禁止词扫描

在 `/frontend/src` 目录下全局 Grep 以下词（.vue 文件）：

| 禁止词 | 说明 |
|--------|------|
| 买入 | 投资建议 |
| 卖出 | 投资建议 |
| 强烈建议 | 投资建议 |
| 必涨 | 确定性判断 |
| 必跌 | 确定性判断 |
| 确定性机会 | 确定性判断 |
| 确定性风险 | 确定性判断 |
| 明确利好 | 确定性判断 |
| 明确利空 | 确定性判断 |
| 推荐股票 | 投资建议 |
| 收益保证 | 收益承诺 |
| 稳赚 | 收益承诺 |
| 预测收益 | 收益承诺 |

**预期：0 matches（M23 审计通过）**

### 允许的表达

- 研究线索、数据观察、结构化分析
- 仅供研究参考、不构成投资建议
- 需结合更多信息判断
- 数据覆盖有限

---

## 八、已知限制

| 限制 | 影响 | 处理方式 |
|------|------|----------|
| 港股行业覆盖 | /industry 仅展示 A 股申万行业 | 界面已提示"当前市场暂不支持行业热门股" |
| 港股基本面字段 | PE/PB 等可能缺失 | DataQualitySummary 说明，StockDashboardPanel 显示 — |
| 新闻时效 72h | 新股或冷门股可能无新闻 | NewsTimelinePanel 空状态提示 |
| 行情非实时 | Redis TTL 缓存 | 界面无实时推送，行情有缓存延迟 |
| industry refresh duplicate | 食品饮料/银行行业偶发 UniqueViolation | 28/30 行业正常，重试一般可恢复 |
| StockMiniTrend 数据不足 | 少于 3 个数据点 | 显示"数据不足"提示，不崩溃 |
| LangGraph 灰度 | 仅开发者模式可用 | 默认 custom_coordinator，生产无影响 |

---

## 九、快速验收 Checklist（5 分钟）

- [ ] 登录正常
- [ ] 首页仪表盘展示（有数据时）
- [ ] 首页分析 CN/000001 → 有报告
- [ ] 跳转股票详情页 → K 线图正常
- [ ] 加入对比 → /compare 正常
- [ ] /watchlist 批量对比入口可用
- [ ] /industry 行业切换正常
- [ ] /history 报告列表正常
- [ ] /me 设置保存正常
- [ ] 移动端 375px 无横向滚动
- [ ] 文案无禁止词
- [ ] npm run build 通过
- [ ] compileall 通过

---

## 十、M25-a SSE 实时进度验收（2026-06-06）

### 环境检查更新

| # | 步骤 | 预期结果（M25-a 更新） |
|---|------|----------------------|
| E-5 | `npm run build` | exit 0，**183 modules**，无 WARNING |

### SSE 路径验证

| # | 步骤 | 预期结果 |
|---|------|----------|
| SSE-1 | 首页输入 CN/000001，点击分析（默认 custom_coordinator） | AnalysisProgressPanel 切换为 realtime 模式，显示 5 个 Agent 格 |
| SSE-2 | 等待分析执行 | 各 Agent 状态从 pending → running → success/failed，进度条实时更新 |
| SSE-3 | 点击"停止等待"（取消按钮） | 分析停止，errorMsg "本次分析已取消" |
| SSE-4 | dev mode 下打开 SSE 事件日志（AnalysisEventTimeline） | 可见逐条事件（analysis_started / agent_started / … / report_ready） |
| SSE-5 | 选择 LangGraph engine 执行分析 | 自动 fallback 阻塞 API，ProgressPanel 显示 time 模式，无报错 |
| SSE-6 | 分析完成后报告正常渲染 | result 展示与 M24 版本完全一致 |
| SSE-7 | 旧 POST /analysis/comprehensive-v2 仍可用（curl 验证） | 200，行为不变 |

### API curl 验证（补充 T-13/T-14）

```bash
# T-13: 创建 SSE 分析运行
curl -s -X POST "http://localhost:8000/api/v1/analysis/runs" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"market":"CN","symbol":"000001","analysis_scope":"technical_only"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('run_id:', d.get('run_id','?')); print('status:', d.get('status','?'))"
# 预期: run_id: <uuid>, status: queued

# T-14: 订阅 SSE 事件流（需替换 RUN_ID）
# curl -sN -H "Authorization: Bearer <TOKEN>" \
#   "http://localhost:8000/api/v1/analysis/runs/<RUN_ID>/events"
# 预期: 逐行输出 event:/data: 直至 report_ready
```

---

## M25-c：开发者模式 LangGraph SSE 验证路径

> 前提：本地 dev 构建或 `localStorage.setItem('tradingagents:dev_mode','true')` 已设置。

### 操作路径

1. 打开首页，确认 EngineSelector 可见
2. 将 Engine 切换为 **LangGraph**
3. 输入股票代码（如 CN/000001），选择 `technical_only` 或 `technical_fundamental`
4. 点击"开始分析"

### 验证项

| 项目 | 预期 |
|------|------|
| ProgressPanel 模式 | realtime（显示 5 个 Agent 状态格） |
| 不在分析范围的 Agent | 显示为 "—"（skipped） |
| technical agent | 先 running → success |
| synthesis 节点 | running → success |
| EventTimeline（dev mode） | 可见 analysis_started、identity_resolved、agent_started/completed、synthesis_started/completed、report_ready 等事件 |
| EventTimeline event_id | 每条事件显示 #N，单调递增 |
| EventTimeline elapsed_ms | 每条显示 +Nms |
| EventTimeline 工作引擎 | analysis_started message 含 "[LangGraph]" |
| 报告渲染 | 正常，与 custom_coordinator 格式一致 |
| metadata.workflow_engine | langgraph |
| 取消分析 | 点击"停止等待"→ 停止 SSE，不触发 fallback，显示"已停止等待"消息 |
| SSE 断线恢复 | 短暂断网后重连，after_event_id replay 正常 |

### 回归验证（切回 custom_coordinator）

1. EngineSelector 切回 custom_coordinator
2. 执行分析
3. ProgressPanel 正常显示 realtime 模式
4. 结果与之前一致

---

## Phase M28-a + M29 — 综合分析页体验增强（2026-06-06）

### M28-a 修复验证

| 测试项 | 预期行为 |
|--------|---------|
| 首页仪表盘"行业机会"点击 | 跳转 `/industries`，不黑屏 |
| 生成按钮文案 | 显示"生成报告" |
| 卡片标题 | 显示"生成分析报告" |
| AnalysisResultLayout sticky bar | 左侧显示"+ 新建分析"按钮 |
| 点击"+ 新建分析" | 清空报告区，滚动回顶 |

### M29 最近搜索

| 测试项 | 预期行为 |
|--------|---------|
| 首次进入（无搜索历史） | RecentSearchList 显示"暂无最近搜索，输入股票代码或名称开始研究。" |
| 搜索 1 次 | RecentSearchList 显示 1 条，无次数角标 |
| 搜索同一股票 2 次 | chip 显示"2次"角标 |
| 搜索同一股票 5 次 | "5次"角标变为 accent 色 |
| 搜索历史 > 5 条 | 显示前 5 条 + "展开更多（共 N 条）" |
| 点击"展开更多" | 展开显示最多 10 条，按钮变为"收起" |
| 点击 chip | 填入输入框，不自动分析 |
| 点击"清空" | 清空并隐藏列表（保留 card 空状态） |

### M29 高频搜索

| 测试项 | 预期行为 |
|--------|---------|
| 无搜索历史时 DiscoveryPanel "快速开始" | 标题"常见标的"，显示 5 个默认 picks |
| 有搜索历史时 | 标题"常搜标的"，显示 top 5 by count |
| 搜索某股票后切换到 DiscoveryPanel | 实时刷新（recent-searches-updated 事件） |

### M29 首次引导

| 测试项 | 预期行为 |
|--------|---------|
| 首次进入（清除 localStorage） | StockInputPanel 显示蓝紫 glow + "输入股票代码或名称，选择分析范围后即可生成报告。" |
| 8 秒后 | 引导自动消失 |
| 点击输入框 | 引导立即消失 |
| 点击"生成报告" | 引导立即消失 |
| 刷新页面 | 不再显示引导 |
| 清除 `tradingagents:first_analysis_hint_seen` 后刷新 | 重新显示引导 |

### M29 报告摘要

| scope | 摘要节标题 | 预期 |
|-------|---------|------|
| technical_only | ## 一、摘要 | ✅ 提取到技术面维度描述 |
| fundamental_only | ## 一、摘要 | ✅ 提取到基本面维度描述 |
| peer_only | ## 一、摘要 | ✅ 提取到同行对比维度描述 |
| news_only | ## 一、摘要 | ✅ 提取到新闻面维度描述 |
| technical_fundamental | ## 一、摘要 | ✅ 提取到双维度描述 |
| comprehensive | ## 一、核心摘要 | ✅ extractSummary 正常提取 |
| fallback 报告 | ## 一、核心摘要 | ✅ extractSummary 正常提取 |
| 旧报告（legacy：## 二、核心结论） | 向后兼容 | ✅ extractSummary 正常 fallback |

---

## Phase M30 — 行业研究页重构（2026-06-06）

### M30-1 行业页首屏结构

| 测试项 | 预期行为 |
|--------|---------|
| `/industries` 打开 | 正常加载，无黑屏 |
| 首屏顶部 | 显示双卡：行业热度全览（左）+ 行业热门板块（右） |
| 桌面端 > 640px | 双卡并排（两列） |
| 移动端 ≤ 640px | 双卡单列 |
| 统计栏位置 | 在双卡下方 |
| 快速跳转位置 | 在统计栏下方（不在顶部） |

### M30-2 行业热度全览

| 测试项 | 预期行为 |
|--------|---------|
| loading 状态 | 显示 12 个 skeleton tile（pulse 动画） |
| 正常加载后 | 显示约 30 个行业 tile，全部 muted 样式（listIndustries 无 hot_score） |
| selected tile | 高亮（accent border + 蓝底） |
| 点击 tile | selectedCode 更新，下方股票列表刷新 |
| IndustryToolbar 同步 | toolbar select 与 tile 联动 |

### M30-3 行业热门板块

| 测试项 | 预期行为 |
|--------|---------|
| 正常状态（无 hot_score） | 显示 EmptyState "当前行业热度数据暂不可用" |
| 若 API 返回 hot_score | 显示按 hot_score 排序的榜单（金银铜） |
| "展示全部"按钮 | 仅在 hasScores 且条数 > limit 时显示 |
| 展开/收起 | 最多 20 条 |
| 点击行业行 | selectedCode 更新，股票列表刷新 |

### M30-4 热门股 20 支

| 测试项 | 预期行为 |
|--------|---------|
| IndustryHotView 股票列表 | 最多 20 支（HOT_LIMIT=20，后端 le=50 允许） |
| DiscoveryPanel 行业热门 | 仍只请求 5 支（调用时显式传 limit=5） |
| StockDetailView 动态同行 | 不受影响（dynamic-peers 端点独立） |

### M30-5 快速跳转股票详情

| 测试项 | 预期行为 |
|--------|---------|
| 搜索 CN/000001 | 跳转 `/stocks/CN/000001` |
| 输入纯代码 600519 后点按钮 | 跳转 `/stocks/CN/600519` |
| 不跳综合分析页 | ✅（路由为 /stocks/...） |

### M30-6 文案安全

| 测试项 | 预期行为 |
|--------|---------|
| DiscoveryPanel tab | 显示"行业热度"（非"行业机会"） |
| IndustryHeatOverviewCard | 无投资建议词 |
| IndustryHotBlocksCard | "热度排名仅供研究线索参考，不代表投资价值判断" |

### M30-7 回归

| 页面 | 状态 |
|------|------|
| `/` 综合分析页 | ✅ 不受影响 |
| `/stocks/CN/000001` | ✅ 不受影响 |
| `/watchlist` | ✅ 不受影响 |
| `/history` | ✅ 不受影响 |
| `/me` | ✅ 不受影响 |
| `/compare` | ✅ 不受影响 |

---

## 十、主题切换测试（M32）

| # | 步骤 | 预期结果 |
|---|------|----------|
| T-1 | /me → 偏好设置 → 界面主题，点击"极夜深潜" | 页面背景立即变深色 #0b1120 附近，卡片层级清晰 |
| T-2 | 刷新页面 | 仍保留"极夜深潜"，无闪白 |
| T-3 | 点击"流光幻岛" | 背景变浅色 #f0f4fa，卡片白色，文字深色 |
| T-4 | 点击"晨暮丁香" | 背景暖米白 #f6f2ec，卡片奶白，文字深暖灰 |
| T-5 | 切换主题后查看 K 线图 | 图表背景、格线、蜡烛颜色随主题更新，不白屏 |
| T-6 | 切换主题后查看 /industries 行业页 | 行业热格色阶更新，热块排行涨跌色正常 |
| T-7 | 切换主题后查看 /watchlist 自选股趋势线 | StockMiniTrend 红绿颜色随主题更新 |

## 十一、主题深度适配验证（M33-a）

| # | 步骤 | 预期结果 |
|---|------|----------|
| C-1 | 切换到"流光幻岛"，打开自选股列表，查看删除按钮悬停色 | 删除按钮 hover 背景为浅红 --status-up-bg，非硬编码蓝色 |
| C-2 | 切换到"晨暮丁香"，打开报告历史，查看状态角标（成功/失败/超时） | 角标底色分别为 --status-down-bg / --status-up-bg / --status-warn-bg |
| C-3 | 切换到"极夜深潜"，打开技术面图表，查看 MA5/MA10/MA20/MA60 切换按钮 on 状态 | 按钮底色和文字色与各 MA 线颜色匹配，使用 CSS var |
| C-4 | 切换到"流光幻岛"，打开股票详情 /stocks/CN/000001，查看研究面板中指标分析卡片 | 卡片趋势分类（正面/中性/警告）底色随主题变化，非蓝色系 |
| C-5 | 任意主题下查看新闻时间线 | 事件类型点标（市场/产品/风险）使用语义色，非硬编码 rgba |

---

## 十二、报告输出语言 output_language E2E 验证（M36 / M36.1）

> 前提：登录后在 /me → 个人设置 → **报告输出语言** 中选择目标语言后，返回首页再执行分析。

### 环境检查更新

| # | 步骤 | 预期结果（M36 更新） |
|---|------|---------------------|
| E-5 | `npm run build` | exit 0，**195 modules**，无 WARNING |
| E-4 | `uv run alembic current` | 显示 `c5e9f12a3b87 (head)` |

### 设置页验证

| # | 步骤 | 预期结果 |
|---|------|----------|
| OL-1 | 打开 /me → ProfileSettingsPanel | 可见"报告输出语言"selector，与"界面语言"独立，当前默认"简体中文" |
| OL-2 | 将报告语言切换为"English (US)" | selector 显示 English (US)，localStorage tradingagents:settings:v1 中 report_language = "en-US" |
| OL-3 | 刷新页面 | selector 仍显示 English (US)，设置持久化 |
| OL-4 | 将界面语言切换为任意语言 | 报告语言 selector 不受影响，两者完全独立 |

### 请求验证

| # | 步骤 | 预期结果 |
|---|------|----------|
| OL-5 | 设置 report_language=en-US，打开 DevTools Network，触发 SSE 分析 | POST /api/v1/analysis/runs body 包含 `"output_language": "en-US"` |
| OL-6 | 同上，触发 legacy fallback 分析（关闭 Redis 或在 payload 中不传 engine） | POST /api/v1/analysis/comprehensive-v2 body 包含 `"output_language": "en-US"` |

### 真实分析测试矩阵

| 测试 | market | symbol | scope | output_language | engine | 预期报告内容 |
|------|--------|--------|-------|----------------|--------|-------------|
| T1 | CN | 000001 | technical_only | zh-CN | custom_coordinator | 中文标题 + 中文正文，metadata.output_language = zh-CN |
| T2 | CN | 000001 | technical_fundamental | en-US | custom_coordinator | 英文章节标题、英文摘要、英文风险提示；badge EN 显示于 HistoryView |
| T3 | HK | 00700 | news_only | zh-TW | custom_coordinator | wrapper 繁體中文（标题/摘要/风险提示），Agent 原文视数据源，metadata.output_language = zh-TW |
| T4 | CN | 000001 | technical_only | en-US | langgraph（开发者模式） | metadata.workflow_engine=langgraph，metadata.output_language=en-US，HistoryView badge EN |
| T5a | CN | 000001 | news_only | ja-JP | custom_coordinator | 日文 wrapper，metadata.output_language=ja-JP，badge JA |
| T5b | CN | 000001 | news_only | ko-KR | custom_coordinator | 韩文 wrapper，metadata.output_language=ko-KR，badge KO |
| T5c | CN | 000001 | news_only | es-ES | custom_coordinator | 西班牙文 wrapper，metadata.output_language=es-ES，badge ES |

### metadata 完整性验证

| # | 步骤 | 预期结果 |
|---|------|----------|
| OL-7 | T2 分析完成后，在 DevTools Console 查看 result 对象 | `result.output_language === "en-US"` 且 `result.metadata.output_language === "en-US"` |
| OL-8 | 分析完成后自动保存，查看 /history 列表 | 报告卡片右上角显示 `EN` badge（黄色警示色） |
| OL-9 | 点击进入报告详情 /history/:id | ReportDetailHeader 右侧显示 `EN` badge，与列表一致 |
| OL-10 | 访问 /stocks/CN/000001 → 历史报告栏 | 该报告条目显示 `EN` badge（如有 output_language 字段） |

### DB 验证（开发环境）

```sql
-- 预期：新报告 output_language = 'en-US'，旧报告 = 'zh-CN'，无 null
SELECT id, market, symbol, analysis_scope, output_language, auto_saved, created_at
FROM analysis_reports
ORDER BY created_at DESC
LIMIT 10;
```

### badge 渲染验证

| 语言代码 | ReportListCard badge | ReportDetailHeader badge |
|---------|---------------------|--------------------------|
| zh-CN | 不显示（默认） | 不显示 |
| en-US | `EN` | `EN` |
| zh-TW | `繁中` | `繁中` |
| ja-JP | `JA` | `JA` |
| ko-KR | `KO` | `KO` |
| es-ES | `ES` | `ES` |
| 未知 code | 原 code（fallback） | 原 code（fallback） |

> 均不得出现 `undefined`、`null`、`[object Object]`。

### single-agent 报告语言完整度说明

| scope | wrapper（标题/摘要/风险提示） | Agent 主体内容 |
|-------|---------------------------|---------------|
| technical_only | ✅ 目标语言（_SINGLE_AGENT_STRINGS） | ⚠️ 仍为 Agent 原始输出（通常中文）|
| fundamental_only | ✅ 目标语言 | ⚠️ 仍为 Agent 原始输出 |
| peer_only | ✅ 目标语言 | ⚠️ 仍为 Agent 原始输出 |
| news_only | ✅ 目标语言 | ⚠️ 仍为 Agent 原始输出 |
| technical_fundamental | ✅ LLM 以目标语言生成（synthesis） | ✅ 完全受控 |
| comprehensive | ✅ LLM 以目标语言生成（synthesis） | ✅ 完全受控 |

> **已知限制（M36）**：single-agent 报告 wrapper 已完全本地化；Agent 原始内容语言由各 Agent 自身 prompt 决定，M36 未修改 Agent prompt，主体仍输出中文。此为已知设计边界，不影响 synthesis 类报告的目标语言输出，将在 M37 通过 Agent-level prompt 注入改善。

### fallback 报告语言验证

| # | 场景 | 预期结果 |
|---|------|----------|
| OL-11 | synthesis LLM 调用失败（网络断开或 mock 异常） | fallback 报告标题、数据来源说明、风险提示以 output_language 目标语言输出（_FALLBACK_STRINGS） |
| OL-12 | 旧版报告（无 output_language 字段，DB NULL） | 前端 fallback `'zh-CN'`，badge 不显示，不报错 |

### 回归检查

| # | 步骤 | 预期结果 |
|---|------|----------|
| OL-13 | output_language=zh-CN 时分析一次 | 报告完全中文，metadata.output_language=zh-CN，无 badge 显示 |
| OL-14 | 切换 UI 语言（界面语言）为 en-US | 界面文案变英文，但 report_language 设置不变，与 UI 语言完全解耦 |
| OL-15 | 三主题切换 + output_language=en-US 分析 | 主题正常，报告英文，两者互不干扰 |
| OL-16 | analysis_scope=comprehensive + output_language=ko-KR | 综合报告韩文，metadata 正确，无 500 |

---

## 十三、Agent-level output_language 验证（M37）

> 前提：登录后在 /me → 报告输出语言中选择目标语言（如 English (US)），返回首页执行分析。

### 已知保留原文规则

以下内容在任何语言下均允许保留原文：
- 股票名称、股票代码（如 000001、00700）
- 新闻标题、新闻来源
- 财务指标缩写：PE、PB、ROE、MACD、RSI、MA5、MA10、MA20、MA60

### M37 测试矩阵

| 测试 | scope | output_language | 预期 Agent 主体 |
|------|-------|----------------|----------------|
| M37-1 | technical_only | en-US | 章节标题英文（如 "Price Overview", "MA & Trend"），解释英文，风险提示英文，MA/RSI 保留原文 |
| M37-2 | fundamental_only | en-US | 盈利能力/成长能力章节标题英文，分析解释英文，PE/PB/ROE 保留原文 |
| M37-3 | peer_only | en-US | 样本说明英文，字段解释英文，财务数值英文描述 |
| M37-4 | news_only | es-ES | 分析解读西班牙语，新闻标题可保留原文（中文或英文） |
| M37-5 | technical_fundamental | zh-TW | 章节标题繁中，解释繁中，技术指标保留缩写 |
| M37-6 | comprehensive | ja-JP | 四个 Agent 主体尽量日文，synthesis 日文 |
| M37-7 | technical_only | zh-CN | 完全中文，无语言指令文本泄漏 |

### backward compat 验证

| # | 测试 | 预期 |
|---|------|------|
| BC-1 | output_language 不传（旧代码路径） | 行为与 zh-CN 完全一致，无额外指令 token |
| BC-2 | output_language=zh-CN 明确传入 | 报告完全中文，无任何语言指令块出现在报告中 |
| BC-3 | 三主题切换后分析 | 主题样式正常，报告语言不受主题影响 |

### language_utils 验证（开发环境）

```python
from app.agents.language_utils import build_output_language_instruction, normalize_output_language

# zh-CN → 空字符串（零 token）
assert build_output_language_instruction("zh-CN") == ""
# en-US → 含【输出语言要求】块
assert "English" in build_output_language_instruction("en-US")
# 无效语言 fallback zh-CN
assert build_output_language_instruction("xx-XX") == ""
```

### 文案安全

M37 新增语言指令中含以下保护措辞：
- 末尾：`本报告仅供研究参考，不构成投资建议`
- 允许保留原文说明不含投资建议词
- 所有 Agent system prompt 中的禁止词列表保持不变

禁止词扫描（新增语言指令部分）：

| 禁止词 | 状态 |
|--------|------|
| 买入/卖出/强烈建议/必涨/必跌 | ✅ 不存在 |
| 确定性机会/确定性风险 | ✅ 不存在 |
| 明确利好/明确利空 | ✅ 不存在 |

---

## Redis Registry 模式烟雾测试（M40-c）

### 启动 Redis 模式服务

```bash
ANALYSIS_RUN_REGISTRY=redis uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 烟雾测试项

| 测试 | 操作 | 期望 |
|------|------|------|
| 健康检查 | GET /api/v1/health | {"status":"ok"} |
| 创建分析运行 | POST /analysis/runs (technical_only) | 201 Created，run_id |
| custom_coordinator SSE | GET /analysis/runs/{id}/events | analysis_started → report_ready + stream-end |
| LangGraph SSE | engine=langgraph，接 SSE | 同上，中间可能有 heartbeat |
| after_event_id replay | 用历史 event_id 重连 SSE | 仅返回 id > N 的事件 |
| cancel | POST /analysis/runs/{id}/cancel | SSE 返回 cancelled 事件 |
| Redis 不可用 | 停 Redis 后创建 run | HTTP 503 |

### 不推荐切换到 Redis 默认的当前理由

默认保留内存模式，因为：
1. 单机单 worker 部署时内存模式零依赖、启动更快
2. Redis 模式需要额外配置 REDIS_URL
3. 开发环境调试更方便（内存模式可直接读 `_runs` dict）

多 worker 生产部署应设置 `ANALYSIS_RUN_REGISTRY=redis`。
