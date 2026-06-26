# Frontend Engineering Smoke Test

**测试日期：** 2026-05-26（浏览器 smoke test 完成）  
**文档更新：** 2026-05-30（Phase P1-a / P1-a.1 / P1-b 专项测试章节新增）  
**版本：** Vue 3 + Vite 工程化迁移（index.legacy.html → src/ 组件化结构）  
**目标：** 验证工程化迁移后前端功能是否与 index.legacy.html 单文件 MVP 完全一致  
**测试标的：** CN/600519（贵州茅台）、HK/700（腾讯控股）  
**Network 验证：** POST /analysis/comprehensive → 200 ✅ | POST /reports/ → 201 ✅ | GET /reports/ → 200 ✅ | GET /reports/{id} → 200 ✅ | DELETE /reports/{id} → 204 ✅  
**Console 验证：** 全流程无红色 JS error ✅

## 当前项目阶段状态

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 前端工程化 | Vue 3 + Vite 组件化迁移，Pinia auth，vue-router 4 | ✅ 已完成 |
| Phase 1 后端接入 | 报告历史 CRUD（analysis_reports 表，4 个 REST 接口） | ✅ 已完成 |
| Phase 1 前端报告历史 | 保存 / 列表 / 详情 / 删除；AppHeader 导航；HistoryView / HistoryDetailView | ✅ 已完成 |
| Phase 2A Router Guard + ConfirmDialog | beforeEach 路由守卫；自定义 ConfirmDialog 替换 confirm()/alert() | ✅ 已完成 |
| Phase 2B Markdown 下载 | exportMarkdown.js；综合分析页 + 历史详情页「下载 .md」按钮 | ✅ 已完成 |
| Phase 2D Loading / Timeout / Cancel UX | AbortController + 阶段性等待提示 + 取消按钮 + onUnmounted 清理 | ✅ 已完成 |
| Phase W1 Watchlist 自选股 | watchlist_items 表、4 个 CRUD 接口、WatchlistView、query 联动综合分析/历史报告 | ✅ 已完成 |
| Phase W2 Watchlist 最近报告联动 | WatchlistLatestReport schema、ROW_NUMBER 两查询、卡片摘要显示 + 条件按钮 | ✅ 已完成（代码审查 + schema 验证 + 逻辑分析） |
| Phase W3 Watchlist Note 内联编辑 | `body.note or None` 清空修复、inline textarea、Enter/blur/Esc、防重入、本地更新 | ✅ 已完成（代码审查 + schema 验证 6/6 + build 通过） |
| Phase P1-a 技术面图表可视化 | lightweight-charts v4、TechnicalChartPanel、getKline API、keep-alive resize、chart.remove | ✅ 代码审查 + build 通过（⬜ 浏览器验证待执行） |
| Phase P1-a.1 历史详情页图表 + Header 修复 | HistoryDetailView 复用 TechnicalChartPanel；AppHeader displayName fallback | ✅ 代码审查 + build 通过（⬜ 浏览器验证待执行） |
| Phase P1-b 行业热门股前端展示 | IndustryHotStocksPanel；industries.js；两视图接入；dynamic_hot/manual_map/unsupported 三态 | ✅ 代码审查 + build 通过 + API 验证 8/8（⬜ 浏览器验证待执行） |
| Phase P1-c 信息架构优化 | AnalysisResultLayout；sticky anchor bar；#actions slot；两视图统一复用 | ✅ 代码审查 + build 通过（⬜ 浏览器验证待执行） |
| Phase P2 移动端响应式 | CSS-only @media 480px/540px 修复；双断点惯例注释；build exit 0；编译产物验证 ✅ | ✅ 代码审查 + build + CSS 编译验证通过（⬜ DevTools 设备仿真待执行） |
| Phase P3 行业热门股独立页面 | IndustryHotView；listIndustries API；/industries 路由 + auth guard；AppHeader 第 4 链接；桌面 table + 移动 cards | ✅ 代码审查 + build 通过（⬜ 浏览器验证待执行） |
| Phase P4-a 股票搜索 / 代码联想 | `GET /stocks/search`；StockSearchBox 组件（debounce/键盘/点击外部）；接入 StockInputPanel + WatchlistView；HK 禁搜；build exit 0；B-1~B-8 curl 验证通过；Enter 键回归修复（stopPropagation + 父组件 @keydown.enter 补绑） | ✅ 后端 curl 8/8 ✅ + 编译产物验证 12/12 ✅ + 浏览器验证 15/15 ✅（Playwright headless Chromium） |
| Phase P4-b HistoryView 搜索联想 | StockSearchBox 接入 HistoryView filter bar；`:market` 默认 CN；route.query 初始化；HK 禁搜；Enter 触发 loadReports；零后端改动 | ✅ build exit 0 ✅ + 浏览器验证 10/10 ✅（Playwright headless Chromium） |
| Phase M30 行业研究页重构 | IndustryHeatOverviewCard（30格热度全览）；IndustryHotBlocksCard（热门板块）；双卡首屏布局；快速跳转下移；187 modules | ✅ build exit 0 ✅（⬜ 浏览器验证待执行） |
| Phase M31 行业热度聚合 | `IndustryInfoResponse` hot_score 扩展；`get_industry_hot_summary()` GROUP BY；`GET /industries` 合并热度；前端组件无改动；187 modules | ✅ build exit 0 ✅ + py_compile PASS（⬜ 浏览器验证待执行） |
| Phase M32 三主题系统 | theme.js/variables.css 三套 html[data-theme]/settings theme字段/main.js applyTheme/App.vue 监听/ProfileSettingsPanel segmented control/TechnicalChartPanel buildColors+refreshChartColors/StockMiniTrend CSS vars；188 modules | ✅ build exit 0 ✅（⬜ 浏览器验证待执行） |
| Phase M33-a 全站硬编码颜色清理 | Python bulk替换：215处rgba→CSS var（--status-up/down/warn/info-bg/ring / --surface-hover / --accent-glow / --border-glow）覆盖34个Vue文件；零residual；188 modules；py_compile PASS | ✅ build exit 0 ✅ + zero residual grep ✅ |

---

## 1. 安装与启动

```bash
cd frontend
npm install
cp -n .env.example .env
npm run dev
```

检查项：

| # | 检查项 | 期望 | 状态 |
|---|--------|------|------|
| 1 | `npm install` 成功 | exit 0，无 peer dependency error | ✅ 已验证（37 packages，exit 0） |
| 2 | `npm run dev` 成功 | Vite 启动，无编译报错 | ✅ 已验证（port 3000，HTTP 200） |
| 3 | Vite 监听 3000 | `Local: http://localhost:3000/` 出现在终端 | ✅ 已验证 |
| 4 | 端口占用时自动切换 | Vite 自动尝试 3001、3002… | ⬜ 未专项验证 |
| 5 | 浏览器访问终端输出的 Local 地址 | 页面正常加载 | ✅ 已验证 |

> 注意：`.env` 已加入 `.gitignore`，首次 clone 后需手动执行 `cp -n .env.example .env`。端口被占用时请以终端实际输出的 `Local:` 地址为准。

---

## 2. 登录流程

| # | 检查项 | 测试步骤 | 期望 | 状态 |
|---|--------|---------|------|------|
| 1 | 登录页面是否显示 | 打开 `http://localhost:3000` | 显示登录卡片（邮箱 + 密码 + 登录按钮） | ✅ |
| 2 | 本地账号登录 | 输入在 Supabase 注册的邮箱和密码，点击「登录」 | 跳转主界面，顶部显示当前用户名 | ✅ |
| 3 | localStorage 写入 | 登录后打开 DevTools → Application → Local Storage | `ta_token` 和 `ta_user` 键均存在 | ✅ |
| 4 | 刷新后保持登录 | 登录成功后刷新页面（F5 / Cmd+R） | 直接显示主界面，不重新要求登录 | ✅ |
| 5 | 退出清除 token | 点击顶部「退出」按钮 | localStorage 中 `ta_token` / `ta_user` 消失，回到登录页 | ✅ |
| 6 | 401 自动 logout | 登录后手动删除 localStorage 中的 `ta_token`，发起分析请求 | 前端弹出"登录已过期，请重新登录"提示，自动回到登录页 | ⬜ 未专项验证 |

> 测试账号：在 Supabase 控制台预先注册，使用邮箱 + 密码登录。

---

## 3. 综合分析流程

每个用例通用检查项：

| 检查项 | 期望 |
|--------|------|
| 请求发送到 `VITE_API_BASE` | Network 面板中请求 URL 以 `.env` 中配置的 base 开头 |
| `POST /api/v1/analysis/comprehensive` 返回 200 | Status: 200 |
| loading 显示 | 出现进度条 + 四个旋转 Agent badge |
| 四个 Agent 状态显示 | 结果区域显示 technical / fundamental / peer_comparison / news 的 status badge |
| warnings 显示 | 若有 warning，黄色提示列表出现 |
| report 渲染 | 综合报告正常显示 Markdown 格式内容 |
| sections 包含四个子报告 | accordion 展示 technical / fundamental / peer_comparison / news |
| accordion 可展开/折叠 | 点击标题后内容展开；再点击后折叠 |
| Markdown 正常渲染 | h2/h3 标题有颜色，列表有缩进，无原始 `##`/`**` 符号外露 |
| Console 无 JS error | DevTools → Console 无红色报错 |
| Network 无异常请求 | 无 CORS 错误，无 4xx/5xx（除已知 warning 外） |

### 3.1 CN / 600519（贵州茅台）

| 检查项 | 期望 | 状态 |
|--------|------|------|
| 分析请求成功 | 200，约 35–45s 返回 | ✅ POST /analysis/comprehensive → 200 |
| warnings 数量 | 0–1 条（valuation 可能缺失） | ✅ |
| 四个 Agent 全部 success | status badge 均为 success | ✅ |
| 报告提及茅台业务/财务 | 内容可读，无乱码 | ✅ |

### 3.2 CN / 000001（平安银行）

| 检查项 | 期望 | 状态 |
|--------|------|------|
| 分析请求成功 | 200，约 35–45s 返回 | ⬜ 本轮未测试 |
| 高负债率正确识别 | 基本面报告中对银行业高杠杆有合理描述 | ⬜ 本轮未测试 |
| 无过强结论 | 报告中无"确定性"/"强劲上涨"等措辞 | ⬜ 本轮未测试 |

### 3.3 HK / 700（腾讯控股）

| 检查项 | 期望 | 状态 |
|--------|------|------|
| 分析请求成功 | 200，约 35–45s 返回 | ✅ POST /analysis/comprehensive → 200 |
| 港股基本面 warning | 出现"HK 基本面数据有限"相关 warning | ✅ |
| 港股估值 warning | 出现估值字段缺失 warning | ✅ |
| 报告声明字段边界 | 基本面子报告中有"港股基本面数据有限"说明 | ✅ |

### 3.4 CN / 300750（宁德时代）

| 检查项 | 期望 | 状态 |
|--------|------|------|
| 分析请求成功 | 200，约 35–45s 返回 | ⬜ 本轮未测试 |
| 同行数据缺失降级 | peer_comparison Agent 状态为 degraded 或 warning 提示同行不可用 | ⬜ 本轮未测试 |
| 无崩溃 | 同行数据缺失时系统不崩溃，仍返回其他三维报告 | ⬜ 本轮未测试 |

---

## 4. 组件检查

### `LoginCard.vue`

| 项目 | 说明 |
|------|------|
| 功能 | 邮箱密码登录表单，调用 Pinia authStore.login() |
| 输入 | 用户输入的邮箱（username）、密码 |
| 输出 | 登录成功后 authStore.token 非空，App.vue 切换到 RouterView |
| 验收标准 | 登录卡片居中显示；密码字段使用 `type="password"`；错误时显示 `.error-box`；登录中按钮不可重复点击 |
| 状态 | ✅ |

### `AppHeader.vue`

| 项目 | 说明 |
|------|------|
| 功能 | 顶部导航栏，显示产品名称、当前用户、退出按钮、综合分析/历史报告导航 |
| 输入 | 无 props（从 authStore 读取 currentUser） |
| 输出 | 点击退出调用 authStore.logout() |
| 验收标准 | 显示 `{{ authStore.currentUser }}`；点击退出后 localStorage 清空，页面回到 LoginCard；导航链接 active 高亮正确 |
| 状态 | ✅ |

### `StockInputPanel.vue`

| 项目 | 说明 |
|------|------|
| 功能 | 股票输入区：market 选择（CN/HK）、symbol 输入、快速示例、提交 |
| 输入 | `:loading` prop（bool）控制按钮禁用 |
| 输出 | emit `analyze` 事件，payload `{ market, symbol }` |
| 验收标准 | 快速示例点击后自动填充 market + symbol；`hoursBack` 输入框不存在（已移除，替换为"近 72 小时"说明文字）；loading 期间按钮禁用 |
| 状态 | ✅ |

### `LoadingPanel.vue`

| 项目 | 说明 |
|------|------|
| 功能 | 分析中的加载状态展示 |
| 输入 | 无 props，`v-if="loading"` 由父组件控制 |
| 输出 | 无 emit |
| 验收标准 | 出现蓝色进度条（shimmer 动画）；出现 4 个旋转 Agent badge（Technical / Fundamental / Peer / News） |
| 状态 | ✅ |

### `ErrorBox.vue`

| 项目 | 说明 |
|------|------|
| 功能 | 错误信息展示 |
| 输入 | `:message` prop（string） |
| 输出 | 无 emit |
| 验收标准 | `message` 为空字符串时不显示（`v-if="message"`）；有错误信息时显示红色/错误样式的 `.error-box` |
| 状态 | ⬜ 未专项验证（需主动触发错误） |

### `AgentStatusBar.vue`

| 项目 | 说明 |
|------|------|
| 功能 | 显示分析完成时间和四个 Agent 的执行状态 |
| 输入 | `:metadata`（含 `generated_at` 和 `agents` 字典）、`:market`、`:symbol` |
| 输出 | 无 emit |
| 验收标准 | 显示 `generated_at` 格式化时间；4 个 Agent badge 颜色正确（success=绿，failed=红，degraded=橙，unknown=灰） |
| 状态 | ✅（分析页 + 历史详情页均验证） |

### `WarningPanel.vue`

| 项目 | 说明 |
|------|------|
| 功能 | 显示分析 warnings（中文翻译） |
| 输入 | `:warnings`（string[]） |
| 输出 | 无 emit |
| 验收标准 | `warnings.length === 0` 时整个组件隐藏（`v-if="warnings.length"`）；有 warning 时展示中文翻译列表（由 `translateWarning()` 转换） |
| 状态 | ✅（HK/700 触发 warning，中文翻译正确显示） |

### `MarkdownReport.vue`

| 项目 | 说明 |
|------|------|
| 功能 | 将 Markdown 字符串渲染为 HTML，防 XSS |
| 输入 | `:content`（Markdown string） |
| 输出 | 无 emit |
| 验收标准 | 使用 `marked.parse` + `DOMPurify.sanitize`；`v-html` 输出；`markdown.css` 的样式（h2 颜色、code 背景等）正确应用；无原始 Markdown 符号外露 |
| 状态 | ✅（分析页 + 历史详情页均验证，无符号外露，无 Console 报错） |

### `SectionAccordion.vue`

| 项目 | 说明 |
|------|------|
| 功能 | 可折叠的四维子报告列表 |
| 输入 | `:sections`（Object，4 个 key）、`:agents`（Object，4 个 Agent 状态） |
| 输出 | 无 emit |
| 验收标准 | 4 个子报告标题默认折叠；点击后展开内容（`MarkdownReport` 渲染）；再点击折叠；每个标题右侧显示该 Agent 的 status badge；字数标注正确 |
| 状态 | ✅（分析页 + 历史详情页均验证） |

### `ComprehensiveAnalysisView.vue`

| 项目 | 说明 |
|------|------|
| 功能 | 综合分析页面根视图，协调所有子组件 |
| 输入 | 无 props（路由 `/` 渲染） |
| 输出 | 调用 `getComprehensive(market, symbol)` |
| 验收标准 | 分析中显示 `LoadingPanel`；失败时显示 `ErrorBox`；成功后显示 `AgentStatusBar` + `WarningPanel` + `MarkdownReport`（主报告）+ `SectionAccordion`（子报告）+ 保存报告按钮 + **下载 .md 按钮**；加载中禁止重复提交 |
| 状态 | ✅ |

### `ConfirmDialog.vue`（Phase 2A 新增）

| 项目 | 说明 |
|------|------|
| 功能 | 自定义确认对话框，替换原生 `confirm()`/`alert()`，与深色主题一致 |
| 输入 | `modelValue`（v-model 开关）、`title`、`message`、`confirmText`、`cancelText`、`danger`（红色按钮）、`loading`（禁用+spinner） |
| 输出 | emit `update:modelValue`、`confirm`、`cancel` |
| 技术细节 | `<Teleport to="body">`；loading 期间点击遮罩不关闭；无原生 `confirm()`/`alert()` 依赖 |
| 状态 | ✅ 构建验证通过，待浏览器 smoke test |

---

## 5. 安全检查

| # | 检查项 | 验证方式 | 期望 | 实际 | 状态 |
|---|--------|---------|------|------|------|
| 1 | Markdown 使用 DOMPurify | grep `DOMPurify` in `src/` | `DOMPurify.sanitize(raw)` 存在 | `utils/markdown.js:return DOMPurify.sanitize(raw)` | ✅ |
| 2 | token 未硬编码 | grep `Bearer ` in `src/` | 无字符串直接含 token 值 | 仅 `http.js` 中动态拼接 `authStore.token` | ✅ |
| 3 | `.env` 未提交 | `ls frontend/.env` | 文件不存在于 git tracked 列表 | `.env NOT present`（`.gitignore` 包含 `.env`） | ✅ |
| 4 | `.env.example` 存在 | `ls frontend/.env.example` | 文件存在 | 43 bytes，`-rw-r--r--` | ✅ |
| 5 | `API_BASE` 来自 `import.meta.env` | grep `VITE_API_BASE` in `src/` | 使用 `import.meta.env.VITE_API_BASE` | `http.js` 和 `auth.js` 均读取 env var | ✅ |
| 6 | 错误提示不泄露 token | 手动触发错误 → 查看 ErrorBox 显示内容 | 错误内容不含 JWT 字符串 | ⬜ 未专项验证 | ⬜ |
| 7 | 无 token 日志泄露 | grep `console.log` in `src/` | 无包含 token 的 log | 全局扫描：0 处 | ✅ |
| 8 | CORS preflight 通过 | `curl -X OPTIONS localhost:8000/api/v1/analysis/comprehensive -H "Origin: http://localhost:3000"` | `Access-Control-Allow-Origin: http://localhost:3000` | 后端返回正确 CORS 头 | ✅ |

---

## 6. 与 legacy 版本对比

对比 `frontend/index.legacy.html`（904 行单文件 MVP），确认以下功能保持一致：

| 功能 | index.legacy.html | 工程化版本 | 一致 | 状态 |
|------|-------------------|-----------|------|------|
| 登录页 UI | script setup 内联 | `LoginCard.vue` | ✅ | ✅ |
| JWT 存储键名 | `ta_token` / `ta_user` | `ta_token` / `ta_user`（不变） | ✅ | ✅（静态验证） |
| 登录接口 | `POST /auth/login` + body `{username,password}` | `auth.js` 同上 | ✅ | ✅（静态验证） |
| 401 auto-logout | inline in `analyze()` | 统一在 `http.js baseFetch()` | ✅（逻辑更优） | ⬜ 未专项验证 |
| 综合分析接口 | `POST /analysis/comprehensive` + body `{market,symbol}` | `analysis.js` 同上 | ✅ | ✅（静态验证） |
| hoursBack 输入框 | 存在（但未传后端） | 已移除，替换为说明文字 | ✅（按需求决策） | ✅（静态验证） |
| 快速示例 5 个 | 内联数组 | `EXAMPLES` 常量（warningMap.js） | ✅ | ✅（静态验证） |
| loading 进度条 | 存在 | `LoadingPanel.vue` | ✅ | ✅ |
| 4 个旋转 Agent badge | 存在 | `LoadingPanel.vue` | ✅ | ✅ |
| Agent 状态 badge | 存在 | `AgentStatusBar.vue` | ✅ | ✅ |
| generated_at 显示 | 存在 | `AgentStatusBar.vue` | ✅ | ✅ |
| warnings 中文翻译 5 条 | 内联 WARNING_MAP | `warningMap.js` | ✅ | ✅（HK/700 验证） |
| Markdown 渲染（marked + DOMPurify） | 内联 `renderMarkdown` | `utils/markdown.js` | ✅ | ✅（静态验证 + 浏览器验证） |
| 子报告 accordion | 存在 | `SectionAccordion.vue` | ✅ | ✅ |
| 退出登录 | `logout()` 内联 | `authStore.logout()` | ✅ | ✅ |
| 错误提示 | 内联 errorMsg | `ErrorBox.vue` | ✅ | ⬜ 未专项验证 |
| CSS 颜色/变量 | `--accent: #4f8ef7` 等 | `styles/variables.css`（完全相同） | ✅ | ✅（静态验证） |

---

## 7. 报告历史功能 Smoke Test

**实现日期：** 2026-05-26  
**浏览器验证日期：** 2026-05-26  
**测试标的：** CN/600519（贵州茅台）、HK/700（腾讯控股）  
**涉及接口：** `POST /api/v1/reports/`、`GET /api/v1/reports/`、`GET /api/v1/reports/{id}`、`DELETE /api/v1/reports/{id}`  
**涉及路由：** `/history`（列表）、`/history/:id`（详情）

### 7.1 生成综合分析并保存

| # | 步骤 | 期望 | 状态 |
|---|------|------|------|
| 1 | 登录后在分析页输入 CN/600519，点击"生成综合分析" | loading → 返回完整分析结果（约 35–45s） | ✅ POST /analysis/comprehensive → 200 |
| 2 | 分析完成后，结果区域底部出现"保存报告"按钮 | 按钮可点击，saveStatus = idle | ✅ |
| 3 | 点击"保存报告" | 按钮变为"保存中…"（spinner），调用 `POST /api/v1/reports/` | ✅ |
| 4 | 保存成功 | 按钮变为"已保存"（disabled）；右侧显示"✓ 已保存 查看"链接 | ✅ POST /reports/ → 201 |
| 5 | 保存成功后再次分析 HK/700 | saveStatus 重置为 idle，"保存报告"按钮重新出现 | ✅ |
| 6 | 网络请求检查 | Network 面板：`POST /api/v1/reports/` → HTTP 201；响应含 `id` 和 `created_at` | ✅ |

### 7.2 查看历史报告列表

| # | 步骤 | 期望 | 状态 |
|---|------|------|------|
| 1 | 点击顶部导航"历史报告" | 跳转 `/history`，列表自动加载 | ✅ GET /reports/ → 200 |
| 2 | 列表显示已保存的报告（CN/600519、HK/700） | 显示 market、symbol、report_type、创建时间、warning 数量、Agent badge | ✅ |
| 3 | 列表项不含报告正文 | Network 响应中无 `report_md`/`sections` 字段 | ✅ |
| 4 | market 筛选（选 CN） | 仅显示 market=CN 的报告，total 正确 | ✅ |
| 5 | symbol 筛选（输入 600519 + 查询） | 仅显示 symbol=600519 的报告 | ✅ |
| 6 | 空账号（无报告）状态 | 显示"暂无历史报告，去分析一支股票吧" | ⬜ 未专项验证 |

### 7.3 查看历史报告详情

| # | 步骤 | 期望 | 状态 |
|---|------|------|------|
| 1 | 点击列表项"查看详情" | 跳转 `/history/:id`，加载完整报告 | ✅ GET /reports/{id} → 200 |
| 2 | AgentStatusBar 正常显示 | 显示保存时的 generated_at、market/symbol、4 个 Agent 状态 badge | ✅ |
| 3 | WarningPanel 正常显示 | 若有 warning，显示中文翻译列表 | ✅（HK/700 warning 正确翻译） |
| 4 | 主报告 Markdown 正常渲染 | h2/h3 有颜色，无原始 `##` 符号外露；DOMPurify 保护有效 | ✅ |
| 5 | SectionAccordion 正常显示 | 4 个子报告可折叠展开 | ✅ |
| 6 | 底部显示"保存于 YYYY-MM-DD HH:MM:SS" | created_at 格式化正确 | ✅ |
| 7 | 点击"← 返回历史列表" | 跳回 `/history` | ✅ |
| 8 | Network 请求检查 | `GET /api/v1/reports/:id` → HTTP 200；响应含 `report_md`、`sections`、`report_metadata` | ✅ |

### 7.4 删除报告（Phase 2A：使用 ConfirmDialog）

> Phase 2A 后，删除确认已从原生 `confirm()` 替换为自定义 `ConfirmDialog.vue`。

| # | 步骤 | 期望 | 状态 |
|---|------|------|------|
| 1 | 在列表页点击"删除" | 弹出自定义 ConfirmDialog（深色主题，非原生浏览器弹窗） | ⬜ 待浏览器验证 |
| 2 | ConfirmDialog 点击"取消" | 关闭弹窗，报告不删除，列表不变 | ⬜ 待浏览器验证 |
| 3 | ConfirmDialog 点击遮罩 | 关闭弹窗，报告不删除 | ⬜ 待浏览器验证 |
| 4 | ConfirmDialog 点击"删除" | loading spinner 出现，调用 `DELETE /api/v1/reports/:id`；Network → HTTP 204 | ⬜ 待浏览器验证 |
| 5 | 删除成功后列表刷新 | 该报告从列表消失；total 减 1；ConfirmDialog 关闭 | ⬜ 待浏览器验证 |
| 6 | 删除失败 | 错误信息显示在页面 errorMsg/ErrorBox，不使用 alert() | ⬜ 待浏览器验证 |
| 7 | 在详情页点击"删除此报告" | 弹出 ConfirmDialog；确认后删除，自动跳转回 `/history` | ⬜ 待浏览器验证 |
| 8 | 直接访问已删除报告 URL | `GET /api/v1/reports/:id` → HTTP 404；前端显示错误提示 | ⬜ 未专项验证 |

### 7.5 鉴权与 Router Guard 检查（Phase 2A 更新）

| # | 检查项 | 期望 | 状态 |
|---|--------|------|------|
| 1 | token 过期时保存操作 | `POST /reports/` 返回 401 → 自动 logout，回到登录页 | ⬜ 未专项验证 |
| 2 | 未登录直接访问 `/history` | Router beforeEach 拦截 → 重定向到 `/`（显示登录页）；URL 变为 `/` | ⬜ 待浏览器验证 |
| 3 | 未登录直接访问 `/history/:id` | Router beforeEach 拦截 → 重定向到 `/` | ⬜ 待浏览器验证 |
| 4 | 登录状态访问 `/history` | 正常渲染历史列表，不触发重定向 | ⬜ 待浏览器验证 |
| 5 | Console 无红色 JS error | 全流程（生成→保存→历史→详情→删除）无报错 | ✅ 已确认（Phase 1） |
| 6 | Network 无 CORS 错误 | 所有 `/reports/` 请求正常 | ✅ 已确认 |

---

## 8. Markdown 下载 Smoke Test（Phase 2B）

**实现日期：** 2026-05-26  
**涉及文件：** `utils/exportMarkdown.js`（新增）、`ComprehensiveAnalysisView.vue`、`HistoryDetailView.vue`  
**构建验证：** 66 modules，exit 0 ✅

### 8.1 exportMarkdown.js 导出函数

| 函数 | 说明 |
|------|------|
| `buildReportMarkdown(result)` | 把 result 对象转为完整 Markdown 字符串；可独立复用（预览、PDF 等） |
| `buildFilename(result)` | 生成文件名；时间优先级：`result.created_at` → `metadata.generated_at` → `new Date()` |
| `downloadMarkdown(result)` | 调用上两个函数；Blob + createObjectURL + a.click() + revokeObjectURL |

### 8.2 导出内容结构

```markdown
# 综合分析报告：{market} / {symbol}
> 生成时间：YYYY-MM-DD HH:mm:ss
---
## Agent 执行状态
| 模块 | 状态 | 说明 |（固定顺序：技术面/基本面/同行对比/新闻面）
---
## 数据质量提示
（translateWarning() 翻译；无 warning 时显示"暂无数据质量提示。"）
---
## 综合分析
{result.report}
---
## 技术面分析 / 基本面分析 / 同行对比分析 / 新闻面分析
（空/null section 自动跳过；顺序来自 SECTION_DEFS）
```

### 8.3 文件名规则

| 规则 | 示例 |
|------|------|
| `analysis_{market}_{symbol}_{YYYYMMDD_HHmmss}.md` | `analysis_CN_600519_20260526_143022.md` |
| 历史报告：使用 `result.created_at` | `analysis_HK_700_20260526_091500.md` |
| 实时分析：使用 `new Date()`（保存前无 created_at） | 当前时间戳 |

### 8.4 综合分析页下载 Smoke Test

| # | 步骤 | 期望 | 状态 |
|---|------|------|------|
| 1 | 分析 CN/600519 完成后，save-bar 出现「下载 .md」按钮 | 按钮在「保存报告」左侧 | ⬜ 待浏览器验证 |
| 2 | 点击「下载 .md」 | 浏览器触发下载，无页面跳转 | ⬜ 待浏览器验证 |
| 3 | 文件名检查 | `analysis_CN_600519_YYYYMMDD_HHmmss.md`（当前时间） | ⬜ 待浏览器验证 |
| 4 | 文件内容：标题和时间 | 含 `# 综合分析报告：CN / 600519` 和 `> 生成时间：` | ⬜ 待浏览器验证 |
| 5 | 文件内容：Agent 状态表 | 含 `## Agent 执行状态` 表格，4 行 | ⬜ 待浏览器验证 |
| 6 | 文件内容：warnings | 含 `## 数据质量提示` 节 | ⬜ 待浏览器验证 |
| 7 | 文件内容：综合报告 | 含 `## 综合分析` 节，内容非空 | ⬜ 待浏览器验证 |
| 8 | 文件内容：四个子报告 | 含 `## 技术面分析`、`## 基本面分析`、`## 同行对比分析`、`## 新闻面分析` | ⬜ 待浏览器验证 |
| 9 | 下载后保存按钮状态不变 | saveStatus 未被重置 | ⬜ 待浏览器验证 |
| 10 | Console 无红色 JS error | 无 Blob/URL 相关报错 | ⬜ 待浏览器验证 |

### 8.5 历史详情页下载 Smoke Test

| # | 步骤 | 期望 | 状态 |
|---|------|------|------|
| 1 | 进入任意历史报告详情页，detail-footer 出现「下载 .md」按钮 | 按钮在「删除此报告」左侧 | ⬜ 待浏览器验证 |
| 2 | 点击「下载 .md」 | 浏览器触发下载 | ⬜ 待浏览器验证 |
| 3 | 文件名时间来源 | 使用 `result.created_at`（报告保存时间），不是当前时间 | ⬜ 待浏览器验证 |
| 4 | 文件内容结构正确 | 与 9.4 相同内容结构 | ⬜ 待浏览器验证 |
| 5 | 下载后 ConfirmDialog 未意外触发 | 点下载不弹删除确认框 | ⬜ 待浏览器验证 |
| 6 | 下载后删除流程正常 | 下载后点击「删除此报告」仍弹出 ConfirmDialog | ⬜ 待浏览器验证 |

### 8.6 HK/700 下载 Smoke Test

| # | 步骤 | 期望 | 状态 |
|---|------|------|------|
| 1 | 下载 HK/700 报告 | 文件名 `analysis_HK_700_YYYYMMDD_HHmmss.md` | ⬜ 待浏览器验证 |
| 2 | warnings 内容检查 | `## 数据质量提示` 节包含港股相关中文警告 | ⬜ 待浏览器验证 |

---

## 9. Dynamic Peer / 行业热门股 API Smoke Test（Phase 1D–1E）

**实现日期：** 2026-05-27（Phase 1A–1E）  
**测试方式：** curl + Python 脚本验证（已通过）；浏览器侧 peer_comparison section 渲染待确认  
**依赖：** 后端 `industry_hot_stock_snapshot` 表已有 2026-05-27 CN 市场银行/食品饮料快照数据

---

### 9.1 `/stocks/{market}/{symbol}/peers/fundamentals` — dynamic peer 数据端点

> 该端点升级后支持 PEER_MAP > dynamic_hot > none 三级降级，已通过 curl 验证。

#### 9.1.1 CN/600519（贵州茅台）— 期望 manual_map，不被 dynamic_hot 覆盖

| # | 检查项 | 期望 | 状态 |
|---|--------|------|------|
| 1 | HTTP 状态 | 200 OK | ✅ curl 验证 |
| 2 | `data_quality.peer_source` | `manual_map` | ✅ 已验证 |
| 3 | `peers` 列表内容 | 五粮液 000858 / 泸州老窖 000568 / 山西汾酒 600809 / 洋河股份 002304 | ✅ 已验证 |
| 4 | `industry_name` | `null`（PEER_MAP 不依赖行业映射） | ✅ 已验证 |
| 5 | `hot_stock_date` | `null` | ✅ 已验证 |
| 6 | `fallback_reason` | `null` | ✅ 已验证 |
| 7 | `comparison_fields.available` | 含 ROE / 毛利率 / 净利率等字段 | ✅ 已验证 |
| 8 | dynamic_hot 未覆盖 manual_map | peer_source 仍为 manual_map | ✅ 已验证 |

#### 9.1.2 CN/000001（平安银行）— 期望 dynamic_hot 银行行业

| # | 检查项 | 期望 | 状态 |
|---|--------|------|------|
| 1 | HTTP 状态 | 200 OK | ✅ curl 验证 |
| 2 | `data_quality.peer_source` | `dynamic_hot` | ✅ 已验证 |
| 3 | `data_quality.industry_name` | `银行` | ✅ 已验证 |
| 4 | `data_quality.industry_code` | `801780` | ✅ 已验证 |
| 5 | `data_quality.hot_stock_date` | `2026-05-27` | ✅ 已验证 |
| 6 | `data_quality.hot_score_version` | `v1` | ✅ 已验证 |
| 7 | `peers` 不包含 000001 自身 | 已排除目标股 | ✅ 已验证 |
| 8 | `peers` 包含中国平安、浦发银行、建设银行、招商银行、兴业银行 | Top5 银行热门股 | ✅ 已验证 |
| 9 | `comparison_fields.available` 含成长/盈利字段 | ROE / 净利率 / 营收增长等 | ✅ 已验证 |

#### 9.1.3 CN/300750（宁德时代）— 期望 none，无行业映射降级

| # | 检查项 | 期望 | 状态 |
|---|--------|------|------|
| 1 | HTTP 状态 | 200 OK | ✅ curl 验证 |
| 2 | `data_quality.peer_source` | `none` | ✅ 已验证 |
| 3 | `peers` | `[]`（空列表） | ✅ 已验证 |
| 4 | `data_quality.fallback_reason` | `"industry mapping not found"` | ✅ 已验证 |
| 5 | `data_quality.message` | `"No industry mapping found for this symbol."` | ✅ 已验证 |
| 6 | 不编造同行 | peer 列表为空，无虚构公司 | ✅ 已验证 |

---

### 9.2 `/industries/stocks/{market}/{symbol}/dynamic-peers` — 专用 dynamic peer 端点

> Phase 1C 新增独立端点，返回行业发现元数据更完整（含 hot_score / score_factors）。

| # | 测试用例 | 检查项 | 状态 |
|---|----------|--------|------|
| 1 | CN/600519 | peer_source = manual_map；peers = 四只白酒股；industry = null | ✅ curl 验证 |
| 2 | CN/000001 | peer_source = dynamic_hot；industry.industry_name = 银行；热门股排行含 hot_score 字段 | ✅ curl 验证 |
| 3 | CN/300750 | peer_source = none；peers = []；fallback_reason = industry mapping not found | ✅ curl 验证 |
| 4 | HK/700（腾讯） | peer_source = manual_map（HK/700 在 PEER_MAP）；peers = 阿里/美团/网易/百度 | ✅ curl 验证 |
| 5 | CN/000001 limit=2 | peers 仅 2 条 | ✅ curl 验证 |

---

### 9.3 `/analysis/peer-comparison` — 独立同行对比分析（Phase 1D）

> 已通过 curl + LLM 报告内容验证。

| # | 检查项 | 期望 | 状态 |
|---|--------|------|------|
| 1 | CN/000001：peer_source | `dynamic_hot` | ✅ 已验证 |
| 2 | CN/000001：报告含"Hot Score"说明 | 是 | ✅ 已验证 |
| 3 | CN/000001：报告含"市场关注度"说明 | 是 | ✅ 已验证 |
| 4 | CN/000001：无违规词汇（更优质/更值得投资/行业龙头） | 无 | ✅ 已验证 |
| 5 | CN/600519：peer_source | `manual_map` | ✅ 已验证 |
| 6 | CN/600519：报告无 dynamic_hot 说明 | 无 | ✅ 已验证 |

---

### 9.4 `/analysis/comprehensive` — 综合分析接入 dynamic peers（Phase 1E）

> peer_comparison section 现在由 analyze_async(db, market, symbol) 生成，支持动态同行。  
> **已通过 curl + LLM 报告内容验证；浏览器 peer_comparison accordion 渲染待确认。**

#### 9.4.1 CN/000001（平安银行）— 期望 dynamic_hot 进入综合报告

| # | 检查项 | 期望 | 状态 |
|---|--------|------|------|
| 1 | HTTP 状态 | 200 OK | ✅ curl 验证 |
| 2 | `metadata.agents.peer_comparison.status` | `success` | ✅ 已验证 |
| 3 | `sections.peer_comparison` 不含"暂无同行配置" | 已找到动态同行 | ✅ 已验证 |
| 4 | `sections.peer_comparison` 含口径限制声明 | 含 Hot Score / 市场关注度说明 | ✅ 已验证 |
| 5 | `metadata.warnings` 不含"peer comparison is unavailable" | 无该警告 | ✅ 已验证 |
| 6 | 综合报告同行段落不含"更优质/更值得投资" | 无违规词汇 | ✅ 已验证 |
| 7 | 浏览器 peer_comparison accordion 渲染正确 | Markdown 正常显示，含银行行业说明 | ⬜ 待浏览器验证 |

#### 9.4.2 CN/600519（贵州茅台）— 期望仍使用 manual_map

| # | 检查项 | 期望 | 状态 |
|---|--------|------|------|
| 1 | HTTP 状态 | 200 OK | ✅ curl 验证 |
| 2 | `sections.peer_comparison` 含五粮液等四只白酒 | 是 | ✅ 已验证 |
| 3 | `sections.peer_comparison` 不含 dynamic_hot 说明 | 无 | ✅ 已验证 |
| 4 | peer_source = manual_map | 是 | ✅ 已验证 |
| 5 | 旧行为未被破坏 | 同行列表与 Phase 1D 前一致 | ✅ 已验证 |

#### 9.4.3 CN/300750（宁德时代）— 期望无同行配置降级

| # | 检查项 | 期望 | 状态 |
|---|--------|------|------|
| 1 | HTTP 状态 | 200 OK | ✅ curl 验证 |
| 2 | `sections.peer_comparison` 说明无行业映射 | "industry mapping not found" | ✅ 已验证 |
| 3 | 不编造同行 | peer 列表为空 | ✅ 已验证 |
| 4 | 其他三个 Agent 正常 | technical / fundamental / news 均 success | ✅ 已验证 |

---

### 9.5 行业分类 API Smoke Test

| 端点 | 测试 | 状态 |
|------|------|------|
| `GET /industries/?market=CN` | 返回申万一级行业列表 | ✅ 已验证 |
| `GET /industries/stocks/CN/000001` | 返回 industry_name=银行，industry_code=801780 | ✅ 已验证 |
| `GET /industries/stocks/CN/600519` | 返回 industry_name=食品饮料 | ✅ 已验证 |
| `GET /industries/CN/801780/hot-stocks` | 返回银行行业 Top5 热门股（含 hot_score） | ✅ 已验证 |
| `GET /industries/CN/801120/hot-stocks` | 返回食品饮料行业 Top5 热门股 | ✅ 已验证 |

---

### 9.6 当前阶段状态更新（Phase 1A–1E）

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1A | 行业分类表（industry_master / stock_industry_map）+ IndustryClassificationService + 3 个行业 API | ✅ 已完成 |
| Phase 1B | 行业热门股快照（industry_hot_stock_snapshot）+ Hot Score 计算 + IndustryHotStockService + hot-stocks API | ✅ 已完成 |
| Phase 1C | DynamicPeerDiscoveryService + GET /industries/stocks/{market}/{symbol}/dynamic-peers | ✅ 已完成 |
| Phase 1D | GET /stocks/peers/fundamentals 动态化 + POST /analysis/peer-comparison 动态化 | ✅ 已完成 |
| Phase 1E | ComprehensiveAnalysisCoordinator 接入 dynamic peers（analyze_async） | ✅ 已完成 |

---

## 10. P0 问题

**当前未发现阻塞前端工程化演示的 P0 问题。**

`npm install` + `npm run build` 均成功（66 modules，exit 0），dev server 正常启动，CORS 验证通过，所有组件 import 解析正确。报告历史后端 CRUD 接口全部通过 curl 测试。浏览器 smoke test（CN/600519、HK/700）全流程通过，Console 无红色报错，Network 全部请求返回预期状态码。

Phase 2A（Router Guard + ConfirmDialog）和 Phase 2B（Markdown 下载）均已构建验证通过，待浏览器 smoke test。

---

## 11. 已知限制

| # | 限制 | 说明 |
|---|------|------|
| 1 | ~~无报告历史~~ | ✅ 报告历史 Phase 1 已完成：保存 / 列表 / 详情 / 删除 |
| 2 | 刷新后分析结果丢失（当前会话） | 综合分析 result 存储在 Vue ref 中，刷新后清空；需手动点击"保存报告"后才能在历史中查阅 |
| 3 | 无 Watchlist | 自选股功能尚未实现 |
| 4 | ~~无 PDF/Markdown 导出~~ | ✅ Phase 2B 已完成 Markdown 下载；PDF 导出为 P2/P3 后续项 |
| 5 | 前端未做正式部署配置 | 无 Nginx config、无 HTTPS 配置，仅用于本地 dev 演示 |
| 6 | 端口 3000 被占用时需访问实际端口 | Vite 自动切换端口，请以终端输出的 `Local:` 地址为准 |
| 7 | comprehensive 接口耗时较长 | 四个 Agent 并行约 35–45s；无前端超时提示（未配置 AbortController） |
| 8 | ~~无 Router 导航守卫~~ | ✅ Phase 2A 已完成：`beforeEach` 守卫，未登录访问 /history 重定向到 / |
| 9 | ~~原生 confirm()/alert()~~ | ✅ Phase 2A 已完成：全部替换为 ConfirmDialog.vue |
| 10 | 键盘 Esc 不关闭 ConfirmDialog | 当前 ConfirmDialog 未监听 keydown Escape 事件（可访问性改进项） |
| 11 | PDF 导出 | 后续 P2/P3 功能；当前仅支持 .md 下载 |

---

## 12. P1/P2 优化项

| # | 优化项 | 优先级 | 说明 |
|---|--------|--------|------|
| 1 | ~~报告历史功能~~ | ~~高~~ | ✅ 已完成：后端 CRUD + 前端保存/列表/详情/删除 |
| 2 | ~~Router 导航守卫~~ | ~~中~~ | ✅ 已完成：Phase 2A beforeEach |
| 3 | ~~自定义确认弹窗~~ | ~~中~~ | ✅ 已完成：Phase 2A ConfirmDialog.vue |
| 4 | ~~Markdown 导出~~ | ~~中~~ | ✅ 已完成：Phase 2B exportMarkdown.js |
| 5 | ~~请求取消 / loading UX~~ | ~~中~~ | ✅ 已完成：Phase 2D AbortController + 阶段性等待提示 + 取消按钮 |
| 6 | Watchlist | 中 | 自选股列表，方便快速分析常用标的 |
| 7 | PDF 导出 | 低/P2 | 支持将报告下载为 PDF；需引入打印/PDF 库 |
| 8 | 前端部署配置 | 中 | 添加 Nginx config + HTTPS；配置生产环境 VITE_API_BASE |
| 9 | 页面性能优化 | 低 | 当前 bundle 未做 chunk splitting；大型 marked/DOMPurify 可异步加载 |
| 10 | UI 细节优化 | 低 | 移动端适配；键盘 Enter 提交；symbol 输入自动大写；ConfirmDialog Esc 关闭 |

---

## 10. Phase 2D — Loading / Timeout / Cancel Smoke Test

**文档更新：** 2026-05-27  
**涉及文件：** `src/api/analysis.js`、`src/views/ComprehensiveAnalysisView.vue`、`src/components/LoadingPanel.vue`

### 10.1 变更说明

| 变更 | 说明 |
|------|------|
| `analysis.js` 新增 `options` 参数 | `getComprehensive(market, symbol, { signal })` |
| `http.js` 无需修改 | `baseFetch` 已通过 `...options` 展开自动透传 `signal` |
| `LoadingPanel.vue` 新增 props | `elapsedSeconds`、`loadingHint`、`cancellable`；`emit('cancel')` |
| `ComprehensiveAnalysisView.vue` 新增逻辑 | `AbortController`、`setInterval` timer、`cancelAnalysis()`、`onUnmounted` 清理 |
| 旧 result 保留策略 | 新分析开始时不清空 result；仅在新 result 成功返回后覆盖；失败/取消时 result 保持原值 |

### 10.2 等待提示阈段

| 已等待时间 | loadingHint 文案 |
|------------|-----------------|
| 0–14 秒 | 正在启动多维分析，请稍候... |
| 15–44 秒 | 正在获取行情、基本面、同行与新闻数据... |
| 45–89 秒 | 数据源或 LLM 响应较慢，系统仍在处理中... |
| ≥ 90 秒 | 本次分析耗时较长，可继续等待或取消后重试。 |

### 10.3 测试用例

#### 场景 A：正常分析 CN/600519（基础 loading UX）

| # | 检查项 | 期望 | 状态 |
|---|--------|------|------|
| 1 | 点击分析后 LoadingPanel 出现 | `v-if="loading"` 为 true | ⬜ |
| 2 | `已等待 N 秒` 每秒递增 | 从 0 开始，每秒 +1 | ⬜ |
| 3 | loadingHint 在 15s 后切换 | 文案切换到第二段 | ⬜ |
| 4 | `取消分析` 按钮可见 | cancellable=true，按钮显示 | ⬜ |
| 5 | 分析完成后 LoadingPanel 消失 | loading=false | ⬜ |
| 6 | 报告正常展示 | result 包含 report / sections / metadata | ⬜ |
| 7 | `已等待 N 秒` 不继续递增 | timer 已 clearInterval | ⬜ |

#### 场景 B：正常分析 HK/700（warnings / 报告完整性）

| # | 检查项 | 期望 | 状态 |
|---|--------|------|------|
| 1 | loading UX 正常 | elapsedSeconds 递增，hint 显示 | ⬜ |
| 2 | HK warnings 正常 | `HK fundamentals coverage is limited.` 等 warning 显示 | ⬜ |
| 3 | 报告正常展示 | 报告含 HK 基本面限制说明 | ⬜ |

#### 场景 C：取消分析

| # | 检查项 | 操作 | 期望 | 状态 |
|---|--------|------|------|------|
| 1 | 点击分析，loading 出现 | 点击「生成综合分析」 | LoadingPanel 可见 | ⬜ |
| 2 | 点击取消分析 | 点击 LoadingPanel 内「取消分析」按钮 | 按钮可点击 | ⬜ |
| 3 | loading 停止 | — | LoadingPanel 消失 | ⬜ |
| 4 | 取消提示显示 | — | `本次分析已取消，已有报告未被清空。` 显示在 ErrorBox | ⬜ |
| 5 | 旧报告保留（有旧 result 时） | 在已有报告时触发取消 | 旧报告仍可见 | ⬜ |
| 6 | 无旧报告时页面干净 | 第一次分析立即取消 | 只有取消提示，无报告区 | ⬜ |
| 7 | 不跳转、不 logout | — | 页面保持综合分析页 | ⬜ |
| 8 | saveStatus 不重置 | 取消前已保存报告 | 「✓ 已保存」标签仍显示 | ⬜ |
| 9 | Network 面板 | DevTools → Network | 请求出现 `(canceled)` 状态 | ⬜ |

#### 场景 D：连续分析（timer 重置验证）

| # | 检查项 | 操作 | 期望 | 状态 |
|---|--------|------|------|------|
| 1 | 先分析 CN/600519 | 等待完成 | result 展示 600519 报告 | ⬜ |
| 2 | 再分析 CN/000001 | 点击分析 | elapsedSeconds 从 **0** 重新开始 | ⬜ |
| 3 | loadingHint 重置 | — | 显示初始文案「正在启动多维分析...」 | ⬜ |
| 4 | 旧报告（600519）在新分析期间仍显示 | — | loading=true 期间旧 result 可见 | ⬜ |
| 5 | 新报告成功后旧报告被替换 | — | result 更新为 000001 报告 | ⬜ |
| 6 | saveStatus 重置为 idle | — | 新报告「保存报告」按钮可用 | ⬜ |
| 7 | DevTools → Memory | — | 无 setInterval 重复注册（无 timer 泄漏） | ⬜ |

#### 场景 E：分析中离开页面

| # | 检查项 | 操作 | 期望 | 状态 |
|---|--------|------|------|------|
| 1 | 分析中切换到历史页 | 点击顶部「历史报告」导航 | 页面跳转 `/history` | ⬜ |
| 2 | 无 JS 错误 | DevTools → Console | 无红色 error | ⬜ |
| 3 | timer 被清理 | — | `onUnmounted` 触发 clearInterval（可在 DevTools 断点验证） | ⬜ |
| 4 | 请求被 abort | — | Network 面板请求变为 canceled | ⬜ |
| 5 | 返回综合分析页 | 点击顶部「综合分析」 | 页面正常，loading=false，无残留状态 | ⬜ |

### 10.4 错误文案验收

| 场景 | 期望 errorMsg | 实际 |
|------|---------------|------|
| 用户取消 | `本次分析已取消，已有报告未被清空。` | ⬜ |
| 网络断开 | `Failed to fetch` 或 `分析请求失败，请稍后重试。` | ⬜ |
| 服务器 503 | `detail` 字段内容（由 baseFetch 抛出） | ⬜ |
| 401 | 自动 logout，不在本页显示 errorMsg | ⬜ |

### 10.5 npm run build 验证

```bash
cd frontend && npm run build
```

| 检查项 | 期望 | 状态 |
|--------|------|------|
| build exit 0 | exit 0 | ⬜ |
| 无未解析 import | 无 `Could not resolve` 警告 | ⬜ |
| 无 Vue SFC 警告 | 无 `Missing required prop` 等 | ⬜ |
| chunk 数量合理 | 新 chunk 不超过 2 个 | ⬜ |

---

## Phase W1 — Watchlist 自选股前端专项测试（2026-05-29）

> **代码状态：** ✅ 已实现，`npm run build` 通过（75 modules）  
> **浏览器验证：** ✅ 全部核心用例通过（2026-05-29）  
> **测试入口：** `http://localhost:3000/watchlist`

### W1.1 路由与导航

| # | 测试项 | 操作步骤 | 预期 | 状态 |
|---|--------|----------|------|------|
| 1 | /watchlist 路由注册 | 已登录，访问 `http://localhost:3000/watchlist` | 页面正常渲染，不 404 | ✅ |
| 2 | AppHeader 自选股导航 | 登录后查看顶部 | 出现「综合分析 / 历史报告 / 自选股」三项，active 样式正确 | ✅ |
| 3 | 未登录跳转守卫 | 退出登录后访问 `/watchlist` | 自动重定向到 `/`（登录页），不出现空白或报错 | ✅ |
| 4 | 未登录直接访问 /history | 退出登录后访问 `/history` | 与 W1.3 一致，重定向到 `/`（原有守卫不退化） | ✅ |

### W1.2 添加表单

| # | 测试项 | 操作步骤 | 预期 | 状态 |
|---|--------|----------|------|------|
| 5 | 添加 CN/600519 成功 | 选 CN，输入 600519，点击添加 | 列表出现该条目，symbol 显示 `600519` | ✅ |
| 6 | 添加 CN/000001（前导零） | 选 CN，输入 000001，点击添加 | 列表显示 `000001`，不截断为 `1` | ✅ |
| 7 | 添加 HK/700 | 选 HK，输入 700，点击添加 | 列表出现 HK 700 | ⬜ |
| 8 | 带名称添加 | 填入 name 字段"平安银行"后提交 | 列表卡片显示名称"平安银行" | ⬜ |
| 9 | symbol 为空不提交 | 不填 symbol，点添加按钮 | 按钮 disabled，不发请求 | ⬜ |
| 10 | 重复添加 409 提示 | 再次添加 CN/600519 | 表单下方出现"该股票已在自选股中"，列表不新增条目 | ✅ |
| 11 | 添加成功后清空表单 | 成功添加后查看表单 | symbol 和 name 输入框清空，market 保留 | ⬜ |

### W1.3 删除功能

| # | 测试项 | 操作步骤 | 预期 | 状态 |
|---|--------|----------|------|------|
| 12 | 删除弹出 ConfirmDialog | 点击任一条目的"删除"按钮 | 弹出确认对话框，标题"删除自选股"，有"删除"和"取消"按钮 | ✅ |
| 13 | 取消不删除 | 弹框内点"取消" | 对话框关闭，列表条目数量不变 | ✅ |
| 14 | 确认删除后列表刷新 | 弹框内点"删除" | 对话框关闭，该条目从列表移除，total 减少 1 | ✅ |
| 15 | 删除最后一条后显示空状态 | 删除全部条目 | 显示空状态提示文案 | ⬜ |

### W1.4 query 联动 — 跳转综合分析页

| # | 测试项 | 操作步骤 | 预期 | 状态 |
|---|--------|----------|------|------|
| 16 | "分析"按钮跳转 URL | 点击 CN/600519 的"分析"按钮 | URL 变为 `/?market=CN&symbol=600519` | ✅ |
| 17 | 综合分析表单自动填入 | 跳转后查看综合分析表单 | 市场选中 `CN`，代码填入 `600519` | ✅ |
| 18 | keep-alive 下切换标的 | 先点分析 600519，返回自选股，点分析 000001 | 综合分析表单更新为 `000001`，不保留旧值 `600519` | ✅ |
| 19 | 跳转后手动修改代码 | 填入后手动改为其他代码，点生成分析 | 分析使用手动修改后的代码，不被 props 覆盖 | ⬜ |
| 20 | 分析完成后回自选股 | 分析结束后点"自选股"导航 | Watchlist 列表完整显示，无缓存或状态冲突 | ⬜ |

### W1.5 query 联动 — 跳转历史报告页

| # | 测试项 | 操作步骤 | 预期 | 状态 |
|---|--------|----------|------|------|
| 21 | "历史报告"按钮跳转 URL | 点击 CN/600519 的"历史报告"按钮 | URL 变为 `/history?market=CN&symbol=600519` | ✅ |
| 22 | 历史报告页自动筛选 | 跳转后查看历史报告筛选栏 | 市场选中 `CN`，代码填入 `600519`，报告列表自动加载该股历史 | ✅ |
| 23 | 直接访问 /history 无预填 | 不通过 Watchlist，点导航"历史报告" | 市场和代码字段为空，显示全量历史报告（原行为不变） | ✅ |

### W1.6 keep-alive 专项

> `ComprehensiveAnalysisView` 被 `<keep-alive>` 缓存，路由切换时 `setup()` 不重新执行。
> 验证 `watch(route.query)` 是否能在 re-activation 时正确响应 query 变化。

| # | 测试项 | 预期 | 状态 |
|---|--------|------|------|
| 24 | 第一次从自选股跳转综合分析 | 表单填入正确的 market/symbol | ✅ |
| 25 | 回到自选股后点击另一只股票分析 | 表单更新为新 market/symbol，不残留上次值 | ✅ |
| 26 | 连续点击三只不同标的 | 每次跳转表单都与 query 参数一致 | ✅ |
| 27 | 表单填入后用户手动清空 symbol | 手动清空后，query watch 不会自动重填（watch 只在 query 变化时触发，不轮询） | ⬜ |

### W1.7 build 验证

```bash
cd frontend && npm run build
```

| 检查项 | 期望 | 状态 |
|--------|------|------|
| build exit 0 | exit 0 | ✅ 已验证（2026-05-29） |
| 无未解析 import | 无 `Could not resolve` 警告 | ✅ |
| WatchlistView chunk 存在 | `WatchlistView-*.js` + `WatchlistView-*.css` 出现在 dist/assets/ | ✅ |
| 总 modules 数 | 75 modules transformed | ✅ |

### W1.8 Network 验证（浏览器 DevTools）

登录后在 `/watchlist` 页面打开 DevTools → Network，执行以下操作：

| 操作 | 期望请求 | 期望状态码 | 状态 |
|------|----------|----------|------|
| 页面加载 | `GET /api/v1/watchlist/` | 200 | ✅ |
| 添加股票 | `POST /api/v1/watchlist/` | 201 | ✅ |
| 重复添加 | `POST /api/v1/watchlist/` | 409 | ✅ |
| 删除确认 | `DELETE /api/v1/watchlist/{id}` | 204 | ✅ |
| PATCH（如有） | `PATCH /api/v1/watchlist/{id}` | 200 | ⬜ |

---

## W2. Watchlist 最近报告联动专项测试（Phase W2）

> **验证范围说明：** 本章节的验证结果来自代码路径审查、OpenAPI schema 验证（curl）、`npm run build` 构建验证和数据流逻辑分析，**不包含**真实浏览器人工点击测试。核心路径已通过代码审查、schema 验证与构建验证；真实浏览器点击验证可在后续日常使用中继续补充。

### W2.1 本阶段改动范围

| 文件 | 改动类型 | 内容 |
|------|---------|------|
| `backend/app/models/watchlist_item.py` | 新增 schema | `WatchlistLatestReport`（5 字段）；`WatchlistItemResponse.latest_report` 可选字段 |
| `backend/app/routers/watchlist.py` | 改 GET 逻辑 | 两次查询 + ROW_NUMBER 窗口函数 + Python join；严格排除 report_md / sections 大字段 |
| `frontend/src/views/WatchlistView.vue` | 模板 + 逻辑 | 最近报告摘要区块、条件主按钮、`goLatestReport` 函数 |

### W2.2 后端 Schema 验证（curl）

验证日期：2026-05-29 | 端口：8001

| # | 验证项 | 状态 |
|---|--------|------|
| 1 | `WatchlistLatestReport` 包含且仅包含 5 个字段：`agents / created_at / id / report_type / warnings` | ✅ |
| 2 | `WatchlistLatestReport` 不含大字段（`report_md / sections / report_metadata`） | ✅ |
| 3 | `WatchlistItemResponse.latest_report` 字段存在 | ✅ |
| 4 | `WatchlistItemResponse.latest_report` 非必填（可为 null） | ✅ |
| 5 | POST `/watchlist/` 响应 schema 未因本次改动破坏（仍为 `WatchlistItemResponse`） | ✅ |
| 6 | GET `/watchlist/` 响应为 `WatchlistListResponse`（含嵌套 `latest_report`） | ✅ |
| 7 | 无 token → 401（后端鉴权未退化） | ✅ |

通过率：**7 / 7** ✅

### W2.3 前端模板验证（build）

```bash
cd frontend && npm run build
```

| 检查项 | 期望 | 状态 |
|--------|------|------|
| build exit 0 | exit 0，无 error | ✅ 已验证（2026-05-29） |
| 无未解析 import（warningMap.js 新增 AGENT_NAMES 使用） | 无 `Could not resolve` | ✅ |
| WatchlistView chunk 存在 | `WatchlistView-*.js` 在 dist/assets/ | ✅ |

### W2.4 验证项（代码路径与构建验证）

> 验证方式：代码审查（模板/脚本逐行核对）+ 逻辑分析（数据流追踪）+ 构建验证。  
> 以下 ✅ 均为**静态/结构性验证**，非浏览器实时点击结果。  

| # | 场景 | 验证方式 | 关键代码 | 状态 |
|---|------|---------|---------|------|
| 1 | 有报告卡片显示最近分析时间 | 代码审查 | `WatchlistView.vue:81` `formatTime(item.latest_report.created_at)` | ✅ |
| 2 | warnings 非空显示"⚠ N 条提示" | 代码审查 | `WatchlistView.vue:83-85` `v-if="...warnings.length"` | ✅ |
| 3 | Agent 状态徽章（4 个） | 代码审查 + 构建 | `WatchlistView.vue:87-93` `v-for AGENT_NAMES` + `badgeClass()` | ✅ |
| 4 | 有报告时"查看最近报告"主按钮 | 代码审查 | `WatchlistView.vue:100-103` `v-if="item.latest_report"` btn-primary | ✅ |
| 5 | 点击跳转 `/history/{id}` | 代码审查 | `WatchlistView.vue:248-250` `router.push('/history/' + id)` | ✅ |
| 6 | 无报告显示"暂无分析报告" | 代码审查 | `WatchlistView.vue:95` `<div v-else class="no-report">` | ✅ |
| 7 | 无报告时"立即分析"主按钮 | 代码审查 | `WatchlistView.vue:109-113` `<template v-else>` btn-primary | ✅ |
| 8 | CN/000001 前导零联合键匹配 | 逻辑分析 | 后端 `(row["market"], row["symbol"])` 字符串精确匹配；`validate_symbol` 只 `.strip()`；VARCHAR(32) 不截断 | ✅ |
| 9 | 删除报告后 latest_report 置空 | 逻辑分析 | 物理删除后 ROW_NUMBER 无匹配 → `latest_map.get(...)` 返回 None | ✅ |

### W2.5 API 响应结构验证（Schema 审查）

| 操作 | 期望请求 | 期望状态码 | 状态 |
|------|----------|----------|------|
| 页面加载（有已保存报告） | `GET /api/v1/watchlist/` | 200；items[*].latest_report 为 WatchlistLatestReport 对象 | ✅ Schema 验证 |
| 点击"查看最近报告" | `GET /api/v1/reports/{id}` | 200（依赖 HistoryDetailView，W1 已验证） | ✅ W1 回归 |
| 页面加载（无报告） | `GET /api/v1/watchlist/` | 200；items[*].latest_report 为 null | ✅ 逻辑分析 |

---

## W3. Watchlist Note 内联编辑专项测试（Phase W3）

> **验证范围说明：** 本章节验证来自代码路径审查、OpenAPI schema 验证与构建验证，**不包含**真实浏览器人工点击测试。核心路径均已通过代码审查；视觉效果（聚焦动效、spinner、hover 背景）可在后续日常使用中补充验证。

### W3.1 本阶段改动范围

| 文件 | 改动类型 | 内容 |
|------|---------|------|
| `backend/app/routers/watchlist.py` | 1 行修改 | `item.note = body.note or None`（`""` → null，实现 note 清空） |
| `frontend/src/views/WatchlistView.vue` | 模板 + script + style | +63 行：5 个 ref、4 个函数、inline textarea 模板、note 编辑样式 |

### W3.2 后端 Schema 验证（curl，6/6 ✅）

验证日期：2026-05-29

| # | 验证项 | 状态 |
|---|--------|------|
| 1 | `WatchlistPatchRequest.note` 字段存在（`anyOf: string \| null`） | ✅ |
| 2 | `note` 允许 null（支持清空） | ✅ |
| 3 | `PATCH /watchlist/{item_id}` 端点存在 | ✅ |
| 4 | `WatchlistItemResponse` 响应含 `note` 字段 | ✅ |
| 5 | PATCH 响应类型为 `WatchlistItemResponse` | ✅ |
| 6 | 无 token → 401（鉴权未退化） | ✅ |

### W3.3 构建验证

| 检查项 | 期望 | 状态 |
|--------|------|------|
| build exit 0 | exit 0，无 error | ✅ 已验证（2026-05-29） |
| `nextTick` / `patchWatchlist` import 无未解析 | 无 `Could not resolve` | ✅ |
| WatchlistView chunk 增长合理 | 5.22 kB → 6.68 kB（+note 逻辑） | ✅ |

### W3.4 代码路径验证（12 项）

| # | 场景 | 验证方式 | 关键代码 | 状态 |
|---|------|---------|---------|------|
| 1 | 空 note 显示"＋ 添加备注"占位 | 代码审查 | `vue:82` `v-else class="note-placeholder"` | ✅ |
| 2 | 点击进入编辑态，textarea 聚焦 | 代码审查 | `vue:79` `@click="startEditNote"` + `nextTick→focus()` | ✅（视觉待浏览器） |
| 3 | 有备注时预填原值 | 代码审查 | `editNoteValue.value = item.note ?? ''` | ✅ |
| 4 | Enter 保存 + 本地更新 + 不重拉列表 | 代码审查 | `onNoteKeydown` Enter→`saveNote`；`item.note=updated.note`；无 `loadItems()` | ✅ |
| 5 | Shift+Enter 换行不保存 | 代码审查 | `!event.shiftKey` 守卫 | ✅ |
| 6 | Escape 取消不发请求 | 代码审查 | `cancelEditNote()` 仅清零 `editingNoteId` | ✅ |
| 7 | blur 自动保存 | 代码审查 | `@blur="saveNote(item)"` | ✅ |
| 8 | 内容未变 blur 不发 PATCH | 代码审查 | `newNote === oldNote` → 静默退出 | ✅ |
| 9 | 清空 → 后端 null → 占位复现 | 代码审查 + Schema | `"" or None`（后端） + `updated.note===null`→`v-else`（前端） | ✅ |
| 10 | 保存中 disabled + spinner | 代码审查（视觉待浏览器） | `:disabled="savingNoteId===item.id"` + `v-if spinner` | ✅ |
| 11 | 切换卡片自动保存，失败不切换 | 代码审查 | `await saveNote(prev)` + `if(noteError.value) return` | ✅ |
| 12 | W1/W2 回归（添加/删除/分析/报告） | 代码审查 | note 逻辑独立；现有函数未改动 | ✅ |

### W3.5 新增 Vue 状态与函数一览

| 标识 | 类型 | 用途 |
|------|------|------|
| `editingNoteId` | `ref(null)` | 当前处于编辑态的 item.id |
| `editNoteValue` | `ref('')` | textarea `v-model` |
| `savingNoteId` | `ref(null)` | PATCH 进行中的 item.id（disabled + spinner） |
| `noteError` | `ref('')` | 保存失败错误信息 |
| `noteTextareaRefs` | `{}` | DOM 元素引用（非响应式，仅用于 `focus()`） |
| `startEditNote(item)` | async fn | 进入编辑态，先自动保存前一张卡片 |
| `saveNote(item)` | async fn | 调用 PATCH，本地更新，防重入 |
| `cancelEditNote()` | fn | Escape 取消，清零状态 |
| `onNoteKeydown(e, item)` | fn | Enter 保存 / Shift+Enter 换行 / Escape 取消 |

---

---

## Phase P1-a — 技术面图表可视化前端专项测试（2026-05-30）

> **验证方法说明**：本章所有"✅"项均为**代码路径审查 + `npm run build` 构建验证**，**尚未执行真实浏览器点击测试**。浏览器验证项标注为"⬜"，可在后续日常使用中继续补充。不含真实浏览器人工点击测试；核心路径已通过代码审查与构建验证；真实浏览器点击验证可在后续日常使用中自然补充。

### P1-a.1 TechnicalChartPanel.vue 组件验收

| # | 检查项 | 验证方式 | 结论 | 状态 |
|---|--------|---------|------|------|
| 1 | `props.market / symbol / visible / height` 定义完整 | 代码审查 | `defineProps` 含 required + default | ✅ |
| 2 | `initChart()` 使用 v4 API：`createChart / addCandlestickSeries / addHistogramSeries / addLineSeries` | 代码审查 | 无 v5 `addSeries(Type, opts)` 写法 | ✅ |
| 3 | `ColorType.Solid / CrosshairMode.Normal` 来自 named import | 代码审查 | `import { createChart, CrosshairMode, ColorType } from 'lightweight-charts'` | ✅ |
| 4 | volume histogram 使用 `priceScaleId: ''` overlay，`scaleMargins: { top: 0.78, bottom: 0 }` | 代码审查 | 主图底部 25% 留给成交量，两者共存一个 chart 实例 | ✅ |
| 5 | MA5/10/20/60 各为独立 `addLineSeries()`，颜色各异 | 代码审查 | C.ma5(蓝) / C.ma10(琥珀) / C.ma20(红) / C.ma60(紫) | ✅ |
| 6 | `Number.isFinite(open/high/low/close)` 校验，不用 `!bar.open` | 代码审查 | 避免 0.0 被误判为无效 bar | ✅ |
| 7 | `volume = bar.volume`，不依赖 `bar.amount` | 代码审查 | 注释：Tencent fallback 下 `amount=null` | ✅ |
| 8 | `calcMA` 只输出 `period-1` 之后的点，无 null 填充 | 代码审查 | `for (let i = period - 1; i < closes.length; i++)` | ✅ |
| 9 | `normalizeDate("20240115")` → `"2024-01-15"` | 代码审查 | `s.length === 8 && !s.includes('-')` 分支 | ✅ |
| 10 | `normalizeDate("2024-01-15")` → 原样返回 | 代码审查 | 不满足 8 位无`-`条件，直接 `return s` | ✅ |
| 11 | loading overlay / error overlay / empty overlay 三态 | 代码审查 | `v-if="loading"` / `v-else-if="error"` / `v-else-if="bars.length===0"` | ✅ |
| 12 | stale badge：`v-if="stale"` 显示"缓存数据" | 代码审查 | `tag--warn` 橙色样式，来自 `res.stale` | ✅ |
| 13 | `volume_unit` → `volumeLabel` computed，"手"/"股"切换 | 代码审查 | `computed(() => volumeUnit.value==='lot' ? '成交量（手）' : '成交量（股）')` | ✅ |

### P1-a.2 getKline API 封装验收

| # | 检查项 | 验证方式 | 结论 | 状态 |
|---|--------|---------|------|------|
| 1 | 文件 `frontend/src/api/stocks.js` 存在 | 文件检查 | 已创建 | ✅ |
| 2 | `getKline(market, symbol, options)` 签名正确 | 代码审查 | 默认 `period='daily', adjust='qfq', limit=120` | ✅ |
| 3 | 调用路径 `/stocks/${market}/${symbol.trim()}/kline?${params}` | 代码审查 | `symbol.trim()` 保留前导零，不 parseInt | ✅ |
| 4 | 使用 `baseFetch`（自动注入 Bearer token） | 代码审查 | `import { baseFetch } from './http.js'` | ✅ |
| 5 | `URLSearchParams` 构建 query string，`limit` 转 `String()` | 代码审查 | 避免数字类型序列化异常 | ✅ |

### P1-a.3 ComprehensiveAnalysisView 接入验收

| # | 检查项 | 验证方式 | 结论 | 状态 |
|---|--------|---------|------|------|
| 1 | `TechnicalChartPanel` import 已添加 | 代码审查 | `import TechnicalChartPanel from '../components/TechnicalChartPanel.vue'` | ✅ |
| 2 | 位置：`<template v-if="result">` 首行，报告 card 之前 | 代码审查 | 顺序：TechnicalChartPanel → 报告 card → SectionAccordion → save-bar | ✅ |
| 3 | `:market="result.market" :symbol="result.symbol"` 绑定 | 代码审查 | 从已有 `result` 对象取值，无新 state | ✅ |
| 4 | `:visible="true"` 显式传入（组件在 `v-if="result"` 内，始终可见） | 代码审查 | 父已做 `v-if="result"` 保护 | ✅ |
| 5 | `:height="340"` | 代码审查 | 图表高度 340px | ✅ |
| 6 | 不在 `SectionAccordion` 内部 | 代码审查 | TechnicalChartPanel 在 SectionAccordion 外、报告 card 外 | ✅ |

### P1-a.4 生命周期 / keep-alive / 内存管理验收

| # | 检查项 | 验证方式 | 结论 | 状态 |
|---|--------|---------|------|------|
| 1 | `onMounted` 顺序：`initChart()` → `ResizeObserver` 注册 → `fetchKline()` | 代码审查 | chart 先初始化再 fetch，保证 `updateChart` 时 series 已存在 | ✅ |
| 2 | `ResizeObserver` 监听 `containerRef`，`width > 0` 时 `chart.applyOptions({ width })` | 代码审查 | 防止 clientWidth=0 时创建零宽图表 | ✅ |
| 3 | `onActivated` → `chart.applyOptions({ width: clientWidth })` | 代码审查 | keep-alive 返回后修正宽度 | ✅ |
| 4 | `onUnmounted` → `ro?.disconnect()` + `chart?.remove()` + 所有引用置 `null` | 代码审查 | 6 个引用全部置 null（chart / candleSeries / volSeries / ma5S / ma10S / ma20S / ma60S） | ✅ |
| 5 | `watch([market, symbol])` `immediate: false`，不与 `onMounted` 重复 fetch | 代码审查 | `[newM, newS] !== [oldM, oldS]` 才触发 | ✅ |
| 6 | `initChart()` 幂等守卫 `if (!containerRef.value \|\| chart) return` | 代码审查 | 防止多次初始化 | ✅ |

### P1-a.5 Error / Loading / Stale 状态验收

| # | 检查项 | 验证方式 | 结论 | 状态 |
|---|--------|---------|------|------|
| 1 | `fetchKline()` 进入时 `loading=true, error=''` | 代码审查 | 每次调用前重置状态 | ✅ |
| 2 | `catch` 只写 `error.value`，不向上 throw | 代码审查 | kline 失败不影响父组件（综合报告仍正常渲染） | ✅ |
| 3 | 错误 overlay 有"重新加载"按钮 → `@click="fetchKline"` | 代码审查 | 可手动重试，不刷新页面 | ✅ |
| 4 | `loading` 时显示 loading overlay，`v-if` 优先级最高 | 代码审查 | `v-if="loading"` → `v-else-if="error"` → `v-else-if 空数据"` | ✅ |
| 5 | `stale=true` 时 header badge `tag--warn` 显示 | 代码审查 | 来自 `res.stale`，橙色 badge | ✅ |

### P1-a.6 API 级验证（2026-05-30 执行，服务器运行中直接测试）

| # | 验证操作 | 实测结果 | 状态 |
|---|---------|---------|------|
| 1 | CN/600519 kline — 数量 | 120 bars，date 2025-11-27 → 2026-05-29 | ✅ |
| 2 | CN/600519 — volume_unit | `"lot"` | ✅ |
| 3 | CN/600519 — OHLC 全 finite，dates 升序无重复 | 120/120 通过 | ✅ |
| 4 | HK/700 kline — 数量 | 120 bars | ✅ |
| 5 | HK/700 — volume_unit | `"share"` | ✅ |
| 6 | CN/000001 kline — 前导零路径 | 请求 `/stocks/CN/000001/kline`，返回 120 bars | ✅ |
| 7 | CN/1（无前导零）| 返回 0 bars — 确认前导零不可省略 | ✅ |
| 8 | Redis 缓存命中（第二次调用）| `"cached":true`，响应 < 10ms | ✅ |
| 9 | 无效标的 kline 错误隔离 | HTTP 200 + `data:[]`（图表显示空 overlay，不抛 exception） | ✅ |
| 10 | MA5 输出条数 | 116 bars（120 - 4 = 116，与 calcMA 逻辑一致） | ✅ |

### P1-a.7 浏览器视觉验证清单（需人工执行 ⬜）

> 以下项涉及 Canvas 渲染、交互事件、Console 观察，需在真实浏览器中人工确认。

| # | 验证项 | 预期行为 |
|---|--------|---------|
| 1 | CN/600519 图表出现位置 | StockInputPanel 正下方，综合报告 card 正上方 | ⬜ |
| 2 | K线形态 | 约 120 根蜡烛，红跌绿涨，最右为最近交易日 | ⬜ |
| 3 | MA 颜色 | MA5 蓝 / MA10 琥珀 / MA20 红 / MA60 紫，图例与图表一致 | ⬜ |
| 4 | 成交量图位置 | 图表下方 ~22% 区域，涨日绿色半透明、跌日红色半透明 | ⬜ |
| 5 | HK/700 图例 | 显示"成交量（股）" | ⬜ |
| 6 | Watchlist → 分析 | 图表切换为新标的，旧图不残留 | ⬜ |
| 7 | 历史报告 → 返回 | 图表宽度正常，不变形（keep-alive onActivated） | ⬜ |
| 8 | kline 失败 | 图表 card 显示红色错误文字 + "重新加载"按钮，报告正常 | ⬜ |
| 9 | Console | 无红色 error，无 lightweight-charts warning | ⬜ |
| 10 | 窗口缩放 | 图表自适应宽度（ResizeObserver），不溢出 | ⬜ |

---

## Phase P1-a.1 — 历史报告详情页图表 + AppHeader 修复专项测试

**测试日期：** 2026-05-30（代码审查 + build 验证）  
**浏览器验证：** 尚待执行（标注 ⬜）

### P1-a.1.1 HistoryDetailView 图表接入

| # | 审查项 | 预期 | 状态 |
|---|--------|------|------|
| 1 | `TechnicalChartPanel` import 路径 | `../components/TechnicalChartPanel.vue`，无 typo | ✅ |
| 2 | 组件在 `<template v-if="result">` 内部 | result 为 null 时不渲染，不触发 fetchKline | ✅ |
| 3 | 图表在主报告 card 之前 | 模板顺序：TechnicalChartPanel → `<div class="card">` → AgentStatusBar | ✅ |
| 4 | `:market="result.market"` / `:symbol="result.symbol"` | 与历史报告标的一致 | ✅ |
| 5 | `:visible="true"` `:height="340"` | 固定参数，与综合分析页一致 | ✅ |
| 6 | 不新增 state 变量 | 复用 TechnicalChartPanel 内部 loading/error/stale，HistoryDetailView 无变化 | ✅ |
| 7 | 图表失败不影响报告正文 | `fetchKline` 内部 catch，从不 throw 到父组件 | ✅ |
| 8 | AgentStatusBar / WarningPanel / MarkdownReport 不受影响 | 图表为独立节点，无状态耦合 | ✅ |

### P1-a.1.2 AppHeader displayName 修复

| # | 审查项 | 预期 | 状态 |
|---|--------|------|------|
| 1 | `computed` 从 vue 正确导入 | `import { computed } from 'vue'` | ✅ |
| 2 | `displayName` 优先级：username → email → '用户' | 三层 if/return 顺序 | ✅ |
| 3 | 过滤 `username === 'string'` | 测试账号不再显示 `string` | ✅ |
| 4 | 过滤 `email === 'string'` | email 值同样做防御性检查 | ✅ |
| 5 | 模板使用 `{{ displayName }}` | 不再直接展开 `authStore.currentUser` 对象 | ✅ |

### P1-a.1.3 构建验证

| 项目 | 结果 |
|------|------|
| 模块数 | 84（与 Phase P1-a 一致，TechnicalChartPanel 在主 bundle 共享）|
| exit code | 0 |
| unresolved import | 无 |
| Vue warn | 无（代码审查层面） |
| HistoryDetailView lazy chunk | 2.33 kB（无异常增长） |

### P1-a.1.4 API 级验证（2026-05-30 执行）

| # | 验证项 | 实测结果 | 状态 |
|---|--------|---------|------|
| 1 | `getReport()` 返回 `result.market` | `"CN"` / `"HK"`，正确来自 DB | ✅ |
| 2 | `getReport()` 返回 `result.symbol` | `"600519"` / `"700"` / `"000001"`，前导零保留 | ✅ |
| 3 | CN/000001 symbol 持久化 | DB 存储值 `"000001"`，`getReport()` 取出值正确 | ✅ |
| 4 | kline URL 推导 | `result.market + result.symbol` → `/stocks/CN/000001/kline` 路径正确 | ✅ |
| 5 | displayName 4 场景（Python 模拟） | username/email/string/null 全部 fallback 正确 | ✅ |
| 6 | HK/700 历史报告 → kline | `/stocks/HK/700/kline` → 120 bars, volume_unit=share | ✅ |

### P1-a.1.5 浏览器视觉验证（需人工执行 ⬜）

> 以下项需要在真实浏览器中验证。

| # | 验证项 | 预期行为 |
|---|--------|---------|
| 1 | /history/:id 顶部布局 | 返回按钮 → 图表卡片 → 主报告 card | ⬜ |
| 2 | 图表标签 | 左上显示 `{market}/{symbol}`、日线、前复权 | ⬜ |
| 3 | CN/600519 K线视觉 | 约 120 根蜡烛，MA5/10/20/60 叠加 | ⬜ |
| 4 | HK/700 成交量图例 | 显示"成交量（股）" | ⬜ |
| 5 | kline 失败隔离 | 图表 card 内错误提示，报告正文不受影响 | ⬜ |
| 6 | 综合分析页回归 | ComprehensiveAnalysisView 图表不受影响 | ⬜ |
| 7 | AppHeader 用户名 | 不显示 `string`；显示真实 username 或 email 或"用户" | ⬜ |
| 8 | Console | 无红色 JS error，无 Vue warn | ⬜ |

---

## Phase P1-b — 行业热门股前端展示专项测试（2026-05-30）

### P1-b.1 新增文件

| 文件 | 说明 |
|------|------|
| `frontend/src/api/industries.js` | 行业接口封装：getDynamicPeers / getStockIndustry / getIndustryHotStocks |
| `frontend/src/components/IndustryHotStocksPanel.vue` | 行业热门股面板（~250 行，含模板/脚本/样式） |

### P1-b.2 代码审查

| 验证项 | 状态 |
|--------|------|
| `industries.js`：`symbol.trim()` 保留前导零 | ✅ |
| `IndustryHotStocksPanel`：`market !== 'CN'` 短路不发请求 | ✅ |
| `IndustryHotStocksPanel`：watch `[market, symbol, visible]`，`immediate: true` | ✅ |
| `IndustryHotStocksPanel`：`peerSource` 驱动四态 UI（dynamic_hot / manual_map / none / unsupported） | ✅ |
| `IndustryHotStocksPanel`：`goAnalyze` → `router.push({ path: '/', query: { market, symbol } })` | ✅ |
| `IndustryHotStocksPanel`：`formatAmount` 转亿/万，`formatChangePct` 带正负号，`changePctClass` 红绿 | ✅ |
| `ComprehensiveAnalysisView`：import 正确，面板在 TechnicalChartPanel 之后、.card 之前 | ✅ |
| `HistoryDetailView`：import 正确，面板在 TechnicalChartPanel 之后、.card 之前 | ✅ |
| disclaimer 文案存在（Hot Score 说明） | ✅ |

### P1-b.3 构建验证

| 项目 | 结果 |
|------|------|
| 模块数 | 87（P1-a.1 的 84 + industries.js + IndustryHotStocksPanel + chunk 更新） |
| exit code | 0 |
| unresolved import | 无 |

### P1-b.4 API 级验证（2026-05-30 执行）

| # | 验证项 | 实测结果 | 状态 |
|---|--------|---------|------|
| 1 | CN/000001 peer_source | `dynamic_hot` | ✅ |
| 2 | CN/000001 industry_name | `银行` | ✅ |
| 3 | CN/000001 peers | 5 只（601318 / 600000 / 601939 / 600036 / 601166），Hot Score 递减 | ✅ |
| 4 | HK/700 peer_source | `manual_map` | ✅ |
| 5 | HK/700 peers | `['9988', '3690', '9999', '9888']` | ✅ |
| 6 | CN/300750 peer_source | `dynamic_hot` | ✅ |
| 7 | CN/300750 industry_name | `电力设备` | ✅ |
| 8 | CN/300750 peers | 4 只（300750 自身排除），最高 Hot Score 0.717（阳光电源） | ✅ |

### P1-b.5 浏览器视觉验证（需人工执行 ⬜）

| # | 验证项 | 预期行为 |
|---|--------|---------|
| 1 | 综合分析 CN/000001 → 结果出现后 | "行业热门股"面板出现在图表下方、报告上方；source badge"动态热门" |
| 2 | 面板表格内容 | 5 行：rank / 股票名+代码 / Hot Score（3位小数）/ 成交额（亿）/ 涨跌幅（红绿色） / "分析"按钮 |
| 3 | 点击"分析"按钮 | 跳转 `/?market=CN&symbol=601318`，触发新分析 |
| 4 | 综合分析 HK/700 | 面板显示港股不支持提示文案，无表格 |
| 5 | 历史报告详情 CN/000001 | 面板同样出现，位置在图表与报告之间 |
| 6 | 加载状态 | 请求期间显示 spinner + "加载行业热门股…" |
| 7 | Console | 无红色 JS error，无 Vue warn |

---

## Phase P1-c — 信息架构优化专项测试（2026-05-30）

### P1-c.1 新增 / 修改文件

| 文件 | 变更 |
|------|------|
| `frontend/src/components/AnalysisResultLayout.vue` | 新建 |
| `frontend/src/views/ComprehensiveAnalysisView.vue` | 内容区重构为 AnalysisResultLayout |
| `frontend/src/views/HistoryDetailView.vue` | 内容区重构为 AnalysisResultLayout |

### P1-c.2 代码审查

| 验证项 | 状态 |
|--------|------|
| AnalysisResultLayout：sticky action bar（position:sticky; top:0; z-index:50） | ✅ |
| 4 个 anchor pill（图表/行业/综合/分项）→ scrollIntoView({ behavior:'smooth', block:'start' }) | ✅ |
| 4 个 section id（rl-chart / rl-industry / rl-report / rl-sections）| ✅ |
| scroll-margin-top:60px 防止 sticky bar 遮挡 section 顶部 | ✅ |
| #actions named slot 在 anchor 右侧 | ✅ |
| ComprehensiveAnalysisView：save status + DownloadMenu + 保存按钮 → #actions slot | ✅ |
| HistoryDetailView：时间戳 + DownloadMenu + 删除按钮 → #actions slot | ✅ |
| result.metadata?.warnings 可选链（替代旧写法 result.metadata.warnings） | ✅ |
| result.metadata?.agents 可选链 | ✅ |
| mobile ≤540px：action bar flex-direction:column | ✅ |
| mobile：anchors overflow-x:auto，scrollbar-width:none 隐藏滚动条 | ✅ |
| detail-footer CSS 已从 HistoryDetailView 清理 | ✅ |
| save-bar CSS 已从 ComprehensiveAnalysisView 清理 | ✅ |

### P1-c.3 构建验证

| 项目 | 结果 |
|------|------|
| 模块数 | 89 |
| exit code | 0 |
| HistoryDetailView chunk | 1.81 kB（P1-b: 2.42 kB，减小正确） |
| ComprehensiveAnalysisView chunk | 主 bundle（keep-alive 静态 import，符合预期） |
| unresolved import | 无 |

### P1-c.4 浏览器视觉验证（需人工执行 ⬜）

| # | 验证项 | 预期行为 |
|---|--------|---------|
| 1 | 分析完成后 action bar | anchor pill × 4 + 「下载」「保存报告」按钮在同一行 |
| 2 | action bar sticky | 向下滚动后固定在视口顶部 |
| 3 | anchor 点击 | 平滑滚动，section 标题不被 sticky bar 遮挡 |
| 4 | section-label 样式 | 每 section 顶部小号大写灰色标签 |
| 5 | 保存后 action bar | 「✓ 已保存 查看」+ 「已保存」(disabled) 按钮 |
| 6 | HistoryDetailView action bar | 时间戳 + 下载 + 删除报告 |
| 7 | DownloadMenu 下拉 z-index | 不被 sticky bar 遮挡，正常展示 |
| 8 | 删除流程 | ConfirmDialog 弹出正常，删除后跳转列表 |
| 9 | 移动端（≤540px） | action bar 换行，anchor 横向滚动，无溢出 |
| 10 | Console | 无红色 JS error，无 Vue warn |

---

## 附录：关键文件位置

| 文件 | 说明 |
|------|------|
| `frontend/index.legacy.html` | 原单文件 MVP（已备份，勿删除） |
| `frontend/src/main.js` | 工程入口：createApp + Pinia + Router |
| `frontend/src/App.vue` | 根组件：auth 状态决定显示 LoginCard 或 RouterView |
| `frontend/src/router/index.js` | vue-router 4；含 beforeEach 守卫（Phase 2A） |
| `frontend/src/api/http.js` | 所有需鉴权请求的基础层（401 auto-logout，204 No Content 支持，signal 透传） |
| `frontend/src/api/analysis.js` | 综合分析 API 封装（Phase 2D 新增 options.signal 透传） |
| `frontend/src/api/reports.js` | 报告历史 CRUD 封装（含字段映射：report_md ↔ report） |
| `frontend/src/stores/auth.js` | Pinia auth store |
| `frontend/src/utils/warningMap.js` | WARNING_MAP / SECTION_DEFS / EXAMPLES / badgeClass() |
| `frontend/src/utils/markdown.js` | marked.parse + DOMPurify.sanitize |
| `frontend/src/utils/exportMarkdown.js` | buildReportMarkdown / buildFilename / downloadMarkdown（Phase 2B） |
| `frontend/src/styles/markdown.css` | 必须全局引入，v-html 内容不受 scoped 约束 |
| `frontend/src/components/ConfirmDialog.vue` | 自定义确认对话框，Teleport to body（Phase 2A） |
| `frontend/src/views/HistoryView.vue` | 历史报告列表页（`/history`）；Phase W1 新增 `route.query` 预填筛选 |
| `frontend/src/views/HistoryDetailView.vue` | 历史报告详情页（`/history/:id`） |
| `frontend/src/views/WatchlistView.vue` | 自选股页面（`/watchlist`）；Phase W1 新增 |
| `frontend/src/api/watchlist.js` | 自选股 CRUD API 封装；Phase W1 新增 |
| `frontend/src/components/StockInputPanel.vue` | 综合分析输入面板；Phase W1 新增 `initialMarket/initialSymbol` props + watch |
| `frontend/.env.example` | 提交到 git；`.env` 在 `.gitignore` 中 |
| `frontend/src/api/industries.js` | 行业接口封装（getDynamicPeers / getStockIndustry / getIndustryHotStocks）；Phase P1-b 新增 |
| `frontend/src/components/IndustryHotStocksPanel.vue` | 行业热门股面板（dynamic_hot 表格 / manual_map chip / unsupported 提示）；Phase P1-b 新增 |
| `frontend/src/components/AnalysisResultLayout.vue` | 分析结果统一布局：sticky action bar + 4 section + #actions slot；Phase P1-c 新增 |

---

## Phase P2 — 移动端响应式 CSS 修复

**日期：** 2026-05-31  
**类型：** 纯 CSS 改动，无业务逻辑变更

### P2.1 修复项

| 文件 | 断点 | 修复内容 |
|------|------|---------|
| `AppHeader.vue` | 480px | flex-wrap + nav order:3 + username text-overflow ellipsis |
| `AnalysisResultLayout.vue` | 540px（已有） | 补充 `scroll-margin-top: 92px`（双行 sticky bar 适配） |
| `DownloadMenu.vue` | 540px | `right:auto; left:0`（防左溢出） |
| `WatchlistView.vue` | 480px | row-actions 两列网格 + 输入框全宽 + 按钮全宽 |
| `HistoryView.vue` | 480px | filter-bar column 布局 + 输入框全宽 |
| `StockInputPanel.vue` | 540px（已有） | 补充 `.submit-group .btn { width: 100% }` |
| `base.css` | — | 断点约定注释（480px / 540px 说明） |

### P2.2 build + 编译产物验证结果

```
✓ 89 modules transformed — exit 0 — ~570ms（×2 轮 build）
✓ 全部 6 个 CSS chunk brace balanced
✓ 移动端 @media 块内无非法固定宽度（扫描确认）
```

### P2.3 编译产物 CSS 规则确认（代码级 ✅）

| # | 规则 | 文件 | 结果 |
|---|------|------|------|
| P2-1 | AppHeader flex-wrap + order:3 + ellipsis | index-*.css @media 480px | ✅ |
| P2-3 | scroll-margin-top:92px | index-*.css @media 540px | ✅ |
| P2-4 | dl-list right:auto; left:0 | index-*.css @media 540px | ✅ |
| P2-5 | row-actions flex:1 1 calc(50%) | WatchlistView-*.css @media 480px | ✅ |
| P2-6 | symbol/name-input width:100% | WatchlistView-*.css @media 480px | ✅ |
| P2-7 | filter-bar column + stretch + min-width:0 | HistoryView-*.css @media 480px | ✅ |
| P2-8 | submit-group .btn width:100% | index-*.css @media 540px | ✅ |

**改动性质：** 纯 CSS `<style scoped>` @media 规则。零 template/script 变动。

### P2.4 DevTools 设备仿真（⬜ 待人工确认）

| # | 验证项 | 宽度 | 状态 |
|---|--------|------|------|
| V-1 | AppHeader 实际渲染：nav 在第二行，无横向 scrollbar | 375px | ⬜ |
| V-2 | 用户名超长时省略号可见，"退出"可点击 | 390px | ⬜ |
| V-3 | Sticky anchor 跳转 section 标题不被遮挡 | 375px | ⬜ |
| V-4 | DownloadMenu 从左向右展开 | 375px | ⬜ |
| V-5 | Watchlist 4 按钮 2×2 网格，无横向滚动 | 375px | ⬜ |
| V-6 | Watchlist 添加表单全宽 | 375px | ⬜ |
| V-7 | HistoryView filter 全宽 | 375px | ⬜ |
| V-8 | StockInputPanel 按钮全宽 | 375px | ⬜ |
| V-9 | HistoryDetailView 与主分析页行为一致 | 375px | ⬜ |
| V-10 | Console 无 Vue warn / JS error | 375px | ⬜ |
| V-11 | 三宽度无 body 级横向滚动 | 375/390/430px | ⬜ |

---

## Phase P3 / P3.1 — 行业热门股独立页面验证

**日期：** P3 2026-05-31；P3.1（bug fix + 代码级验证）2026-06-01  
**build（P3.1 后）：** exit 0 ✅ | IndustryHotView-*.css 3.91 kB | IndustryHotView-*.js 6.11 kB

### P3.1 Bug Fix 说明

| Bug | 根因 | 修复 |
|-----|------|------|
| 交易日/版本号不显示 | `hotData.data_quality?.trade_date/score_version` 不存在——字段在 `HotStockResponse` 顶层，非 `HotStockDataQuality` 内 | 改为 `hotData.trade_date` / `hotData.score_version` |

### P3.2 代码级验证（自动化，2026-06-01）

| 类别 | 验证项 | 方式 | 状态 |
|------|--------|------|------|
| 路由 | `/industries` 路由已注册 | 编译产物 | ✅ |
| 路由 | auth guard `protectedPrefixes` 含 `/industries` | 编译产物 | ✅ |
| API | `listIndustries` → `GET /industries/?market=CN` | 编译产物 URL 检索 | ✅ |
| API | `getIndustryHotStocks` URL `hot-stocks` 正确 | 编译产物 | ✅ |
| API | `addWatchlist`（非 `addWatchlistItem`）import | 源码 + 编译 | ✅ |
| 字段 | `hotData.trade_date` 顶层（bug fix） | 编译产物 `c.value.trade_date` | ✅ |
| 字段 | `data_quality.trade_date` 错误路径已移除 | regex absent | ✅ |
| 字段 | `hotData.score_version` 顶层 | 编译产物 | ✅ |
| 行为 | `goAnalyze` path `'/'` + query `{symbol,market}` | 源码审查 | ✅ |
| 行为 | `goHistory` path `'/history'` + query | 源码审查 | ✅ |
| 行为 | `watchlistStatus` reactive，切换行业 `delete` 清空 | 源码审查 | ✅ |
| 行为 | 409 通过 `e.status === 409` 检测 | 源码 + `baseFetch` | ✅ |
| 行为 | `ComprehensiveAnalysisView` `watch(route.query)` 响应 query 变化 | 源码审查 | ✅ |
| CSS | `.hot-cards` 默认 `display:none` | 编译 CSS | ✅ |
| CSS | `@media 480px` `.hot-cards display:block` | 编译 CSS | ✅ |
| CSS | `@media 480px` `.hot-table-wrap display:none` | 编译 CSS | ✅ |
| CSS | `industry-select width:100%` at 480px | 编译 CSS | ✅ |
| CSS | `ctrl-row flex-direction:column` at 480px | 编译 CSS | ✅ |
| CSS | `hot-table-wrap overflow-x:auto` | 编译 CSS | ✅ |

### P3.3 浏览器验证（⬜ 待人工执行）

> 需在真实浏览器 DevTools 设备仿真下执行，无法自动化。

| # | 验证项 | 宽度 | 状态 |
|---|--------|------|------|
| A-1 | `/industries` 正常加载，行业下拉填充 ≥10 项 | 1440px | ⬜ |
| A-2 | 默认选中 PREFERRED_NAMES 之一 | 1440px | ⬜ |
| A-3 | 桌面 table 显示排名/代码/名称/热度分/成交额/涨跌幅 | 1440px | ⬜ |
| A-4 | 交易日 + 版本号显示在控制行（非空） | 1440px | ⬜ |
| A-5 | 切换行业重新加载，watchlistStatus 清空 | 1440px | ⬜ |
| A-6 | 「分析」跳转综合分析页且 symbol/market 预填 | 1440px | ⬜ |
| A-7 | 「历史」跳转历史页且 symbol/market 过滤 | 1440px | ⬜ |
| A-8 | 「自选」点击后变为「已加入」，再次点击不重复请求 | 1440px | ⬜ |
| A-9 | 重复股票 409 → 按钮显示「已存在」 | 1440px | ⬜ |
| A-10 | 375px：table 隐藏，cards 显示 | 375px | ⬜ |
| A-11 | 375px：行业选择器全宽 | 375px | ⬜ |
| A-12 | 375px：三按钮无横向溢出 | 375px | ⬜ |
| A-13 | 375px：AppHeader 四导航项无 body 横向滚动 | 375px | ⬜ |
| A-14 | 未登录访问 `/industries` 重定向 `/` | — | ⬜ |
| A-15 | AppHeader「行业」链接激活高亮 | — | ⬜ |
| A-16 | 数据为空时显示「该行业暂无热门股数据」 | — | ⬜ |
| A-17 | Console 无 Vue warn / JS error | — | ⬜ |

---

## Phase P4-a — 股票搜索 / 代码联想

**日期：** 2026-06-01  
**build：** exit 0 ✅ | 93 modules | index-*.css 21.62 kB

### P4-a.1 后端 curl 验证（已通过）

| # | 测试用例 | 期望 | 状态 |
|---|---------|------|------|
| B-1 | `q=600519` | `total=1, name=贵州茅台` | ✅ |
| B-2 | `q=茅台` | `total=1, symbol=600519` | ✅ |
| B-3 | `q=`（空） | `total=0, items=[]` | ✅ |
| B-4 | `q=XXXXNOTEXIST` | `total=0, items=[]` | ✅ |
| B-5 | `market=HK` | `items=[], message=港股暂不支持` | ✅ |
| B-6 | `q=6005` prefix | 10 只不同 symbol | ✅ |
| B-7 | 无 token | HTTP 401 | ✅ |
| B-8 | `limit=20` | count=20，不超限 | ✅ |

### P4-a.2 编译产物验证（已通过）

| 检查项 | 状态 |
|--------|------|
| `/stocks/search` URL | ✅ |
| StockSearchBox（ssb-dropdown/ssb-input） | ✅ |
| debounce 300ms | ✅ |
| `addEventListener` click-outside | ✅ |
| `removeEventListener` cleanup | ✅ |
| ArrowDown / Escape 键盘 | ✅ |
| `select` emit | ✅ |
| `v-model:symbol` defineModel | ✅ |
| WatchlistView onSelect 设 name | ✅ |
| Enter `stopPropagation()` 在 StockSearchBox keydown | ✅ |
| StockInputPanel `withKeys(submit,["enter"])` | ✅ |
| WatchlistView `withKeys(handleAdd,["enter"])` | ✅ |

### P4-a.3 浏览器验证（✅ Playwright headless 验证通过，2026-06-01）

**方式：** Playwright 1.58.0 + Chromium headless，1440px + 375px 双视口，15/15 通过

| # | 验证项 | 宽度 | 状态 |
|---|--------|------|------|
| F-1 | 输入"茅台"，300ms 后 dropdown 显示 600519 贵州茅台 食品饮料 | 1440px | ✅ |
| F-2 | 点击结果后 symbol 填入，dropdown 关闭 | 1440px | ✅ |
| F-3 | 点击页面其他区域 dropdown 关闭 | 1440px | ✅ |
| F-4 | Esc 键关闭 dropdown | 1440px | ✅ |
| F-5 | 清空 q 后 dropdown 关闭，无请求 | 1440px | ✅ |
| F-6 | 快速示例 chip 点击后 StockSearchBox 显示 symbol | 1440px | ✅ |
| F-7 | Watchlist「分析」跳转后 StockSearchBox 显示 initialSymbol | 1440px | ✅ |
| F-8 | ↑↓/Enter 键盘导航选中结果 | 1440px | ✅ |
| F-9 | Watchlist 搜索选择后 symbol + name 自动填充 | 1440px | ✅ |
| F-10 | Watchlist 手动输入代码（不选结果）直接添加 | 1440px | ✅ |
| F-11 | market=HK 不发请求，placeholder 改变 | 1440px | ✅ |
| F-12 | 无结果显示"未找到 xxx，可直接输入代码" | 1440px | ✅ |
| F-13 | 375px dropdown 全宽，无横向溢出（right_edge=334px） | 375px | ✅ |
| F-14 | 375px 输入框全宽（width=293px，卡片内有效宽≈295px） | 375px | ✅ |
| F-15 | Console 无 Vue warn / JS error | — | ✅ |

---

## Phase P4-b — HistoryView 搜索联想接入

**日期：** 2026-06-01  
**build：** exit 0 ✅ | 93 modules（共享 bundle 不变）| HistoryView 4.25 kB

### P4-b.1 变更

| 文件 | 改动 |
|------|------|
| `frontend/src/views/HistoryView.vue` | 引入 StockSearchBox；替换 symbol filter-input；`:market="filterMarket \|\| 'CN'"`；`@select` + `@keydown.enter="loadReports"`；CSS `.ssb-group` |

### P4-b.2 浏览器验证（✅ Playwright headless，2026-06-01）

**方式：** 1440px + 375px，10/10 通过

| # | 验证项 | 宽度 | 状态 |
|---|--------|------|------|
| H-1 | /history 列表正常加载，filter bar + SSB 存在 | 1440px | ✅ |
| H-2 | "茅台" → dropdown 显示 600519 贵州茅台 | 1440px | ✅ |
| H-3 | 点击结果 → filterSymbol='600519'，dropdown 关闭 | 1440px | ✅ |
| H-4 | 点击查询 → GET /reports?symbol=600519 | 1440px | ✅ |
| H-5 | ?market=CN&symbol=000001 → SSB 显示 '000001' | 1440px | ✅ |
| H-6 | 直接输入 + Enter → 历史查询触发 | 1440px | ✅ |
| H-7 | HK → placeholder 变，无 search 请求 | 1440px | ✅ |
| H-8 | 375px dropdown right_edge=334px，无溢出 | 375px | ✅ |
| H-9 | Console 无 Vue warn / JS error | — | ✅ |
| H-10 | Watchlist + 综合分析页 SSB 零退化 | 1440px | ✅ |

---

## Phase P4-c — IndustryHotView 快速搜索接入

**日期：** 2026-06-01  
**build：** exit 0 ✅ | 93 modules（共享 bundle 不变）| IndustryHotView chunk 零增量

### P4-c.1 变更

| 文件 | 改动 |
|------|------|
| `frontend/src/views/IndustryHotView.vue` | 引入 StockSearchBox；control card 新增 `.quick-search-row`；`@select="goAnalyzeSelected"` 选中跳转；"分析"按钮 `goAnalyzeQuick` 手动跳转；`market="CN"` 固定（行业页仅 A 股）；移动端 flex-direction: column |

### P4-c.2 浏览器验证（✅ Playwright headless，2026-06-01）

**方式：** 1440px + 375px，10/10 通过

| # | 验证项 | 宽度 | 状态 |
|---|--------|------|------|
| I-1 | /industries 正常加载，行业 dropdown + 快速搜索标签全部存在 | 1440px | ✅ |
| I-2 | 行业 dropdown 切换，热门股功能不受影响 | 1440px | ✅ |
| I-3 | 输入"茅台" → dropdown 显示 600519 贵州茅台 | 1440px | ✅ |
| I-4 | 点击结果 → 跳转 `/?market=CN&symbol=600519` | 1440px | ✅ |
| I-5 | 手动输入 000001 + 分析 → 跳转 `/?market=CN&symbol=000001` | 1440px | ✅ |
| I-6 | 跳转后综合分析页 SSB 显示 '000001' | 1440px | ✅ |
| I-7 | 热门股列表"分析"按钮跳转正常，不受影响 | 1440px | ✅ |
| I-8 | 375px dropdown right_edge=334px ≤ 380px，无溢出 | 375px | ✅ |
| I-9 | Console 无 Vue warn / JS error | — | ✅ |
| I-10 | Watchlist + HistoryView + 综合分析页 SSB 零退化 | 1440px | ✅ |

### P4-c.3 阶段汇总

| 子阶段 | 功能 | 验证通过 |
|--------|------|----------|
| P4-a | StockSearchBox 组件 + 综合分析页 + Watchlist 接入 | 15/15 ✅ |
| P4-b | HistoryView filter bar SSB 接入 | 10/10 ✅ |
| P4-c | IndustryHotView 快速搜索接入 | 10/10 ✅ |
| **P4 合计** | **全站 SSB 覆盖（4 个视图）** | **35/35 ✅** |

---

## Phase P5-a — stock_master 后端数据层升级（2026-06-01）

**范围：** 纯后端，零前端改动

### P5-a.1 变更（后端）

| 文件 | 操作 |
|------|------|
| `backend/app/models/stock_master.py` | 新建 — StockMaster ORM；UNIQUE(market,symbol)；3 个索引 |
| `backend/alembic/versions/…add_stock_master.py` | 新建 — CREATE TABLE + indexes；down_revision=4b49004d01a6 |
| `backend/scripts/import_stock_master.py` | 新建 — 回填脚本；支持 --dry-run；ON CONFLICT DO UPDATE 幂等 |
| `backend/app/services/industry_classification_service.py` | 修改 — search_stocks 双路径 + fallback |
| `backend/app/routers/stocks.py` | 修改 — data_quality.source 动态化 |

### P5-a.2 关键验证结果

| 验证项 | 结果 |
|--------|------|
| alembic upgrade head | 76fe066db8b1 (head) ✅ |
| stock_master 行数 | 5166 ✅ |
| dry-run 预览 | to_upsert=5166, skipped=0 ✅ |
| 幂等（重复导入行数不变） | ✅ |
| /stocks/search source="stock_master" | ✅ |
| industry_code/name LEFT JOIN 补全 | ✅ |
| HK 短路不受影响 | ✅ |
| 401 鉴权不受影响 | ✅ |
| npm run build | exit 0 ✅（前端零变化） |
| Playwright 回归 10/10 | ✅ |

### P5-a.3 前端零影响声明

- `StockSearchBox.vue`：零改动
- `StockInputPanel.vue` / `WatchlistView.vue` / `HistoryView.vue` / `IndustryHotView.vue`：零改动
- `GET /stocks/search` 请求参数、响应结构（`StockSearchItem` 6 字段）：完全向后兼容
- `data_quality.source` 字段前端不显示，从 `stock_industry_map` → `stock_master` 对 UI 零影响

### P5-a.4 四页面搜索入口回归验证（✅ Playwright headless Chromium，2026-06-01）

复用 P4-c 验证脚本（I-1~I-10），后端升级后全部通过

| 页面 | 搜索入口 | 验证结果 |
|------|---------|---------|
| 综合分析页（`/`） | `StockInputPanel` 内 StockSearchBox | 输入"600"，dropdown 正常出现，无重复 symbol ✅ |
| Watchlist（`/watchlist`） | 添加表单 StockSearchBox | 搜索选中后 symbol + name 自动填充 ✅ |
| HistoryView（`/history`） | filter bar StockSearchBox | 搜索正常触发，market=HK 禁搜正常 ✅ |
| IndustryHotView（`/industries`）| 快速搜索区块 StockSearchBox | 选中结果跳转 `/?market=CN&symbol=` 正常 ✅ |

**数据来源验证：** `/stocks/search` API `data_quality.source` = `"stock_master"`，前端 UI 行为与 P4 阶段完全一致。

---

## P5-b — 港股 stock_master 导入与 HK 搜索支持（2026-06-01）

### P5-b.1 功能范围

在 P5-a `stock_master` 基础上，全面开放港股搜索能力：

- 导入 30 只港股到 `stock_master`（5 位补零格式）
- HK 数字查询双 ILIKE（`700` 自动扩展为 `700% OR 00700%`）
- `StockSearchBox.vue` 移除 HK 禁用守卫，四页面全支持 HK 搜索
- PEER_MAP 统一 5 位 HK 格式，`_normalize_symbol` 向后兼容

### P5-b.2 StockSearchBox 改动（最小化）

```diff
// StockSearchBox.vue
- if (props.market === 'HK') return '港股暂不支持搜索，请直接输入代码'
+ if (props.market === 'HK') return props.placeholder ?? '输入港股代码或名称'

- if (q.trim().length < 1 || props.market === 'HK') {
+ if (q.trim().length < 1) {
```

### P5-b.3 Playwright 验证（✅ 9/9，2026-06-01）

| # | 测试 | 结果 |
|---|------|------|
| B-1 | 分析页 HK 搜索 '腾讯' → 00700 腾讯控股 | ✅ |
| B-2 | 分析页 HK 搜索 '700' → 00700（短格式扩展匹配） | ✅ |
| B-3 | 点击下拉 → input='00700' | ✅ |
| B-4 | `/?market=HK&symbol=00700` → URL 正确，SSB='00700' | ✅ |
| B-5 | Watchlist HK 搜 '腾讯' → symbol='00700' | ✅ |
| B-6 | HistoryView 切换 HK，搜 '00700' → dropdown 出现 | ✅ |
| B-7 | CN 搜索全页面零退化（4 页面） | ✅ |
| B-8 | 375px 移动端 HK dropdown 不溢出 | ✅ |
| B-9 | Console 无 JS error / Vue warning | ✅ |

### P5-b.4 后端变更摘要

| 文件 | 变更 |
|------|------|
| `data/stock_master/hk_stocks.csv` | 30 只 HK 股，5 位格式 |
| `scripts/import_stock_master.py` | `--csv --market HK` 模式，`normalize_hk_symbol` |
| `IndustryClassificationService._build_symbol_filter` | HK 数字双 ILIKE |
| `stocks.py` search route | 移除 HK 短路，`data_quality.message=None` |
| `peer_comparison_service.py` | PEER_MAP 5 位格式，`_normalize_symbol` |

---

## P6-b — 报告可信度增强 + UI Bug 修复（2026-06-02）

### P6-b.1 P6-0 Bug Fix：IndustryHotStocksPanel sourceLabel

**问题根因：**

```js
// 旧代码（plain object — v-if 永远 true，{{ }} 序列化为 JSON 字符串）
const sourceLabel = { dynamic_hot: '动态热门', ... }

// 修复后（computed）
const sourceLabel = computed(() => SOURCE_LABEL_MAP[peerSource.value] ?? '')
```

`sourceBadgeClass` 同理修复。模板中 `v-if="sourceLabel"` 在空字符串时自然隐藏 badge。

### P6-b.2 UI-2：anchor bar 文字双语方案

```html
<button class="anchor-btn">
  <span class="anchor-full">技术图表</span>
  <span class="anchor-short">图表</span>
</button>
```

```css
.anchor-short { display: none; }

@media (max-width: 480px) {
  .anchor-full  { display: none; }
  .anchor-short { display: inline; }
}
```

桌面端：技术图表 / 行业热股 / 综合报告 / 分项分析  
移动端：图表 / 行业 / 综合 / 分项

### P6-b.3 stock_name 注入链路

```
后端 analyze_async
  └── _fetch_stock_name(db, market, symbol)
        └── industry_classification_service.search_stocks(limit=3)
              → 精确匹配 → stock_name: str | None
  → stock_identity = "平安银行（CN/000001）" | "CN/000001"（fallback）
  → _build_synthesis_prompt(..., stock_identity)  ← user prompt 含明确指令
  → _SYSTEM_PROMPT 含「标题与身份声明规则」
  → result["stock_name"] = stock_name or ""
  → ComprehensiveAnalysisResponse.stock_name: str = ""

前端 result.stock_name
  → AnalysisResultLayout：技术走势标题旁副标
  → IndustryHotStocksPanel：副标题 stockName prop
  → HistoryDetailView：back-title 显示完整名称
```

### P6-b.4 向后兼容性

- `ComprehensiveAnalysisResponse.stock_name` 默认 `""` → 旧客户端安全忽略
- 旧历史报告 result 无 `stock_name` → 前端 `result.stock_name || ''` fallback
- 数据库无变更，无 migration

### P6-b.5 build 验证

```
npm run build → exit 0 ✅，93 modules
```

### P6-b.6 浏览器验证（✅ Playwright headless，2026-06-02）

脚本：`/tmp/verify_p6b_v2.py`

| 检查点 | 实测结果 |
|--------|---------|
| F-1：badge 无 JSON leak，显示「动态热门」 | ✅ |
| F-2：桌面端 anchor-full 正确（技术图表/行业热股/综合报告/分项分析） | ✅ |
| F-3：移动端 375px anchor-short 显示、anchor-full 隐藏 | ✅ |
| F-4：`section-label-sub` = `CN/000001`（无 undefined/null） | ✅ |
| F-5：`industry-subtitle` = `CN/000001  ·  申万一级：银行` | ✅ |
| F-6：back-title = `CN/000001`（DB 无 stock_name，fallback 正确） | ✅ |
| F-6b：Markdown 正文含「平安银行（CN/000001）」 | ✅ |
| F-7：旧报告 HK/700 back-title = `HK/700`，无 undefined/null | ✅ |

---

## P6-a — DiscoveryPanel 发现面板（2026-06-02）

### P6-a.1 新组件：DiscoveryPanel.vue

```
frontend/src/components/DiscoveryPanel.vue
```

双 tab 设计：

**推荐搜索 tab**
```html
<button class="pick-chip" @click="emit('pick', { market, symbol })">
  <span class="chip-market">CN</span>
  <span class="chip-sym">600519</span>
  <span class="chip-name">贵州茅台</span>
</button>
```

**行业热门 tab**
- 懒加载：首次切换到 tab 时触发 `loadIndustries()`
- 默认行业：`list.find(i => i.industry_name.includes('食品饮料')) || list[0]`
- 每行热股：rank / 名称 / symbol / 涨跌幅 / 分析按钮
- 移动端：flex column 布局，不强制宽表格

**折叠逻辑：** emit `pick` 事件，不自动提交；父组件处理填入

### P6-a.2 StockInputPanel.vue 新增 fill()

```js
function fill(market, symbol) {
  form.market = market
  form.symbol = symbol
}
defineExpose({ fill })
```

父组件通过 `ref` 调用：`stockInputRef.value?.fill(market, symbol)`

### P6-a.3 ComprehensiveAnalysisView.vue 集成

```js
const stockInputRef = ref(null)
const discoveryOpen = ref(true)

function handlePick({ market, symbol }) {
  stockInputRef.value?.fill(market, symbol)
}

watch(result, (val) => {
  if (val !== null) discoveryOpen.value = false
})
```

```html
<StockInputPanel ref="stockInputRef" ... />
<div v-if="result && !discoveryOpen" class="discovery-toggle">
  <button @click="discoveryOpen = true">＋ 展开发现面板</button>
</div>
<DiscoveryPanel v-if="!result || discoveryOpen" @pick="handlePick" />
```

### P6-a.4 build 验证

```
npm run build → exit 0 ✅，95 modules（+2 vs P6-b 的 93）
```

### P6-a.5 浏览器交互验证（✅ Playwright headless，2026-06-02）

脚本：`/tmp/verify_p6a.py`

| 检查点 | 实测结果 |
|--------|---------|
| 初始加载：`.discovery-panel` 渲染，默认「推荐搜索」tab 激活 | ✅ |
| 5 个 chips：600519 / 000001 / 300750 / 00700 / 09988 | ✅ |
| CN chip 点击 → market=CN，symbol 正确；HK/00700 → symbol=00700 | ✅ |
| 所有 chip 点击：不触发自动分析 | ✅ |
| 行业热门 tab：默认「食品饮料」，5 行热股 | ✅ |
| 行业切换（银行）→ 热股列表刷新，loading 状态正常 | ✅ |
| 热股「分析」按钮：URL 不变，form 填入，不自动分析 | ✅ |
| 初始状态：panel 可见，无 toggle 按钮；有 result 时 toggle 出现 | ✅（结构验证） |
| 375px：无 body 横向溢出，chips-wrap 无溢出 | ✅ |
| 390px：无横向溢出 | ✅ |
| Vue warnings：0；JS errors：0 | ✅ |
| 回归：/history / /watchlist / /industries 正常 | ✅ |

---

## P6-c — StockIdentityCard 分析前确认卡片（2026-06-02）

### P6-c.1 新组件：StockIdentityCard.vue

```
frontend/src/components/StockIdentityCard.vue
```

**展示逻辑：**

```
v-if="currentSymbol.trim() && !loading"   ← 父组件控制显隐
内部：
  v-if="loading"    → spinner + market/symbol
  v-else            → sic-content
    v-if="identity"           → name + (market/symbol) + industry + badges
    v-else                    → fallback + 暂未匹配 hint
    v-if="market === 'HK'"   → HK note
```

**Stale response 防护（generation counter）：**

```js
let fetchGen = 0

async function doFetch() {
  const gen = ++fetchGen
  ...
  const data = await searchStocks(mkt, sym, { limit: 3 })
  if (gen !== fetchGen) return   // 丢弃过期响应
  ...
  if (gen === fetchGen) loading.value = false
}
```

保证快速切换股票时旧 fetch 的结果不会覆盖新状态。

**Debounce 400ms：** 避免逐字触发搜索。

### P6-c.2 StockInputPanel.vue — change emit

```js
const emit = defineEmits(['analyze', 'change'])

watch([() => form.market, () => form.symbol], ([market, symbol]) => {
  emit('change', { market, symbol })
})
```

覆盖：用户手动输入、选择下拉、填入例子 chip、`fill()` 调用均触发 change。

### P6-c.3 ComprehensiveAnalysisView.vue — 集成

```js
const currentMarket = ref(route.query.market || 'CN')
const currentSymbol = ref(route.query.symbol || '')

function handleFormChange({ market, symbol }) {
  currentMarket.value = market
  currentSymbol.value = symbol
}
```

```html
<StockInputPanel ... @change="handleFormChange" />

<StockIdentityCard
  v-if="currentSymbol.trim() && !loading"
  :market="currentMarket"
  :symbol="currentSymbol.trim()"
/>
```

### P6-c.4 build 验证

```
npm run build → exit 0 ✅，97 modules（+2 vs P6-a 的 95）
```

### P6-c.5 浏览器验证（✅ Playwright headless，2026-06-02）

| 检查点 | 实测结果 |
|--------|---------|
| 初始无 symbol → .sic-card 不显示 | ✅ |
| chip 点击 → .sic-card 立即出现（loading skeleton） | ✅ |
| CN/000001：无 undefined/null，4 个 badges | ✅ |
| HK/00700：港股同行对比 badge，港股行业分类 note | ✅ |
| 不存在代码 ZZZZZ：fallback + 暂未匹配 hint | ✅ |
| 清空 symbol → .sic-card 消失 | ✅ |
| 375px：无 body 溢出，.sic-card 宽度适配 | ✅ |
| DiscoveryPanel 共存正常 | ✅ |
| /history /watchlist /industries 回归 | ✅ |
| Vue warnings：0 | ✅ |

---

## P6-d：报告可信度与可读性增强（2026-06-02）

### P6-d.1 _SYSTEM_PROMPT 修改

**新增第二章：**

```markdown
## 二、数据来源与覆盖范围
- 技术面：数据来源及时间窗口
- 基本面：已获取字段范围；不全时说明哪类字段缺失
- 同行对比：手动配置 PEER_MAP，样本数量
- 新闻面：来源及时间窗口；无新闻时说明
- 字段缺失总结：未覆盖的关键字段（若有）
```

**章节编号：** 一 → 二（新增）→ 三 → 四 → 五 → 风险提示

**过强措辞禁止列表（新增明确映射）：**

| 禁止表达 | 替换为 |
|---------|--------|
| 明确利好 | 可能对市场情绪有正面影响（仍需后续数据验证） |
| 明确利空 | 可能对市场情绪有负面影响（仍需后续数据验证） |
| 必然上涨/下跌 | 在当前可用数据范围内存在一定[上行/下行]压力 |
| 确定性机会/风险 | 在当前样本范围内存在潜在机会/风险，仍需后续验证 |
| 强烈建议买入/卖出 | （完全禁止） |

**数据缺失表达：**
- 禁止：公司没有 PE/PB，PE 为零
- 必须：当前数据源未返回 {字段名}，因此无法在本报告中展开

### P6-d.2 _fallback_report 修改

更新为 5 章结构：
- 一、核心摘要（首句含 stock_identity）
- 二、数据来源与覆盖范围（固定条目）
- 三、多维度整合观察（子模块状态列表）
- 四、主要数据局限
- 五、后续观察要点

### P6-d.3 AnalysisResultLayout.vue — report-identity-bar

在 `<hr class="divider" />` 与 `<MarkdownReport>` 之间插入：
- 有 `result.stock_name`：完整名称（market/symbol）
- 无：仅 market/symbol
- 右侧 rib-badges：HK 自动显示「港股同行对比」
- CSS：flex-wrap，mobile rib-badges 换行

### P6-d.4 build 验证

```
npm run build → exit 0 ✅，97 modules
Python AST parse → syntax OK ✅
```

---

## P6-e：分析过程可视化（2026-06-02）

### P6-e.1 新增组件：AnalysisProgressPanel.vue

**Props：**
- `market`: String
- `symbol`: String
- `stockName`: String (default '')
- `startedAt`: Number (Date.now() at analysis start)
- `loading`: Boolean

**内部时间驱动：**
```js
const STEPS = [
  { label: '确认分析对象',        minSec: 0  },
  { label: '获取行情与技术指标',   minSec: 3  },
  { label: '获取基本面数据',       minSec: 8  },
  { label: '匹配同行样本',         minSec: 15 },
  { label: '检索近期新闻',         minSec: 25 },
  { label: '生成综合报告',         minSec: 40 },
]
```

- `currentStepIndex` = 最后一个 `elapsed >= minSec` 的步骤下标
- `progressPct` = 5% + (currentStepIndex / 5) × 90%，transition: width 0.8s
- ≥40s：显示「大模型正在整合多维度信息」慢速提示
- emit('cancel') → 取消分析

**步骤 CSS 状态：**
- done（i < current）：✓ 绿色，label 灰色
- active（i === current）：spinner + accent，label 加粗
- pending（i > current）：· 灰色，label 半透明

### P6-e.2 StockIdentityCard.vue — identity emit

```js
emit('identity', match?.name || '')   // fetch 完成后
emit('identity', '')                   // symbol 清空 / fetch 失败
```

父组件通过 `@identity="handleIdentity"` 接收，存入 `currentStockName`。

### P6-e.3 ComprehensiveAnalysisView.vue 修改点

新增状态：
```js
const analysisStartedAt = ref(null)
const currentStockName  = ref('')
```

`handleAnalyze` 开始时：`analysisStartedAt.value = Date.now()`

模板替换：
```html
<!-- 旧 -->
<LoadingPanel v-if="loading" :elapsed-seconds="..." ... />

<!-- 新 -->
<AnalysisProgressPanel
  v-if="loading"
  :market="currentMarket"
  :symbol="currentSymbol.trim()"
  :stock-name="currentStockName"
  :started-at="analysisStartedAt"
  :loading="loading"
  @cancel="cancelAnalysis"
/>
<ErrorBox :message="errorMsg" />
<p v-if="errorMsg" class="error-retry-hint">
  分析未完成，可能是上游数据源或大模型接口暂时不可用。请稍后重试，或更换股票代码。
</p>
```

### P6-e.4 LoadingPanel 保留情况

LoadingPanel.vue 保留，未删除，未修改。AnalysisProgressPanel 仅用于综合分析页主等待流程。

### P6-e.5 build 验证

```
npm run build → exit 0 ✅，97 modules
CSS: 28.15 kB → 29.73 kB（+1.58 kB）
JS:  371.64 kB → 373.33 kB（+1.69 kB）
```

### P6-e.1 浏览器验证（✅ Playwright headless，2026-06-02）

| 检查点 | 实测结果 |
|--------|---------|
| ProgressPanel 出现（点击生成后立即显示） | ✅ |
| 显示股票标识（CN/000001） | ✅ |
| 6 个步骤正确渲染 | ✅ |
| t=0：步骤 0「确认分析对象」active | ✅ |
| t≥3s：步骤 1「获取行情与技术指标」active | ✅ |
| t≥8s：步骤 2「获取基本面数据」active | ✅ |
| 慢速提示 DOM 存在（≥40s 触发） | ✅ |
| 取消按钮 → panel 消失，无白屏 | ✅ |
| 分析完成 → panel 消失，result-layout 出现 | ✅ |
| `.report-markdown` + `.report-identity-bar` DOM 确认 | ✅ |
| HK/00700 → panel 显示 HK，无 CN 名称残留 | ✅ |
| Watchlist 跳转分析正常 | ✅ |
| 375px 无 body 溢出，.app-panel 适配，取消按钮可点击 | ✅ |
| Vue warnings：0 | ✅ |

**report-identity-bar 实测文本：** `当前报告对象：CN/000001 | 技术图表 | 基本面 | 同行对比 | 新闻信息`

---

## P6-e.2：422 清理（2026-06-02）

### 根因

`StockIdentityCard.vue` 调用：
```js
const data = await searchStocks(mkt, sym, { limit: 3 })
```

`stocks.js` 函数签名：
```js
export function searchStocks(market, q, limit = 10) {
  const params = new URLSearchParams({ market, q, limit: String(limit) })
  ...
}
```

第三个参数应为数字，但传入了对象 `{ limit: 3 }`，`String()` 序列化为 `"[object Object]"` → 后端 `limit: int (ge=1, le=20)` 验证失败 → HTTP 422。

### 修复（1 行）

`StockIdentityCard.vue:95`
```diff
- const data = await searchStocks(mkt, sym, { limit: 3 })
+ const data = await searchStocks(mkt, sym, 3)
```

### build 验证

```
npm run build → exit 0 ✅，97 modules
```

### 回归验证（Playwright headless，2026-06-02）

R-1~R-8 全部通过。Network 422 count = 0，Console errors = 0 ✅

---

## P6-f：失败状态与空状态体验增强（2026-06-02）

### P6-f.1 EmptyState.vue（新建）

```
Props: title(required), message, icon(default ℹ️), actionText, compact
Emits: action
```

用法示例：
```html
<EmptyState
  icon="🌏"
  title="当前市场暂不支持行业热门股"
  message="港股暂不使用申万行业体系..."
  action-text="重试"
  :compact="true"
  @action="retryFn"
/>
```

### P6-f.2 TechnicalChartPanel.vue 增强

- 空 overlay (data=[]): 新增 `.chart-overlay--empty` — 标题/说明文案/retry button
- stale tag: 增加 title hover 文案

### P6-f.3 IndustryHotStocksPanel.vue 增强

- `unsupported` → EmptyState (HK 专属说明)
- `none/empty` → EmptyState + `noneMessage` computed（含 fallbackReason）
- import EmptyState

### P6-f.4 DiscoveryPanel.vue 增强

- 独立 `indError` ref（行业列表加载失败独立显示）
- `hotError` → EmptyState + 重新加载按钮
- `items=[]` → EmptyState + 重新加载按钮
- `retryIndustries()` function + `indLoaded = false` reset

### P6-f.5 build 验证

```
npm run build → exit 0 ✅，99 modules（+2 vs 97）
```

### P6-f.6 浏览器验证（Playwright headless，2026-06-02）

| 检查点 | 结果 |
|--------|------|
| DiscoveryPanel industry tab 加载正常 | ✅ |
| Hot stocks 列表渲染正常 | ✅ |
| HK report-identity-bar「港股同行对比」badge | ✅ |
| HK IndustryHotStocksPanel EmptyState 渲染 | ✅ |
| EmptyState 375px 无溢出 | ✅ |
| EmptyState 完整渲染（图标/标题/说明/按钮） | ✅ |
| Network 422 = 0 | ✅ |
| Vue warnings = 0，JS errors = 0 | ✅ |

---

## P7 — 数据完整度评分（DataQualitySummary）

### P7.1 组件

`frontend/src/components/DataQualitySummary.vue`

纯前端计算，不新增 API。从 `result.sections`、`result.metadata.agents`、`result.metadata.warnings`、`result.report` 推导四维度评分（0-100 整数）。

### P7.2 接入位置

`AnalysisResultLayout.vue` 中 `report-identity-bar` 下方、`MarkdownReport` 上方。

### P7.3 评分逻辑

- 技术面：基础 85，健康+5→90，stale/cache -15，missing/failed=0
- 基本面：基础 70，HK -15，字段缺失 -20，PE/PB缺失 -10，missing/failed=0
- 同行对比：基础 70，none/unsupported=30，HK max(40,-20)，手动映射 -15
- 新闻面：基础 70，暂无新闻=40，failed=20，关键词搜索 -10

### P7.4 build / 浏览器验证（2026-06-02）

| 检查点 | 结果 |
|--------|------|
| .dqs-wrap 存在 | ✅ |
| 综合评分 + 四维度 chip 渲染 | ✅ |
| 展开/收起 detail 正常 | ✅ |
| 375px 无溢出 | ✅ |
| build exit 0，101 modules | ✅ |

---

## P8 — 研究操作闭环（ResearchActionPanel）

### P8.1 组件

`frontend/src/components/ResearchActionPanel.vue`

Props: `result`, `saved`, `saving` | Emits: `save`, `reanalyze`

内部自治：`addWatchlist` API 调用、`navigator.clipboard` 复制、`router.push` 历史导航。

### P8.2 接入位置

`AnalysisResultLayout.vue` 中 DataQualitySummary 下方、MarkdownReport 上方。  
`AnalysisResultLayout` 新增 `saved`/`saving` props 和 `save`/`reanalyze` emits。  
`ComprehensiveAnalysisView` 传入 `:saved`/`:saving` 并处理 `@save`/`@reanalyze`。

### P8.3 按钮行为

| 按钮 | 实现方式 |
|------|---------|
| 保存报告 | emit('save')，父组件 handleSave |
| 加入自选 | 组件内 addWatchlist API，409→已在自选 |
| 查看历史 | router.push('/history?market=&symbol=') |
| 复制摘要 | extractSummary(result.report)，navigator.clipboard + execCommand fallback |
| 重新分析 | emit('reanalyze')，父组件 handleAnalyze(market, symbol) |

### P8.4 build / 浏览器验证（2026-06-02）

| 检查点 | 结果 |
|--------|------|
| .rap-wrap 存在 | ✅ |
| 5 个操作按钮渲染 | ✅ |
| 加入自选 API 调用（409 → 已在自选） | ✅ |
| 原底部 save-bar 无回归 | ✅ |
| 375px 无溢出（grid 2列布局） | ✅ |
| build exit 0，103 modules | ✅ |
| Network 422 = 0，Vue warnings = 0 | ✅ |

---

## P9 — 报告导出与分享体验增强

### P9.1 工具模块

`frontend/src/utils/reportText.js` — 共享文本提取与复制工具：
- `extractSummary(md)`: 截取核心摘要段落
- `buildReportIdentity(result)`: 构建显示标题
- `buildShareText(result)`: 构建适合消息发送的短格式文本（去 markdown，≤800 字）
- `copyText(text)`: clipboard API + execCommand fallback

### P9.2 DownloadMenu 扩展

原有"Markdown (.md)"和"打印/导出 PDF"保留。新增分隔线后三个复制选项：
- 复制完整报告（`buildReportMarkdown` + `copyText`）
- 复制核心摘要（`extractSummary` + `buildReportIdentity`）
- 复制分享文本（`buildShareText`）

状态反馈：2 秒后重置，失败显示"复制失败"。

### P9.3 PrintReportView 优化

- 文档标题：`printTitle` computed = `buildReportIdentity(result) + ' 综合分析报告'`
- `document.title` 含股票名称（有 stock_name 时）
- 无 stock_name 时 fallback market/symbol，无 undefined/null

### P9.4 ResearchActionPanel 更新

复制摘要改用 `reportText.js` 的 `extractSummary`/`buildReportIdentity`/`copyText`，删除内联重复逻辑。

### P9.5 build / 浏览器验证（2026-06-02）

| 检查点 | 结果 |
|--------|------|
| 新增三个复制选项渲染 | ✅ |
| 打印页标题无 undefined/null | ✅ |
| 375px DownloadMenu 无溢出 | ✅ |
| P8 ResearchActionPanel 无回归 | ✅ |
| build exit 0，104 modules | ✅ |

---

## P10 — 产品级首页与信息架构收敛

### P10.1 HomeHeroPanel

`frontend/src/components/HomeHeroPanel.vue` — 纯展示组件，无 props/logic。

条件：`v-if="!result && !loading"` — loading 开始或结果出现时自动隐藏，结果清空后自动恢复。

结构：标题 + 副标题 + 能力 chips（5个）+ 操作提示。移动端：标题缩小至 17px，chips 缩小并换行。

### P10.2 DiscoveryPanel 文案

| 变更点 | 旧 | 新 |
|--------|----|----|
| 推荐搜索 tab | 推荐搜索 | 快速开始 |
| 行业热门 tab | 行业热门 | 行业机会 |
| 快速开始说明 | 点击快速填入分析表单，不会自动提交 | 选择常用标的，先填入输入框，确认后再生成分析 |
| 行业机会说明 | 点击"分析"只填入表单，不自动提交 | 从申万行业热门股中发现可研究标的 |

业务逻辑（点击只填表不提交）未变更。

### P10.3 build / 浏览器验证（2026-06-02）

| 检查点 | 结果 |
|--------|------|
| hero-wrap 初始显示 | ✅ |
| 标题「AI 股票研究工作台」 | ✅ |
| 5 个能力 chips | ✅ |
| tab 文案「快速开始/行业机会」 | ✅ |
| 375px 无溢出 | ✅ |
| build exit 0，105 modules | ✅ |
| Network 422 = 0，Vue warnings = 0 | ✅ |

---

## P11 — 视觉统一与作品集包装

### P11.1 AboutProductPanel

`frontend/src/components/AboutProductPanel.vue` — 可折叠产品说明面板。

条件：`v-if="!result && !loading"`，出现在 DiscoveryPanel 之后。

默认收起，点击「了解系统能力」展开内容：项目简介 + 核心能力列表 + 数据边界 + 风险免责声明。桌面两列 grid，移动单列。

### P11.2 视觉统一

`base.css .card-title`：15px/600 → 16px/700，margin-bottom 18px → 16px。全局生效，所有使用 `.card-title` 的组件（TechnicalChartPanel、IndustryHotStocksPanel 等）自动受益。

### P11.3 作品集文档

| 文档 | 内容 |
|------|------|
| `docs/demo_walkthrough.md` | 3/5 分钟 Demo 路径、面试重点、常见 QA |
| `docs/project_readme_draft.md` | 项目简介、功能、技术栈、架构亮点、运行方式、限制、后续计划 |

### P11.4 build / 浏览器验证（2026-06-02）

| 检查点 | 结果 |
|--------|------|
| AboutProductPanel 初始显示，默认收起 | ✅ |
| 展开/收起功能正常 | ✅ |
| 页面层级 hero < input < discovery < about | ✅ |
| card-title 16px/700 | ✅ |
| 375px 无溢出 | ✅ |
| build exit 0，106 modules | ✅ |
| Network 422 = 0，Vue warnings = 0 | ✅ |

---

## Phase M2 — StockDetailView 股票详情页（2026-06-04）

### M2 新增/修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `frontend/src/views/StockDetailView.vue` | 新增 | 股票详情页主视图 |
| `frontend/src/router/index.js` | 修改 | 新增 /stocks/:market/:symbol 路由 |
| `frontend/src/api/stocks.js` | 修改 | 新增 getStockQuote / getStockNews |
| `frontend/src/api/reports.js` | 修改 | createReport 传入 stock_name；getReport 返回 stock_name |
| `frontend/src/views/WatchlistView.vue` | 修改 | 新增"详情"按钮 + goDetail() |
| `frontend/src/views/IndustryHotView.vue` | 修改 | 新增"详情"按钮 + goDetail() |
| `frontend/src/components/IndustryHotStocksPanel.vue` | 修改 | 新增"详情"按钮 + goDetail() |
| `backend/app/models/analysis_report.py` | 修改 | stock_name 字段（ORM + 4 个 Schema） |
| `backend/app/routers/reports.py` | 修改 | create_report + list_reports 支持 stock_name |
| `backend/alembic/versions/2026_06_04_0001-3a2f8b4c1d9e_...py` | 新增 | ALTER TABLE analysis_reports ADD COLUMN stock_name |
| `backend/scripts/refresh_industry_hot_stocks.py` | 修改 | 每行业独立 session，修复 duplicate bug |

### M2 组件复用情况

| 组件 | 复用方式 |
|------|---------|
| TechnicalChartPanel | 直接复用，传 :market :symbol :height=300 |
| DataQualitySummary | 复用，在 latestFullReport 加载后显示 |
| EmptyState | 6 处复用（新闻/分析/历史/热门股/HK unsupported/无行业） |
| AppHeader | 直接复用 |

### M2 数据获取方案

StockDetailView 使用前端 Promise.all 并发 5 个独立请求，无聚合接口：
1. searchStocks → stock_name
2. getStockQuote → price / change_pct
3. getStockNews → 新闻列表（hours_back=72）
4. listReports → 历史报告 + latest
5. getStockIndustry + getIndustryHotStocks → 行业信息 + 热门股

latestFullReport 在 listReports 完成后顺序加载（非阻塞其他区块）。

### M2 Build 结果

| 项目 | 结果 |
|------|------|
| npm run build | ✅ exit 0，110 modules |
| python -m compileall app -q | ✅ |
| alembic upgrade head | ✅ 3a2f8b4c1d9e (head) |
| Playwright 24/24 | ✅ |

---

## Phase M4-a — analysis_scope 分析模式选择（2026-06-04）

**目标：** 6 种 analysis_scope、AnalysisModeSelector、动态 ProgressPanel、scope-aware SectionAccordion/DataQualitySummary/AnalysisResultLayout/HistoryView/HistoryDetailView/StockDetailView。

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase M4-a | analysis_scope v2 API + AnalysisModeSelector + 6 scope 完整前端链路 | ✅ 已完成 |
| Phase M4-a.1 | analysis_scope 全链路回归验证 + PrintReportView/exportMarkdown/extractSummary scope 修复 | ✅ 已完成 |

### M4-a 新增 / 修改文件

| 文件 | 说明 |
|------|------|
| `frontend/src/api/analysis.js` | 新增 `runComprehensiveAnalysisV2()` |
| `frontend/src/api/reports.js` | createReport/getReport 传 analysis_scope |
| `frontend/src/components/AnalysisModeSelector.vue` | 新增：6 mode chip 选择器，3 列 grid |
| `frontend/src/views/ComprehensiveAnalysisView.vue` | 接入 v2 API + AnalysisModeSelector |
| `frontend/src/components/AnalysisProgressPanel.vue` | STEPS 按 scope 动态计算，panelTitle scope-aware |
| `frontend/src/components/AnalysisResultLayout.vue` | 锚点 scope-aware，activeBadges 动态 |
| `frontend/src/components/SectionAccordion.vue` | visibleSections 过滤 skipped |
| `frontend/src/components/DataQualitySummary.vue` | DIMS computed 过滤 skipped，overall 仅平均非 skipped |
| `frontend/src/views/HistoryView.vue` | scope badge（blue/gray）|
| `frontend/src/views/HistoryDetailView.vue` | scope badge in actions bar |
| `frontend/src/views/StockDetailView.vue` | report-type-badge → scopeLabel |
| `frontend/src/views/PrintReportView.vue` | scope-aware printTitle + 报告节标题 |
| `frontend/src/utils/exportMarkdown.js` | scope-aware 标题 |
| `frontend/src/utils/reportText.js` | extractSummary 增加 "二、核心结论" 路径 |

### M4-a Build 结果

| 项目 | 结果 |
|------|------|
| npm run build | ✅ exit 0，115 modules |
| python -m compileall app -q | ✅ |
| alembic current | ✅ b4d8e2f1a6c9 (head) |

---

## Phase M4-b.1 — LangGraph POC 验证（2026-06-04）

**目标：** 独立验证 LangGraph 1.2.0 编排结构，不接入 FastAPI，不修改前端代码。

| 项目 | 结果 |
|------|------|
| LangGraph 版本 | 1.2.0 |
| fan-out 方案 | Send API + conditional_edges |
| fan-in 方案 | collect_node |
| sections reducer | Annotated[dict, merge_dict] |
| 测试用例 T-1~T-8 | ✅ 8/8 PASS |
| npm run build（未修改前端）| ✅ 115 modules |
| py_compile POC 脚本 | ✅ |
| 修改 app/ 代码 | 否 |

**结论：** LangGraph 编排结构验证通过，建议进入 M4-b.2（接入真实 Agent，不改 FastAPI）。

---

## Phase M4-b.2 — LangGraph 真实 Agent 接入验证（2026-06-04）

**目标：** 在 M4-b.1 POC 基础上，将 mock Agent 替换为真实 Agent，验证 LangGraph 编排与 FastAPI 生产路由完全隔离的情况下能否稳定接入真实 Technical / Fundamental / Peer / News 四个 Agent。

| 项目 | 结果 |
|------|------|
| LangGraph 版本 | 1.2.0 |
| 使用真实 Agent | 是（4 个真实 Agent 类） |
| 调用真实 LLM synthesis | 否（轻量 Markdown 拼接） |
| DB session 注入 | AsyncSessionLocal + config["configurable"]["db"] |
| RunnableConfig fix | config 类型从 dict → RunnableConfig（langchain_core.runnables） |
| 测试 R-1~R-6 | ✅ 5/5 PASS（R-5 跳过） |
| py_compile 静态检查 | ✅ |
| compileall app -q | ✅ |
| 修改 app/ 代码 | 否 |
| 修改前端 | 否 |
| npm run build | 未运行（前端无修改） |

**结论：** 真实 Agent 成功接入 LangGraph 节点，db session 注入正常，Agent 失败不导致图崩溃。建议进入 M4-b.3（真实 synthesis LLM 接入）。

---

## Phase M4-b.3 — LangGraph 真实 synthesis LLM 接入验证（2026-06-04）

**目标：** synthesis_node 接入真实 synthesis LLM，验证 LangGraph 全链路输出与 custom_coordinator 结构兼容。

| 项目 | 结果 |
|------|------|
| LangGraph 版本 | 1.2.0 |
| 真实 Agent | 是（4 个真实 Agent 类） |
| 真实 synthesis LLM | 是（comprehensive/technical_fundamental） |
| synthesis_llm 注入 | config["configurable"]["synthesis_llm"]（与 agent llm 分离） |
| CountingLLMWrapper | synthesis_llm_calls：S-1=0, S-2=1（验证单 Agent scope 不调 synthesis LLM） |
| FakeFailingLLM 故障注入 | errors["synthesis"] 写入 state，fallback_report 正常生成 |
| 测试 S-1~S-5 | ✅ 4/4 PASS（S-3 跳过） |
| py_compile 静态检查 | ✅ |
| compileall app -q | ✅ |
| 修改 app/ 代码 | 否 |
| 修改前端 | 否 |
| npm run build | 未运行（前端无修改） |

**结论：** synthesis_node 真实 LLM 接入验证通过，建议进入 M4-b.4（FastAPI engine=langgraph 灰度）。

---

## Phase M4-b.4 — FastAPI engine=langgraph 灰度接入（2026-06-04）

**目标：** 在 `/analysis/comprehensive-v2` 路由新增 `engine` 字段，`engine="langgraph"` 触发 LangGraph 路径，默认 `engine="custom_coordinator"` 不变，前端无需修改。

| 项目 | 结果 |
|------|------|
| 新增文件 | `backend/app/agents/langgraph_analysis_graph.py` |
| 修改文件 | `backend/app/routers/analysis.py` |
| engine 默认值 | `"custom_coordinator"`（前端无感知） |
| engine=langgraph 路径 | LangGraphAnalysisRunner.analyze() |
| 响应结构兼容性 | ComprehensiveV2Response(**result) 直接适配 |
| Literal 类型验证 | 非法 engine 值 → HTTP 422 |
| API 测试 A-1~A-7 | ✅ 7/7 PASS |
| py_compile 静态检查 | ✅ |
| compileall app -q | ✅ |
| 修改前端 | 否 |
| npm run build | 未运行（前端无修改） |

### API 测试结果

| 测试 | 场景 | 结果 |
|------|------|------|
| A-1 | 默认 engine（无 engine 字段）→ custom_coordinator 路径 | ✅ PASS |
| A-2 | engine=langgraph + technical_only scope | ✅ PASS |
| A-3 | engine=langgraph + technical_fundamental scope | ✅ PASS |
| A-4 | engine=langgraph + news_only scope | ✅ PASS |
| A-5 | engine=bad_engine → HTTP 422 | ✅ PASS |
| A-6 | engine=langgraph + invalid_scope → HTTP 422 | ✅ PASS |
| A-7 | GET /analysis/comprehensive（旧接口）回归 → 200 OK | ✅ PASS |

### 关键实现节点

| 文件 | 变更摘要 |
|------|----------|
| `app/agents/langgraph_analysis_graph.py` | 生产级 LangGraph 模块；LangGraphAnalysisRunner 类；_finalize_node 写入 workflow_engine="langgraph" |
| `app/routers/analysis.py` | ComprehensiveV2Request 增加 `engine: Literal["custom_coordinator", "langgraph"] = "custom_coordinator"`；handler 分支 if/else |

**结论：** LangGraph 灰度路径接入 FastAPI 验证通过，旧接口 100% 向后兼容，默认行为未受影响。

---

## Phase M4-b.5 — LangGraph vs custom_coordinator 对比验证（2026-06-04）

**目标：** 在不修改默认 engine、不修改前端、不保存测试报告的情况下，直接调用内部 runner 对两条路径做结构、质量、延迟三维对比。

| 项目 | 结果 |
|------|------|
| 新增文件 | `backend/scripts/compare_analysis_engines.py` |
| 修改 app/ 业务代码 | 否 |
| 修改前端 | 否 |
| 保存测试报告到 DB | 否 |
| 默认 engine | custom_coordinator（未变） |
| 测试 case 数 | 4（默认轻量组合） |
| PASS / WARN / FAIL | 4 / 0 / 0 |
| 结构不兼容 | 无 |
| 质量明显下降 | 无 |
| 性能明显劣化 | 无（最高 ratio=1.26x < 阈值 1.5x） |

### 对比结果

| Case | scope | custom_title | langgraph_title | ratio |
|------|-------|-------------|----------------|-------|
| CN/000001 | technical_only | # 技术面分析报告：平安银行（CN/000001） | # 技术面分析报告：平安银行（CN/000001） | 0.72x |
| CN/000001 | technical_fundamental | # 技术面与基本面分析报告：平安银行（CN/000001） | # 技术面与基本面分析报告：平安银行（CN/000001） | 0.76x |
| CN/000001 | news_only | # 新闻面分析报告：平安银行（CN/000001） | # 新闻面分析报告：平安银行（CN/000001） | 0.95x |
| HK/00700 | technical_only | # 技术面分析报告：腾讯控股（HK/00700） | # 技术面分析报告：腾讯控股（HK/00700） | 1.26x |

**结论：** 两条路径输出结构完全一致，报告标题/身份/质量检查全部通过，延迟无劣化。建议继续灰度，可进入 M4-b.6。

---

## Phase M4-b.6 — 前端开发者 EngineSelector 灰度开关（2026-06-04）

**目标：** 新增开发者隐藏 EngineSelector，允许本地切换分析引擎，不影响普通用户。

| 项目 | 结果 |
|------|------|
| 新增组件 | `EngineSelector.vue`（两个 chip，custom_coordinator / langgraph）|
| 修改 API | `runComprehensiveAnalysisV2` 支持可选 engine 参数 |
| 修改视图 | `ComprehensiveAnalysisView.vue` 新增 showEngineSelector + analysisEngine |
| 修改后端 | 否 |
| 修改旧接口 | 否 |
| 新增 DB migration | 否 |
| npm run build | ✅ exit 0，117 modules |
| compileall app -q | ✅ |

### 显示条件（showEngineSelector computed）

```js
import.meta.env.DEV || localStorage.getItem('tradingagents:dev_mode') === 'true'
```

### localStorage keys

| key | 说明 |
|-----|------|
| `tradingagents:dev_mode` | `"true"` 时在生产环境也显示 EngineSelector |
| `tradingagents:analysis_engine` | 记忆上次选择（`"custom_coordinator"` 或 `"langgraph"`）|

### 请求行为

| 场景 | 请求 body 中的 engine |
|------|----------------------|
| 生产环境（showEngineSelector = false）| 不传（后端默认 custom_coordinator）|
| dev 模式选 custom_coordinator | `engine: "custom_coordinator"` |
| dev 模式选 langgraph | `engine: "langgraph"` |

### E-1 至 E-8 验收

| 测试 | 结果 |
|------|------|
| E-1 生产路径不变 | ✅ |
| E-2 DEV 环境显示 EngineSelector | ✅ |
| E-3 选 LangGraph 请求含 engine=langgraph | ✅ |
| E-4 切回 custom_coordinator | ✅ |
| E-5 刷新后 localStorage 恢复 | ✅ |
| E-6 移除 dev_mode 普通用户不受影响 | ✅ |
| E-7 375px 无横向溢出 | ✅ |
| E-8 Console 无错误 | ✅ |

**结论：** 灰度开关完成，默认 custom_coordinator 不变，LangGraph 路径仅开发者可见。

---

## Phase M5 — ProfileView + History Filter + User Settings MVP（2026-06-04）

**目标：** 补齐「我的」页面、历史报告筛选增强、用户偏好设置 MVP。

| 项目 | 结果 |
|------|------|
| 新增 ProfileView.vue | ✅（用户信息/统计卡/最近报告/最近搜索/偏好/数据源说明/系统操作）|
| 新增 utils/settings.js | ✅（getSettings/saveSettings/resetSettings，events 通知）|
| /me 路由 + auth guard | ✅ |
| AppHeader 新增「我的」 | ✅（5 个导航项，移动端不溢出）|
| HistoryView scope/auto_saved 筛选 | ✅（2 个新筛选 select，不影响旧筛选）|
| 后端 /reports/ 新增 analysis_scope/auto_saved | ✅（无 migration）|
| ComprehensiveAnalysisView 读取 default_market/default_analysis_scope | ✅ |
| ComprehensiveAnalysisView auto_save_report 条件 | ✅ |
| StockDetailView EmptyState 改进 + auto_saved badge | ✅ |
| npm run build | ✅ exit 0，120 modules |
| compileall app -q | ✅ |

### settings.js localStorage key

```
tradingagents:settings:v1
{
  "default_market": "CN",
  "default_analysis_scope": "comprehensive",
  "auto_save_report": true,
  "default_news_hours": 72,
  "show_risk_notice": true,
  "dev_mode": false
}
```

dev_mode 写入时同步更新 tradingagents:dev_mode（M4-b.6 兼容 key）。

---

## Phase M6 — BottomTabBar + PWA 基础配置（2026-06-04）

**目标：** 移动端底部 TabBar 导航 + 基础 PWA 配置，不破坏桌面端布局。

| 项目 | 结果 |
|------|------|
| BottomTabBar.vue（5 tabs）| ✅ |
| 显示断点 | ≤640px |
| 桌面端 AppHeader 保留 | ✅ |
| AppHeader .app-nav 移动端隐藏 | ✅（≤640px display:none）|
| .app-shell padding-bottom 增加 | ✅（≤640px: 72px + safe-area-inset-bottom）|
| App.vue 插入 BottomTabBar | ✅（authenticated template 内）|
| /print 路由隐藏 BottomTabBar | ✅（shouldShow computed）|
| public/manifest.webmanifest | ✅ |
| index.html PWA meta | ✅（manifest/theme-color/apple-capable/viewport-fit）|
| Service Worker | 无（不新增）|
| npm run build | ✅ exit 0，122 modules |
| compileall app -q | ✅ |

### BottomTabBar tab 列表

| tab | path | icon | active 匹配 |
|-----|------|------|------------|
| 综合 | / | 🔬 | exact === '/' |
| 自选 | /watchlist | ⭐ | startsWith('/watchlist') |
| 行业 | /industries | 🏢 | startsWith('/industries') |
| 历史 | /history | 📋 | startsWith('/history') |
| 我的 | /me | 👤 | startsWith('/me') |

### 路由显示策略

| 路由类型 | BottomTabBar |
|---------|-------------|
| 一级页（/、/watchlist 等）| 显示 |
| 二级页（/stocks/:id、/history/:id）| 显示 |
| 打印页（/print/*）| 隐藏 |

---

## M7 — 自选股 / 行业页 Enriched 数据增强（2026-06-04）

### 变更文件

| 文件 | 类型 |
|------|------|
| `backend/app/models/watchlist_item.py` | MODIFIED（+WatchlistEnrichedItemResponse/ListResponse）|
| `backend/app/routers/watchlist.py` | MODIFIED（+GET /watchlist/enriched）|
| `frontend/src/utils/marketFormat.js` | NEW（formatAmount / formatPrice / formatChangePct / changePctClass / formatScopeLabel）|
| `frontend/src/api/watchlist.js` | MODIFIED（+getWatchlistEnriched）|
| `frontend/src/views/WatchlistView.vue` | MODIFIED（enriched data + filter bar）|
| `frontend/src/views/IndustryHotView.vue` | MODIFIED（shared formatters + industry header）|
| `frontend/src/views/StockDetailView.vue` | MODIFIED（当前徽章 + 成交额 + formatAmount import）|

### 关键设计

- **GET /watchlist/enriched** — 注册在 `GET /{item_id}` 之前，避免路由冲突
- **Industry batch query** — `StockIndustryMap.symbol.in_(cn_symbols)` 单次 DB 查询，无 N+1
- **Quote parallel** — `asyncio.gather(*[asyncio.to_thread(svc.get_quote, m, s) for ...])`
- **Fallback** — `getWatchlistEnriched()` 失败时前端自动回退到 `listWatchlist()`
- **"当前" marker** — `s.symbol === symbol` 时添加 `hs-current-row` + `hs-current-badge`，禁止点击跳转

### 冒烟测试（9/9 PASS）

| ID | 描述 | 结果 |
|----|------|------|
| M7-1 | /watchlist/enriched 字段完整 | ✅ |
| M7-2 | quote 失败 graceful | ✅ |
| M7-3 | WatchlistView enriched 展示 | ✅ |
| M7-4 | WatchlistView 过滤栏 | ✅ |
| M7-5 | enriched 失败回退 | ✅ |
| M7-6 | IndustryHotView 行业 header | ✅ |
| M7-7 | StockDetailView 当前徽章 | ✅ |
| M7-8 | StockDetailView 成交额 | ✅ |
| M7-9 | marketFormat.js 正确性 | ✅ |

**npm run build：** 123 modules（+1 vs 122）  
**compileall app -q：** ✅

---

## M8 — StockDetail Profile 聚合接口 + 首屏性能优化（2026-06-04）

### 变更文件

| 文件 | 类型 |
|------|------|
| `backend/app/routers/stocks.py` | MODIFIED（+ProfileQuote/Industry/Watchlist/LatestReport/DataQuality/StockProfileResponse schemas，+_extract_summary()，+GET /{market}/{symbol}/profile）|
| `frontend/src/api/stocks.js` | MODIFIED（+getStockProfile）|
| `frontend/src/views/StockDetailView.vue` | MODIFIED（profile 优先加载，fallback 旧组合请求，watchlist 状态增强）|

### 关键设计

- **GET /stocks/{market}/{symbol}/profile** — asyncio.create_task 启动 quote 后台获取，同时 DB 顺序查询 industry / watchlist / latest_report（避免 AsyncSession 并发问题）
- **summary_excerpt** — 后端 `_extract_summary()` 优先提取「核心摘要」/「核心结论」段落，fallback 前 160 字（strip markdown）
- **identityLoading** — 改为 `computed(() => profileLoading.value)`，无需手动维护两个状态
- **_quoteData computed** — 统一读取 profile.quote 或 fallback 到旧 quote.data dict，消除模板分支
- **quote 价格修复** — 模板从 `quote.data?.current_price ?? quote.data?.close` 修正为 `_quoteData.latest_price ?? ...price`（providers 均返回 `price` 字段）
- **loadAll 结构** — profile → hot_stocks（串行，hot_stocks 需要 industryCode）+ news/reports（并行）
- **回退路径** — profile 失败 → _loadIdentityFallback (searchStocks+getStockQuote) + loadWatchlist

### 冒烟测试（11/11 PASS）

| ID | 描述 | 结果 |
|----|------|------|
| M8-1 | CN profile 字段完整 | ✅ |
| M8-2 | HK profile 不 500，industry=null | ✅ |
| M8-3 | 无 token 返回 401 | ✅ |
| M8-4 | quote 失败降级不白屏 | ✅ |
| M8-5 | StockDetailView 使用 profile | ✅ |
| M8-6 | 自选状态增强 | ✅ |
| M8-7 | summary_excerpt 展示 | ✅ |
| M8-8 | 同行热门股 CN/HK 正确 | ✅ |
| M8-9 | profile 失败回退 | ✅ |
| M8-10 | 移动端 BottomTabBar | ✅ |
| M8-11 | Console 无错误 | ✅ |

**npm run build：** 123 modules  
**compileall app -q：** ✅

---

## Phase M9 — StockDetailView 研究体验增强

### 新增/修改文件

| 文件 | 状态 |
|------|------|
| `frontend/src/utils/navigation.js` | NEW（goAnalyze/goStockDetail/goHistory/goReportDetail）|
| `frontend/src/components/StockDetailResearchPanel.vue` | NEW（section 4 组件化）|
| `frontend/src/utils/marketFormat.js` | MODIFIED（+formatVolume）|
| `frontend/src/views/StockDetailView.vue` | MODIFIED（5 处增强）|

### 关键设计

- **StockDetailResearchPanel** — props: market/symbol/stockName/latestReport/latestFullReport/fullReportLoading/summaryExcerpt/loading；内置 copyText 2s 反馈
- **quote-metrics grid** — 3列，6字段（open/high/low/prev_close/volume/amount），仅 profile.quote.status==='success' 时显示
- **kline-info-bar** — 文案调整为"可切换区间、均线与成交量指标"
- **history limit** — loadReports() limit 10→5，查看全部条件 >=10→>=5

### 冒烟测试（10/10 PASS）

**npm run build：** 126 modules  
**compileall app -q：** ✅

---

## Phase M10 — K 线图与技术面体验增强

### 新增/修改文件

| 文件 | 状态 |
|------|------|
| `frontend/src/components/TechnicalChartPanel.vue` | MODIFIED（全面重写控制栏+MA toggle+stats+hint）|
| `frontend/src/views/StockDetailView.vue` | MODIFIED（kline-info-bar 文案）|
| `frontend/src/components/AnalysisResultLayout.vue` | MODIFIED（section label 文案）|

### 关键设计

- **range/period tabs** — 6 个 tab（1月/3月/6月/1年/周K/月K），默认 3月；activeTab ref，selectTab 触发 fetchKline
- **MA toggles** — reactive show 对象，applySeriesVisibility() 调用 series.applyOptions({ visible })，不重新请求
- **rangeStats computed** — 从 bars.value 计算 max(high)/min(low)/(lastClose-firstOpen)/firstOpen*100/count
- **generation counter** — fetchGen 递增，每次 fetch 捕获 gen，完成后 gen!==fetchGen 时丢弃结果
- **chart-hint** — CSS hidden/show 切换（.hint-desktop / .hint-mobile）配合 media query
- **vol_unit** — volUnitLabel computed 基于 volumeUnit ref（'lot'→手，其他→股）
- **stale tag** — res.stale=true 时显示橙色"缓存数据"标签
- **stock 切换时** — watch([market,symbol]) 重置 activeTab='3m' 防止旧区间状态残留

### 冒烟测试（11/11 PASS）

**npm run build：** 126 modules  
**compileall app -q：** ✅

---

## Phase M11 — MACD / RSI 技术指标扩展

### 新增/修改文件

| 文件 | 状态 |
|------|------|
| `frontend/src/utils/technicalIndicators.js` | NEW（calculateEMA/calculateMACD/calculateRSI/safeNumber）|
| `frontend/src/components/TechnicalChartPanel.vue` | MODIFIED（MACD + RSI 子图、指标摘要、切换开关）|

### 关键设计

- **technicalIndicators.js**
  - `calculateEMA(values, period)` — SMA 种子初始化，返回长度 = 输入长度，前 period-1 个为 null
  - `calculateMACD(times, closes, 12, 26, 9)` — EMA(12)-EMA(26)=DIF，EMA(DIF,9)=DEA，histogram=DIF-DEA；最少需要 34 根K线
  - `calculateRSI(times, closes, 14)` — Wilder's 平滑法，最少需要 15 根K线
  - 所有函数对 NaN/Infinity 严格过滤，输入不足时返回 []

- **MACD 子图** — 独立 lightweight-charts 实例（140px），histogramSeries 按正负着色，2×lineSeries（DIF蓝/DEA橙），lazy init via watch+nextTick，destroyMacdChart 清理

- **RSI 子图** — 独立 lightweight-charts 实例（120px），lineSeries + 3×priceLine（70/30/50），LineStyle.Dashed/Dotted，destroyRsiChart 清理

- **生命周期**
  - `watch(() => show.macd, val => val ? (await nextTick(); init; update) : destroy)`
  - `onUnmounted` 依次调用 destroyMacdChart + destroyRsiChart
  - 独立 ResizeObserver（roMacd/roRsi）随 destroy 一并 disconnect

- **指标摘要** — v-if 依赖 showIndicatorSummary computed（macdSummary/rsiSummary 非空），最新一个点，rsiLabel 4 档文案，macdHistLabel 3 档文案

- **M10 完全保留** — show 初始值 macd:false/rsi:false，MA/vol 切换路径不变，generation counter 不受影响

### 冒烟测试（11/11 PASS）

**npm run build：** 127 modules（+1 vs 126）  
**compileall app -q：** ✅

---

## Phase M16 — 报告中心与历史报告筛选体验升级（2026-06-05）

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase M16 报告中心 | ReportCenterStats / ReportFilterPanel / ReportListCard / HistoryView 重排 / reports.py start_date+end_date | ✅ 已完成 |

### 新增 / 修改文件

| 文件 | 状态 |
|------|------|
| `frontend/src/components/ReportCenterStats.vue` | NEW（4 统计卡：全部/自动/手动/涉及股票） |
| `frontend/src/components/ReportFilterPanel.vue` | NEW（市场/代码/报告类型/保存方式/时间范围 + 查询/重置按钮） |
| `frontend/src/components/ReportListCard.vue` | NEW（卡片式报告行，4 操作按钮，移动端 2 列） |
| `frontend/src/views/HistoryView.vue` | MODIFIED（全面重排，接入 3 个新组件，URL query 联动，时间范围过滤） |
| `backend/app/routers/reports.py` | MODIFIED（新增 start_date / end_date 查询参数，UTC 时区精确过滤） |
| `frontend/src/api/reports.js` | MODIFIED（listReports 新增 start_date / end_date 参数透传） |

### 关键设计

- **ReportCenterStats** — 全部报告数从后端 total（与当前筛选条件一致），其余 3 项基于当前页数据；移动端 ≤540px 变 2 列
- **ReportFilterPanel** — StockSearchBox 选中后自动 emit('search')；时间范围前端转 start_date/end_date 传 API；移动端全部竖排 + 按钮 flex 1
- **ReportListCard** — stock_name 优先/market+symbol fallback；scope badge 与 HistoryDetailView/ProfileView 口径统一；delete emit 交父组件 ConfirmDialog 处理；移动端操作按钮 2×2 grid
- **HistoryView** — 初始 filters 从 route.query 读取；applyFilters → offset=0 + router.replace + loadReports；resetFilters → 清空 filters + router.replace({}) + loadReports；无 watch(route.query)（避免 _syncUrl 触发双重加载）
- **reports.py** — UTC 边界：start_date → datetime(y,m,d, tzinfo=UTC)，end_date → +1day；FastAPI 自动 422 非法日期格式；旧请求行为不变；total_count 与筛选条件一致

### 冒烟测试（15/15 PASS）

**npm run build：** 146 modules（+6 vs 140）  
**compileall backend/app -q：** ✅

---

## Phase M17 — 自选股研究工作台与批量管理（2026-06-05）

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase M17 自选股工作台 | WatchlistStats / WatchlistToolbar / WatchlistStockCard / WatchlistView 重排 / 批量删除 | ✅ 已完成 |

### 新增 / 修改文件

| 文件 | 状态 |
|------|------|
| `frontend/src/components/WatchlistStats.vue` | NEW（4 统计卡：总数/上涨/下跌/有报告；≤540px 2列） |
| `frontend/src/components/WatchlistToolbar.vue` | NEW（市场/涨跌/行业/报告/排序筛选 + 批量模式 + 刷新按钮） |
| `frontend/src/components/WatchlistStockCard.vue` | NEW（卡片式股票行，内联note编辑，bulkMode checkbox，4操作按钮，移动端2列grid） |
| `frontend/src/views/WatchlistView.vue` | MODIFIED（全面重排，接入3个新组件，filteredItems computed，批量删除逻辑） |

### 关键设计

- **WatchlistStats** — 上涨/下跌：quote_status !== 'failed' && change_pct > 0/< 0；有报告：latest_report != null
- **WatchlistToolbar** — `direction:'unavail'` → quote_status==='failed'；行业列表动态来自 items.industry_name 去重；排序：default(保持接口顺序)/change_desc/change_asc/symbol/name；批量模式下显示已选N个/清空/批量删除/退出批量；refresh emit 给 WatchlistView 调 loadItems()
- **WatchlistStockCard** — `isEditingNote`/`editNoteValue`/`isSavingNote`/`noteError` 由 WatchlistView 管理，通过 props 传入；`watch(isEditingNote)` 自动聚焦 textarea；bulkMode=true 时卡片 click 触发 toggle-select，操作按钮隐藏；`wsc-card--selected` class 加 accent box-shadow
- **WatchlistView filteredItems** — 过滤顺序：market → direction → industry → reportFilter → sort；change_pct null 在 change_desc 用 -Infinity，change_asc 用 Infinity，排在末尾
- **批量删除** — `reactive(new Set())` 存 selectedIds；Promise.allSettled 并发逐个调 DELETE；成功项本地从 items 移除，失败项保留；batchStatus 文案反馈；失败>0 时补全 loadItems() 同步状态
- **enriched fallback** — 保留原有逻辑：enriched 失败 → fallback listWatchlist()，listError 仅在 fallback 也失败时显示
- **note 编辑** — 逻辑与原 WatchlistView 完全一致，移入 WatchlistView 管理 editingNoteId/editNoteValue/savingNoteId/noteError

### 冒烟测试（15/15 PASS）

**npm run build：** 152 modules（+6 vs 146）  
**compileall backend/app -q：** ✅

---

## Phase M18 — 个人研究中心与用户偏好增强（2026-06-05）

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase M18 个人研究中心 | ProfileResearchStats / ProfileActivityPanel / ProfileSettingsPanel / DataSourceNoticePanel / ProfileView 重排 / userSettings.js | ✅ 已完成 |

### 新增 / 修改文件

| 文件 | 状态 |
|------|------|
| `frontend/src/utils/userSettings.js` | NEW（settings.js 薄包装：DEFAULT_SETTINGS alias + updateSettings + syncDevMode；保留 settings.js 原有导出路径） |
| `frontend/src/components/ProfileResearchStats.vue` | NEW（6统计卡：watchlistCount/reportTotal/autoSavedCount/manualCount/uniqueStocksCount/recentSearchCount；6列→3列→2列 responsive） |
| `frontend/src/components/ProfileActivityPanel.vue` | NEW（2列desktop/1列mobile；最近报告+最近搜索；emit go-report/pick-search/clear-searches；RouterLink 查看全部） |
| `frontend/src/components/ProfileSettingsPanel.vue` | NEW（6设置项；patch emit → ProfileView 调 saveSettings；还原默认 emit reset；移动端竖排） |
| `frontend/src/components/DataSourceNoticePanel.vue` | NEW（默认折叠；数据源/边界/风险声明 3 节；no props；内部 open ref） |
| `frontend/src/views/ProfileView.vue` | MODIFIED（全面重排；导入 4 个新组件；保留 settings.js/loadStats/loadRecentReports/auth 全部逻辑） |

### 关键设计

- **ProfileResearchStats** — manualCount = reportTotal - autoSavedCount（后端 total 精确）；loading 时显示 "—"；注明"报告统计基于最近加载数据"
- **ProfileActivityPanel** — 纯展示+emit，不在组件内 router.push；recentSearches.slice(0, 10)；时间格式 M月D日 HH:MM
- **ProfileSettingsPanel** — emit('update:settings', patch)，ProfileView 调 saveSettings；新增 default_news_hours(24/72/168) 和 show_risk_notice UI（settings.js DEFAULTS 已有这两项）
- **DataSourceNoticePanel** — 3节：数据来源（行情/财务/新闻/行业/技术指标）+ 数据边界（5条）+ 风险声明（4条）；无投资建议措辞
- **ProfileView** — 保留 getSettings/saveSettings/resetSettings/SETTINGS_EVENT 从 settings.js 导入（不改 ComprehensiveAnalysisView 依赖链）；ActivityPanel go-report/pick-search 直接 inline handler；handleClearSearches 更新 recentSearches ref
- **userSettings.js** — re-export 路径：`export { ... } from './settings.js'` + 新增 updateSettings/syncDevMode；ComprehensiveAnalysisView/EngineSelector/ProfileView 仍从 settings.js 导入，无需修改

### 冒烟测试（11/11 PASS）

**npm run build：** 160 modules（+8 vs 152）  
**compileall backend/app -q：** ✅

## Phase M19 — 行业研究页 App 化与热门股卡片化（2026-06-06）

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase M19 行业研究页升级 | IndustryOverviewPanel / IndustryHotStats / IndustryToolbar / IndustryStockCard / IndustryHotView 重排 | ✅ 已完成 |

### 新增 / 修改文件

| 文件 | 状态 |
|------|------|
| `frontend/src/components/IndustryOverviewPanel.vue` | NEW（行业名称/code/market badge/trade_date/score_version/item 数量/data_quality.message/loading skeleton/error/empty；Hot Score 说明文案无投资建议） |
| `frontend/src/components/IndustryHotStats.vue` | NEW（4 统计卡：热门股数量/上涨/下跌/平均 Hot Score；change_pct null safe；hot_score null safe；avgScore 3 位小数；NaN/Infinity 无法出现） |
| `frontend/src/components/IndustryToolbar.vue` | NEW（行业下拉/涨跌筛选/数据源动态筛选/排序 select/刷新按钮；切换筛选不 emit refresh，只 emit update:filters/update:sortKey；切换行业 emit update:selectedCode 由父组件触发 loadHotStocks） |
| `frontend/src/components/IndustryStockCard.vue` | NEW（rank badge 金银铜/普通；Hot Score；股票名+market badge+symbol；change_pct 涨跌色；amount；data_source；4 操作按钮；加自选 5 状态机；移动端 2×2 操作 grid） |
| `frontend/src/views/IndustryHotView.vue` | MODIFIED（全面重排；移除 table+mobile card 双 markup；统一 IndustryStockCard；filteredItems computed；availableDataSources computed；快速搜索 → goDetail；切换行业重置 filters/sortKey/watchlistStatus） |

### 关键设计

- **IndustryOverviewPanel** — 无 API 调用，props 接收 industry + hotData；data_quality.message 展示；加 "Hot Score 仅用于研究线索排序" 免责说明
- **IndustryHotStats** — 全部数值通过 computed 推导；avgScore 使用 `.filter(isFinite)` 避免 NaN；up/down 仅统计 change_pct 非 null 的条目
- **IndustryToolbar** — dataSources prop 来自父组件 availableDataSources computed（从 hotData.items 动态提取 Set）；筛选 emit `update:filters` 由父组件更新 filters ref，触发 filteredItems 重算，不触发 API
- **IndustryStockCard** — add-watchlist emit 给父组件处理，addingStatus prop 回流；added/exists 状态下按钮点击无效；detail/analyze/history 全部 emit，父组件 inline handler 调 router
- **filteredItems 排序** — null 值处理：hot_score null → -Infinity (desc)；change_pct null → -Infinity (desc) / +Infinity (asc)；amount null → -Infinity；rank null → +Infinity；不 mutate 原数组（`[...list].sort`）
- **快速搜索** — @select → goDetailSelected → `/stocks/CN/${item.symbol}`（改为跳详情而非分析页）
- **切换行业** — onIndustryChange：先更新 selectedCode，重置 filters/sortKey/'all'/'rank'，清空 watchlistStatus，再 loadHotStocks
- **table 移除** — 统一 IndustryStockCard，减少 DOM 冗余，移动端一致性提升

### 冒烟测试（8/8 PASS）

**npm run build：** 168 modules（+8 vs 160）  
**compileall backend/app -q：** ✅  
**无影响范围：** StockDetailView / WatchlistView / HistoryView / HistoryDetailView / ProfileView / LangGraph 灰度开关 均未修改

## Phase M20 — 股票对比功能 MVP（2026-06-06）

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase M20 股票对比 | StockCompareSelector / StockCompareSummary / StockCompareTable / StockCompareView / WatchlistToolbar 对比入口 | ✅ 已完成 |

### 新增 / 修改文件

| 文件 | 状态 |
|------|------|
| `frontend/src/components/StockCompareSelector.vue` | NEW（市场选择+StockSearchBox搜索/手动输入；最多4只；重复 2.5s 提示；chip 展示 market/symbol/name；移动端竖排） |
| `frontend/src/components/StockCompareSummary.vue` | NEW（4统计卡：已选/行情可用/有报告/涉及行业；quote.status==='success'；industry_name Set去重；null safe；2列→2列→2列 responsive） |
| `frontend/src/components/StockCompareTable.vue` | NEW（桌面表格+移动端卡片双 markup，≤600px 切换；stock_name fallback 链；quality dots 行情/行业/报告；remove emit；_loading/_failed 安全渲染） |
| `frontend/src/views/StockCompareView.vue` | NEW（selectedStocks ref + profiles ref；handleAdd/handleRemove/clearAll；_loadProfile 失败写入 _failed stub 不白屏；URL query 初始化 Promise.allSettled；_pushUrl router.replace + _syncingUrl flag） |
| `frontend/src/router/index.js` | MODIFIED（新增 /compare 懒加载路由；/compare 加入 protectedPrefixes） |
| `frontend/src/components/WatchlistToolbar.vue` | MODIFIED（新增对比按钮 btn-compare 样式；selectedCount 2~4 可用；disabled 时 opacity 0.45；emit compare） |
| `frontend/src/views/WatchlistView.vue` | MODIFIED（新增 handleCompare：取 selectedIds→items→stocks param→router.push('/compare?stocks=...')；@compare="handleCompare"） |

### 关键设计

- **StockCompareSelector** — tryAdd 先判 isFull 再判重复，重复时 showDup(2500ms 定时清除)；@select 直接 tryAdd(market, item.symbol, item.name)；@keydown.enter → onAddManual；添加后清空 searchSymbol
- **StockCompareSummary** — quoteAvail: `p?.quote?.status === 'success'`；hasReport: `p?.latest_report != null`；industryCount: `new Set(names).size`（names filter 非空字符串，HK 无 industry_name 不计入）
- **StockCompareTable** — `_market/_symbol/_name/_loading/_failed` 内部元数据字段；stockName 三级 fallback（quote.stock_name → industry.stock_name → _name → market/symbol）；qualityDotClass：success→绿，failed/none→灰，其他→黄
- **StockCompareView** — profiles[idx] 整体替换（Vue 追踪响应性）；profile 失败写 `_failed: true` stub 而非抛出；_syncingUrl flag 防止 router.replace 后触发重复加载（本页没有 watch route.query，flag 为防御性保留）；URL 初始化跳过格式不合法 token（非 CN/HK 前缀）
- **WatchlistToolbar compare** — 选 <2 或 >4 时 disabled（title tooltip 解释原因）；按钮仅在 bulkMode 时可见，不影响正常模式
- **handleCompare** — filter selectedIds.has(item.id) 从 items.value 中取实际 item，构建 market:symbol param，router.push 不影响批量删除逻辑

### 冒烟测试（7/7 PASS）

**npm run build：** 176 modules（+8 vs 168）  
**compileall backend/app -q：** ✅  
**无影响范围：** StockDetailView / IndustryHotView / HistoryView / HistoryDetailView / ProfileView / LangGraph 灰度开关 均未修改

## Phase M21 — 股票详情加入对比与迷你趋势图（2026-06-06）

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase M21 对比链路增强 | compareStorage / StockMiniTrend / StockDashboardPanel 对比入口 / StockCompareView storage 联动 / StockCompareTable 趋势列 | ✅ 已完成 |

### 新增 / 修改文件

| 文件 | 状态 |
|------|------|
| `frontend/src/utils/compareStorage.js` | NEW（LS key tradingagents:compare_list:v1；getCompareList/addCompareStock/removeCompareStock/clearCompareList/buildCompareQuery/dispatchCompareUpdated；JSON parse 失败 fallback []；HK/00700 原格式保留） |
| `frontend/src/components/StockMiniTrend.vue` | NEW（纯 SVG polyline；close 价格归一化到 [PAD_Y, height-PAD_Y]；range=0 画水平线；_mounted flag 防止卸载后更新；watch market/symbol 重新加载；ResizeObserver 适配容器宽度；trend-up/down/neutral 颜色） |
| `frontend/src/components/StockDashboardPanel.vue` | MODIFIED（compareStatus prop；compareBtnLabel/compareBtnClass computed；+ 加入对比 / → 对比页 两个按钮；emit add-to-compare/go-compare；btn-compare-on CSS） |
| `frontend/src/views/StockDetailView.vue` | MODIFIED（import compareStorage；compareStatus ref；_refreshCompareStatus；handleAddToCompare 含 2.5s 定时恢复；handleGoCompare 自动加入当前股票再跳转；loadAll 开始时调用 _refreshCompareStatus） |
| `frontend/src/components/StockCompareTable.vue` | MODIFIED（桌面端新增"近30日趋势"列；移动卡片新增趋势行；_failed 时不渲染 StockMiniTrend；导入 StockMiniTrend） |
| `frontend/src/views/StockCompareView.vue` | MODIFIED（import compareStorage 全套；handleAdd/handleRemove/clearAll 同步 storage；_init 优先 URL query，fallback storage；_onCompareUpdated 监听外部更新（view 为空时才响应）；onUnmounted 清理事件） |

### 关键设计

- **compareStorage** — 纯 localStorage + JSON；addCompareStock 先查 duplicate，再查 full，避免 state 错误；dispatchCompareUpdated 触发跨页面同步
- **StockMiniTrend** — SVG 宽度由 ResizeObserver 动态测量；close 字段兼容 `d.close / d.c / d[4]`；`_mounted` flag 防止异步回调在组件卸载后修改 ref；range=0 时 `y = h/2`（水平线）；trendClass 仅表达区间涨跌，无投资建议
- **StockDashboardPanel** — compareStatus 由父组件（StockDetailView）管理并传入；按钮不依赖 localStorage，纯 prop 驱动
- **StockDetailView** — _refreshCompareStatus 在 loadAll 开始时调用（symbol 切换时刷新）；handleAddToCompare 结果驱动 compareStatus，2.5s 后 _refreshCompareStatus 回调到真实状态；handleGoCompare 保证至少把当前股票加入 storage 再跳转
- **StockCompareView** — URL query 优先：有 query 时清空 storage 再重写（URL 为 source of truth）；无 query 时读 storage；_onCompareUpdated 只在 view 为空时响应，避免覆盖用户已选股票

### 冒烟测试（7/7 PASS）

**npm run build：** 179 modules（+3 vs 176）  
**compileall backend/app -q：** ✅  
**无影响范围：** IndustryHotView / HistoryView / HistoryDetailView / ProfileView / WatchlistView 批量对比 / LangGraph 灰度开关 均未修改

---

## Phase M22 — 首页综合分析仪表盘增强（2026-06-06）

### 新增 / 修改文件

| 文件 | 状态 |
|------|------|
| `frontend/src/components/HomeDashboardPanel.vue` | NEW（6区块仪表盘；stats bar 4卡 + 双列网格 + compare bar；纯 props/emit；≤640px 单列） |
| `frontend/src/components/HomeHeroPanel.vue` | MODIFIED（标题→"AI 多 Agent 股票研究助手"；chips 更新；底部风险提示） |
| `frontend/src/views/ComprehensiveAnalysisView.vue` | MODIFIED（useRouter 导入；listReports/getWatchlistEnriched/listIndustries/getIndustryHotStocks/getRecentSearches/compareStorage 导入；dashboard state refs；loadDashboardData Promise.allSettled；7个 onDash* 事件处理器；HomeDashboardPanel 在 v-if="!result && !loading" 渲染） |

### 关键设计

- **loadDashboardData** — Promise.allSettled 并发加载 reports/watchlist/industries；行业热门单独 try/catch 非阻塞；任意失败不白屏；dashboardLoading ref 控制 spinner
- **pick-stock** — emit → stockInputRef.fill(market, symbol)，填入输入框不触发分析
- **compareList** — 同步读 compareStorage.getCompareList()（localStorage），仅在 loadDashboardData 调用时刷新
- **go-compare** — 有 compareList 时带 query 参数跳转，无则直接 /compare

### 冒烟测试（7/7 PASS）

**npm run build：** 181 modules（+2 vs 179）  
**compileall backend/app -q：** ✅  
**无影响范围：** StockCompareView / StockDetailView / WatchlistView / IndustryHotView / HistoryView / ProfileView / LangGraph 灰度开关 均未修改

---

## Phase M23 — 全局发布前质量收口（2026-06-06）

### 审计结果

| 审计项 | 结果 |
|--------|------|
| 文案安全（13个禁止词 .vue 全局扫描） | ✅ PASS，0 matches |
| 跳转链路（20+ 路由，HomeDashboardPanel/Watchlist/Industry/Report/Profile） | ✅ PASS |
| 移动端 padding（BottomTabBar 72px 遮挡防护） | ✅ PASS，.app-shell calc(72px + env(safe-area-inset-bottom)) |
| 空状态（EmptyState.vue 存在 + hdp/wv/hv empty 覆盖） | ✅ PASS |

### CSS 轻量修复

| 文件 | 修改 |
|------|------|
| `HomeDashboardPanel.vue` | `.hdp-stats` margin-bottom 0→12px；`.hdp-grid` gap 0→10px；`.hdp-col` 新增 gap 10px；`.hdp-grid` margin-bottom 新增 12px |

### 文档更新

| 文档 | 内容 |
|------|------|
| `docs/demo_walkthrough.md` | 3分钟/5分钟 Demo 全量重写，含首页仪表盘/股票详情/K线/对比/行业/报告中心/我的 |
| `docs/project_readme_draft.md` | 功能表/技术栈/架构图/限制全量更新至 M22 |
| `docs/final_project_summary.md` | 页面路由表/组件数/功能全景更新至 M22 |
| `docs/final_app_smoke_test.md` | 新建最终交付测试清单（环境/登录/5Tab/二级页/核心链路/移动端/文案安全） |

### 冒烟测试（6/6 PASS）

**npm run build：** 181 modules（CSS-only patch，module count 不变）  
**compileall backend/app -q：** ✅

---

## Phase M24 — 最终部署准备与生产环境 Smoke Test（2026-06-06）

### 审计结果

| 审计项 | 结果 |
|--------|------|
| 环境变量安全（.env 未 track，config.py 无硬编码） | ✅ PASS |
| Docker 文件完整性（Dockerfile×2 / compose / nginx.conf / deploy_smoke_check.sh） | ✅ PASS |
| deploy_smoke_check.sh syntax（bash -n） | ✅ PASS |
| Alembic migration 链（单 head b4d8e2f1a6c9，5 revisions，线性） | ✅ PASS |
| .gitignore 覆盖（.env / dist/ / node_modules / __pycache__）| ✅ PASS |
| 无敏感文件 track（git ls-files 验证） | ✅ PASS |

### 新增文档

| 文件 | 内容 |
|------|------|
| `docs/deployment_guide.md` | 本地开发+Docker+Alembic+环境变量+数据初始化+常见问题 |
| `docs/security_checklist.md` | 密钥管理+.gitignore+代码安全+日志安全+部署前检查命令 |
| `docs/api_smoke_test_plan.md` | T-01~T-12 curl 模板（health/auth/search/profile/kline/news/watchlist/reports/industries/hot-stocks/分析×2），token 不打印 |

### 静态检查

**npm run build：** 181 modules（不变）  
**compileall backend/app -q：** ✅  
**bash -n scripts/deploy_smoke_check.sh：** ✅ SYNTAX OK

### 回归保护

本阶段仅修改文档，无任何业务代码变更。M14~M23 所有功能完整保留。  
人工验证路径：`docs/final_app_smoke_test.md`

---

## Phase M25-a — SSE 实时分析进度推送 MVP（2026-06-06）

### 概述

新增 SSE 实时进度展示。build 模块数：183（+2）。

### 新增/修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/api/analysis.js` | 修改 | 新增 createAnalysisRun / subscribeAnalysisEvents / getAnalysisRun / cancelAnalysisRun |
| `src/components/AnalysisProgressPanel.vue` | 修改 | 新增 mode/progress/agentStatuses/latestEvent props，realtime 模式 Agent 格，"停止等待"按钮 |
| `src/components/AnalysisEventTimeline.vue` | 新增 | Dev mode SSE 事件日志，折叠展示，最多 20 条 |
| `src/views/ComprehensiveAnalysisView.vue` | 修改 | SSE 为主路径（custom_coordinator），langgraph/SSE 错误 fallback 旧 API |
| `nginx.conf` | 修改 | `proxy_cache off` + `add_header X-Accel-Buffering no` |

### subscribeAnalysisEvents 实现要点

使用 `fetch + ReadableStream`（非 `EventSource`）原因：EventSource 不支持自定义 Authorization header。
SSE 解析：手动处理 `event:` / `data:` / `id:` / `:comment` 行，buffer 跨 chunk 拼接。

### 降级策略

```
handleAnalyze()
  └─ engine === 'langgraph'  → _runLegacyApi()（阻塞 API）
  └─ createAnalysisRun 失败  → _runLegacyApi()（fallback）
  └─ SSE stream 错误         → _runLegacyApi()（fallback）
  └─ AbortError              → errorMsg '本次分析已取消'
```

### 静态检查

**npm run build：** ✓ 183 modules，exit 0

---

## Phase M25-c：LangGraph SSE 事件流灰度接入（2026-06-06）

### 变更说明

engine=langgraph 时前端不再 early-return 到旧阻塞 API，统一走 SSE 路径。

### 降级策略更新

```
handleAnalyze()
  └─ createAnalysisRun(engine=langgraph) → SSE path（M25-c 新增）
     └─ SSE 失败 → _runLegacyApi(engineParam)  ← engineParam 保留 langgraph
  └─ createAnalysisRun(engine=custom_coordinator) → SSE path（不变）
     └─ SSE 失败 → _runLegacyApi(undefined)
  └─ cancel → 停止等待，不触发 fallback
```

### 修改文件

| 文件 | 变更 |
|------|------|
| `frontend/src/api/analysis.js` | `createAnalysisRun` 透传 `engine` 字段 |
| `frontend/src/views/ComprehensiveAnalysisView.vue` | 移除 `if (engineParam === 'langgraph') { _runLegacyApi }` early-return；SSE fallback 保留 `engineParam` |

### 兼容性

- **ProgressPanel**：不需知道 engine 差异，`agentStatuses` / `analysisScope` 驱动显示
- **EventTimeline**：正常显示 `workflow_engine=langgraph` 的事件；`event_id` / `elapsed_ms` / `clear` 均正常
- **EngineSelector**：dev mode 不退化
- **普通用户**：不传 engine，默认 custom_coordinator，行为完全不变

### 静态检查

**npm run build：** ✓ 183 modules，exit 0

---

## Phase M26：最终收口（2026-06-06）

### 变更说明

本阶段零代码变更，仅更新文档。前端 build 保持 183 modules。

### 最终前端架构确认

```
ComprehensiveAnalysisView（keep-alive）
  ├─ SSE path（default / langgraph M25-c）
  │    createAnalysisRun(engine?) → subscribeAnalysisEvents(reconnect)
  │    guard: reportReadyHandled / fallbackStarted / cancelRequested / _isMounted
  │    cancel: abort-first → API cancel（不触发 fallback）
  │    failure → _runLegacyApi(engineParam)
  └─ AnalysisProgressPanel (mode=realtime)
       SCOPE_AGENTS_MAP → skipped 推导（无需事件）
       secondsSinceEvent → 15s 慢连接提示
  └─ AnalysisEventTimeline (dev mode)
       MAX_DISPLAY=30 / event_id / elapsed_ms / clear
```

### 路由矩阵（最终）

| 路由 | 组件 | Auth Guard | BottomTabBar | 备注 |
|------|------|-----------|--------------|------|
| `/` | ComprehensiveAnalysisView | ✅ | ✅（tab 1）| keep-alive |
| `/watchlist` | WatchlistView | ✅ | ✅（tab 2）| |
| `/industries` | IndustryHotView | ✅ | ✅（tab 3）| |
| `/history` | HistoryView | ✅ | ✅（tab 4）| |
| `/me` | ProfileView | ✅ | ✅（tab 5）| |
| `/stocks/:market/:symbol` | StockDetailView | ✅ | ❌（二级）| 返回键 |
| `/compare` | StockCompareView | ✅ | ❌（二级）| stocks query |
| `/history/:id` | HistoryDetailView | ✅ | ❌（二级）| |
| `/print/report` | PrintReportView | ✅ | ❌（打印页）| |
| `/login` | LoginView | ❌ | ❌ | |
| `/register` | RegisterView | ❌ | ❌ | |

### npm run build 结果

✓ 183 modules transformed，exit 0

---

## Phase M29 — 综合分析页体验增强（2026-06-06）

### npm run build 结果

✓ 183 modules，exit 0

### 架构变更

```
ComprehensiveAnalysisView
├── StockInputPanel (showGuide, @focus-input)    ← M29: 首次引导 glow
├── RecentSearchList (defaultLimit=5, expandedLimit=10)  ← M29: 展开/收起 + count badge
├── DiscoveryPanel → getTopSearches(5) fallback DEFAULT_PICKS  ← M29: 高频 Top 5
└── AnalysisModeSelector (文案更新)              ← M29: "选择分析范围"
```

### 新增 localStorage key

| Key | 用途 |
|-----|------|
| `tradingagents:first_analysis_hint_seen` | 首次引导是否已显示（写入后不再展示）|

### recentSearches 数据格式

```js
// M29+ 格式（向后兼容旧数据）
{ market, symbol, stock_name, ts, count }
```

旧数据无 `count` 字段 → `getTopSearches()` 内部补充为 1，不报错。

### 路由矩阵（不变，参见 M26 节）

---

## Phase M30 — 行业研究页重构（2026-06-06）

### npm run build 结果

✓ 187 modules，exit 0（M29 为 183，+4 新组件）

### 新增组件

| 组件 | 功能 |
|------|------|
| `IndustryHeatOverviewCard.vue` | 行业热度全览网格（30 tiles），hot_score 可用时颜色渐变 |
| `IndustryHotBlocksCard.vue` | 行业热门板块榜，展开/收起至 20 条 |

### IndustryHotView 新结构

```
IndustryHotView
├── 标题栏（"行业研究"）
├── .ihv-hero-grid（grid 2列→1列）
│    ├── IndustryHeatOverviewCard
│    └── IndustryHotBlocksCard (hotBlocksExpanded ref)
├── IndustryHotStats（card）
├── 快速跳转（card，原在顶部，现在统计栏下方）
├── IndustryToolbar
├── IndustryOverviewPanel
└── IndustryStockCard list（HOT_LIMIT=20）
```

### 后端变更

- `backend/app/routers/industry.py`: hot-stocks limit Query(default=20, le=50)
- DiscoveryPanel 仍显式传 limit=5（`getIndustryHotStocks(market, code, { limit: 5 })`）

### 响应式断点

| 断点 | 行为 |
|------|------|
| > 640px | hero grid 双列 |
| ≤ 640px | hero grid 单列 |
| ≤ 480px | tile 4 列，搜索全宽 |
| ≤ 380px | tile 3 列 |

---

## Phase M36 + M36.1 — output_language 前端验证（2026-06-07）

### 新增/修改文件

| 文件 | 变更 |
|------|------|
| `src/utils/settings.js` | DEFAULTS.report_language = 'zh-CN' |
| `src/components/ProfileSettingsPanel.vue` | 报告输出语言选择器（独立于 UI 语言） |
| `src/api/analysis.js` | createAnalysisRun / runComprehensiveAnalysisV2 含 output_language |
| `src/api/reports.js` | createReport body 含 output_language；getReport 返回 output_language |
| `src/views/ComprehensiveAnalysisView.vue` | reportLanguage ref；两条分析路径均透传 output_language |
| `src/components/ReportListCard.vue` | langLabel computed + .rlc-lang-badge 黄色 badge |
| `src/components/ReportDetailHeader.vue` | langBadge computed + .rdh-lang-badge 黄色 badge |
| 6 locale 文件 | settings_rpt_lang / settings_rpt_lang_hint / lang_* 各 8 键 |

### Badge 逻辑

- zh-CN 不显示 badge（默认语言，无需额外标记）
- 其他 5 语言显示短码：`EN` / `繁中` / `JA` / `KO` / `ES`
- 未知语言 fallback 显示原 code，不出现 undefined/null

### M36.1 Fix

- `getReport()` 补充 `output_language: data.output_language || 'zh-CN'`，确保历史报告详情 badge 正常读取 DB 值

### 构建

- `npm run build` ✅ 195 modules，0 errors，877ms

---

## Phase M37 — Agent-level output_language prompt 原生支持（2026-06-07）

### 变更范围（纯 Backend，无前端改动）

| 文件 | 变更 |
|------|------|
| `backend/app/agents/language_utils.py` | 新建 — normalize_output_language / build_output_language_instruction |
| `backend/app/agents/technical_analyst.py` | analyze() 新增 output_language 参数，_build_user_prompt 追加语言指令 |
| `backend/app/agents/fundamental_analyst.py` | 同上 |
| `backend/app/agents/peer_comparison_analyst.py` | analyze() + analyze_async() 均新增 output_language 参数 |
| `backend/app/agents/news_analyst.py` | analyze() 新增 output_language 参数，_build_user_prompt 追加语言指令 |
| `backend/app/agents/comprehensive_analysis_coordinator.py` | _run_agents_parallel / _run_agents_parallel_async / _run_agents_scoped 透传 output_language |
| `backend/app/agents/realtime_analysis_runner.py` | _run_named_agent 新增 output_language 参数，任务创建时透传 |
| `backend/app/agents/langgraph_analysis_graph.py` | 4 个 node 函数从 state.output_language 读取并透传至 Agent |

### 前端影响

无。前端 API 已在 M36 正确传递 output_language，无需修改。

### 构建结果

| 检查项 | 结果 |
|--------|------|
| `npm run build` | ✓ 195 modules, 0 errors |
| `python -m compileall app -q` | ✓ 0 errors |
| `alembic current` | ✓ c5e9f12a3b87 (head) |

### 静态验证结果

- language_utils 6 语言 normalize + instruction 生成：ALL PASS
- 四个 Agent 签名含 output_language default zh-CN：ALL PASS
- backward compat（旧调用不传 output_language）：ALL PASS
- LangGraph 4 node 函数从 state 读取 output_language：ALL PASS

---

## Phase M40-b + M40-c：Redis Registry + SSE Bug 修复回归

### 后端变更（零前端改动）

- `redis_run_registry.py`：RedisAnalysisRunRegistry 全新实现（443 行）
- `run_registry_factory.py`：懒加载单例，Redis 分支 fail-fast
- `analysis.py`：_safe_get_registry() 503 处理，asyncio.shield(pending_task) B1 修复
- `langgraph_realtime_runner.py`：_merge_updates None 守卫（B2 修复）

### 前端回归（无变更）

- npm run build: ✅ 195 modules，0 errors
- 页面路由：全部正常（前端无改动）
- EngineSelector 灰度开关：DEV / dev_mode 仅限开发者
- SSE 重连 after_event_id / reportReadyHandled / fallbackStarted：行为不变

### SSE 关键修复验证

| 场景 | 结果 |
|------|------|
| custom_coordinator + memory 完整事件流 | ✓ PASS |
| LangGraph + memory 心跳后继续流（B1 验证） | ✓ PASS（heartbeat #1 后继续） |
| LangGraph + Redis None 守卫（B2 验证） | ✓ PASS（无 NoneType 错误） |
| after_event_id replay（Redis） | ✓ PASS（3/3 事件正确回放） |
| cancel memory / Redis | ✓ PASS（两路均返回 cancelled 事件） |
| Redis 不可用 HTTP 503 | ✓ PASS |

---

## Phase M41：LangGraph 默认化灰度决策验证

### 前端审计（无代码改动）

- EngineSelector `v-if="showEngineSelector"`：`import.meta.env.DEV || localStorage.tradingagents:dev_mode=true` ✅
- 生产构建不传 engine 字段（`engineParam = showEngineSelector ? value : undefined`）✅
- ComprehensiveAnalysisView：两条 engine 路径走同一 SSE 处理逻辑 ✅
- npm run build: ✅ 195 modules，0 errors（无前端改动）

### 结论

- LangGraph 灰度满足前端零改动条件
- EngineSelector 灰度开关设计正确，不需要修改
- 后端 DEFAULT_ANALYSIS_ENGINE 环境变量方案（G2）前端透明

---

## Phase M42：DEFAULT_ANALYSIS_ENGINE 前端兼容性

### 前端行为审计（无代码改动）

`ComprehensiveAnalysisView.vue` L531:
```js
const engineParam = showEngineSelector.value ? analysisEngine.value : undefined
// ...
engine: engineParam,  // undefined → JSON 序列化时省略此键
```

- 非 dev mode：`showEngineSelector = false` → `engineParam = undefined` → 请求 body 无 `engine` 字段 → 后端使用 `DEFAULT_ANALYSIS_ENGINE` ✅
- dev mode：`showEngineSelector = true` → `engineParam = analysisEngine.value` → 请求 body 含 `engine` → 优先于 env ✅

### 结论

- 前端零改动，env 灰度对普通用户完全透明
- npm run build: ✅ 195 modules
- 前端 SSE 处理逻辑对两种 engine 完全兼容（M40-c/M41 已验证）

---

## Phase M43：Release Candidate 前端收口

### 构建验证

| 项目 | 结果 |
|------|------|
| npm run build | ✅ 195 modules, 0 errors |
| 无 TypeScript/Vite 编译错误 | ✅ |
| 无 console.error（静态） | ✅ |

### 前端兼容性（M43）

| 验证点 | 结果 |
|--------|------|
| 生产模式不传 engine 字段（`engineParam = undefined`） | ✅ 后端使用 DEFAULT_ANALYSIS_ENGINE |
| dev 模式显式 engine 字段优先 | ✅ 已 M42-7/M42-8 验证 |
| SSE 前端解析对 4-worker Redis 无改动 | ✅ 事件流协议层零变更 |
| 报告保存 POST /reports/ 返回 201 + id | ✅ M43-7 PASS |
| 报告列表 GET /reports/ total/items 正确 | ✅ M43-7 PASS |
| 报告详情 GET /reports/{id} 字段完整 | ✅ M43-7 PASS |

### 主题 × 语言矩阵（构建级验证）

三套主题（light-holo / dark-dive / paper-lilac）× 六语言（zh-CN / zh-TW / en-US / ja-JP / ko-KR / de-DE）CSS 变量均通过 `html[data-theme]` 属性选择器隔离，无冲突，build 正常。

---

## Phase M47 / M47-b：综合分析页行业热门板块验证

**日期：** 2026-06-11  
**构建：** ✅ 195 modules, 0 errors

### 改动内容

| 改动 | 文件 | 说明 |
|------|------|------|
| 删除"最近搜索"小卡片 | HomeDashboardPanel.vue | 右列上区域移除 |
| 新增"行业热门板块"卡片 | HomeDashboardPanel.vue | top 6 行业按 hot_score 排列 |
| 传入 industryList + error | ComprehensiveAnalysisView.vue | 排序后注入 |
| 点击行业跳转 /industries?focus= | ComprehensiveAnalysisView.vue | onDashGoIndustryBlock |
| hot stocks limit 5 → 20 | ComprehensiveAnalysisView.vue | 仪表盘 compact 仍 slice(0,5) |
| focus query 高亮滚动 | IndustryHotView.vue | watch + data-industry-code |
| data-industry-code 属性 | IndustryHotBlocksCard.vue | 供 focus DOM 查询 |
| fmtScore 1dp → 2dp | HomeDashboardPanel.vue | 与 IndustryHotBlocksCard 一致 |
| ind_unknown 缺字段 fallback | HomeDashboardPanel.vue + 6 locales | 行业名为空时展示 |
| ind_blocks_* keys | zh-TW/ja-JP/ko-KR/es-ES | 4 语言补齐 |

### M47-b 验证项

| # | 验证点 | 结果 |
|---|--------|------|
| 1 | 右上区域不再显示"最近搜索" | ✅ 已删除 |
| 2 | 下方大块"最近搜索"(RecentSearchList)仍保留 | ✅ 未改动 |
| 3 | 右上区域显示"行业热门板块" | ✅ ind_blocks_title |
| 4 | 最多显示 6 个行业 | ✅ slice(0,6) |
| 5 | hot_score 降序排列 | ✅ sort desc in ComprehensiveAnalysisView |
| 6 | 排名 1/2/3 弱高亮 | ✅ hdp-iblk-rank--top (gold) |
| 7 | avg_change_pct 正负颜色 | ✅ up/down CSS vars |
| 8 | hot_score 2dp 格式 | ✅ fmtScore toFixed(2) |
| 9 | 行业名为空不崩溃 | ✅ || t('ind_unknown') fallback |
| 10 | hot_score/avg_change_pct 缺失显示 — | ✅ ternary fallback |
| 11 | 点击"展示全部"跳转 /industries | ✅ emit go-industries |
| 12 | 点击行业跳转 /industries?focus=<code> | ✅ onDashGoIndustryBlock |
| 13 | 行业页 focus 高亮+滚动 | ✅ watch + scrollIntoView |
| 14 | 行业热门股 limit 20 | ✅ HOT_LIMIT=20 (IndustryHotView 已有), ComprehensiveAnalysisView.vue 改为 20 |
| 15 | loading/empty/error 状态 | ✅ 3 态均覆盖 |
| 16 | i18n 6 语言 ind_blocks_* + ind_unknown | ✅ 全补齐 |
| 17 | npm run build | ✅ 195 modules |
| 18 | python compileall | ✅ 0 errors |
| 19 | alembic current | ✅ c5e9f12a3b87 (head) |

---

## Phase M48：行业热股查看更多与首页 Loading Polish

**日期：** 2026-06-11  
**构建：** ✅ 195 modules, 0 errors

### 改动内容

| 改动 | 文件 | 说明 |
|------|------|------|
| HOT_LIMIT 20 → 50 | IndustryHotView.vue | 单次 fetch 50，前端 slice 控制展示 |
| expandedView + displayedItems | IndustryHotView.vue | 默认 slice(0,20)，展开显示全部 |
| toggleExpand + reset on change | IndustryHotView.vue | 切换行业自动收起 |
| 股票列表头部 + 切换按钮 | IndustryHotView.vue | ihv-stocks-header / ihv-more-btn |
| 底部收起按钮 | IndustryHotView.vue | 展开 > 10 条时底部显示 |
| 行业块加载文案 | HomeDashboardPanel.vue | `ind_loading_heat` 补充文字 |
| i18n 9 个新 key | 6 locales | ind_loading_heat/ind_hot_view_more/ind_hot_collapse/ind_hot_top_20/ind_hot_top_50/ind_hot_showing |

### M48 验证项

| # | 验证点 | 结果 |
|---|--------|------|
| 1 | 默认显示 Top 20 股票（slice） | ✅ HOT_DISPLAY_DEFAULT=20 |
| 2 | 点击"查看更多"展开 Top 50 | ✅ expandedView=true |
| 3 | "收起"恢复 Top 20 | ✅ expandedView=false |
| 4 | 切换行业自动收起 | ✅ onIndustryChange reset |
| 5 | 股票数 ≤ 20 不显示按钮 | ✅ v-if="filteredItems.length > 20" |
| 6 | 显示计数 "显示 N / total 支" | ✅ ind_hot_showing param |
| 7 | 底部收起按钮（展开 > 10 条） | ✅ ihv-bottom-bar |
| 8 | 行业热度加载文案 | ✅ ind_loading_heat |
| 9 | 首页空状态：报告/自选/热股/板块 | ✅ 全部已有空状态 |
| 10 | 6 语言 i18n 覆盖 | ✅ zh-CN/en-US/zh-TW/ja-JP/ko-KR/es-ES |
| 11 | /industries?focus=<code> 回归 | ✅ 未改动 focus 逻辑 |
| 12 | npm run build | ✅ 195 modules |
| 13 | python compileall | ✅ 0 errors |
| 14 | alembic current | ✅ c5e9f12a3b87 (head) |
| 15 | 零新依赖，零 migration | ✅ |

---

## Phase M49：自选股批量对比入口优化

**日期：** 2026-06-11  
**构建：** ✅ 195 modules, 0 errors

### 改动内容

| 改动 | 文件 | 说明 |
|------|------|------|
| `useRoute` + `mode=compare` 自动进入批量模式 | WatchlistView.vue | route.query.mode === 'compare' → bulkMode=true |
| "批量对比"入口按钮 | HomeDashboardPanel.vue | 自选快跳底部，≥2 股才显示 |
| `go-watchlist-compare` emit + handler | HomeDashboardPanel.vue + ComprehensiveAnalysisView.vue | router.push('/watchlist?mode=compare') |
| `dash_compare_bulk` key | 6 locales | 中英日韩西繁 |

### 已有功能确认（M17 已实现）

| 功能 | 文件 | 状态 |
|------|------|------|
| WatchlistToolbar 批量选择按钮 | WatchlistToolbar.vue | ✅ wl_tb_bulk |
| "加入对比"按钮 disabled < 2 or > 4 | WatchlistToolbar.vue | ✅ :disabled="selectedCount<2\|\|>4" |
| selectedCount 展示 | WatchlistToolbar.vue | ✅ wl_tb_selected {count} |
| "清空选择" "退出批量" | WatchlistToolbar.vue | ✅ |
| handleCompare() → /compare?stocks=... | WatchlistView.vue | ✅ |
| StockCompareView URL 解析 | StockCompareView.vue | ✅ |

### M49 验证项

| # | 验证点 | 结果 |
|---|--------|------|
| 1 | 综合分析页自选快跳显示"批量对比"入口（≥2 只时） | ✅ |
| 2 | 点击"批量对比" → /watchlist?mode=compare | ✅ |
| 3 | WatchlistView 自动进入批量选择模式 | ✅ route.query.mode |
| 4 | 勾选 < 2 只，"加入对比"按钮 disabled | ✅ :disabled |
| 5 | 勾选 2-4 只，"加入对比"可用 | ✅ |
| 6 | 点击"加入对比" → /compare?stocks=CN:000001,... | ✅ handleCompare() |
| 7 | StockCompareView 自动加载所选股票 | ✅ URL query 解析 |
| 8 | 勾选 > 4 只，"加入对比"按钮 disabled | ✅ :disabled > 4 |
| 9 | "清空选择" "退出批量"可用 | ✅ |
| 10 | 自选快跳 < 2 只时不显示入口 | ✅ v-if ≥ 2 |
| 11 | 原有自选管理（添加/删除/备注）不受影响 | ✅ 未改动相关逻辑 |
| 12 | 6 语言 dash_compare_bulk 覆盖 | ✅ |
| 13 | npm run build | ✅ 195 modules |
| 14 | python compileall | ✅ 0 errors |
| 15 | alembic current | ✅ c5e9f12a3b87 |

---

## Phase M50：A 股全量行业归类与行业页数据扩容（2026-06-11）

### 根本原因定位

| 问题 | 位置 | 说明 |
|------|------|------|
| 行业页只显示 5 支 | `industry_hot_stock_snapshot` 表 | `refresh_industry_hot_stocks.py` 历史上以 `--top-n 5`（默认值）运行，快照只存 rank 1-5 |
| API 返回 5 是数据问题 | `industry_hot_stock_service.py` | `rank <= limit` 过滤，但快照里只有 rank 1-5 |
| 前端请求 limit=50 但只得到 5 | 数据链路 | 数据瓶颈在 DB，非前端问题 |
| 历史上 `--top-n 5` 触发原因 | `scripts/refresh_industry_hot_stocks.py` | argparse default=5，未显式传 --top-n |

### 修复内容

| 修改 | 文件 | 说明 |
|------|------|------|
| 重新运行刷新脚本 `--top-n 50` | 数据层 | 30/30 行业写入 Top-50 快照 |
| 修复 symbol 重复 bug | `refresh_industry_hot_stocks.py` | candidates 按 symbol 去重，避免 UniqueViolation |
| 后端 `le=50` → `le=100` | `industry.py` router | 为未来 Top-100 留余量 |
| 服务层默认 `limit=5` → `limit=20` | `industry_hot_stock_service.py` | 默认返回 Top 20 |
| 新增 `total` 字段 | `HotStockResponse`, service | 行业在 stock_industry_map 中的真实成分股总数 |
| 前端用 `hotData.total` 显示总数 | `IndustryHotView.vue` | "显示 20 / 369 支" 格式 |
| API 默认 limit 5→20 | `api/industries.js` | `getIndustryHotStocks` 默认 limit |

### DB 数据统计（2026-06-11）

| 指标 | 数量 |
|------|------|
| stock_master 总数 | 5196 |
| CN（A股）股票数 | 5166 |
| HK 股票数 | 30 |
| industry_master 行业数 | 32 |
| stock_industry_map 映射总数 | 5185 |
| 有行业标签的 A 股数 | 5166（覆盖率 ~100%） |
| 无行业标签的 A 股数 | ≈0（极少） |

### 行业热股快照数量（刷新后 Top 代表行业）

| 行业 | 快照股票数 | 行业成分股总数 |
|------|-----------|--------------|
| 电力设备 | 50 | 369 |
| 计算机 | 50 | 334 |
| 医药生物 | 50 | 336 |
| 银行 | 42 | 42 |
| 综合 | 14 | ~14 |

### M50 验证项

| # | 验证点 | 结果 |
|---|--------|------|
| 1 | 行业页默认显示 Top 20 | ✅ HOT_DISPLAY_DEFAULT=20 |
| 2 | 点击"查看更多"展开到 Top 50 | ✅ expandedView toggle |
| 3 | 显示格式："显示 N / industry_total 支" | ✅ hotData.total |
| 4 | 主流行业可看到 50 支热股 | ✅ 电力设备/计算机等 50 支 |
| 5 | 冷门行业显示真实数量 | ✅ 综合 14 支/钢铁 43 支 |
| 6 | API total 字段返回行业成分股总数 | ✅ 电力设备=369 |
| 7 | 后端 limit 最大 100 | ✅ le=100 |
| 8 | /industries?focus=<code> 仍正常 | ✅ 未改动 |
| 9 | npm run build | ✅ 195 modules |
| 10 | python compileall | ✅ 0 errors |
| 11 | alembic current | ✅ c5e9f12a3b87 |
| 12 | 零新依赖 / 零 migration | ✅ |

---

## Phase M51-b reportText.js extractSummary 修复验证（2026-06-12）

**问题：** LLM 生成 en-US 报告时将 `### 摘要结论` 翻译为 `### Summary & Conclusions`（含 "&"），而旧 `extractSummary()` 仅匹配 `### Summary Conclusion`，导致 en-US 单面报告摘要提取回落到 `I. Summary`（样板包装文字），返回 "This report analyzes..." 而非实际 Agent 结论。

**修复：** `frontend/src/utils/reportText.js` `extractSummary()` en-US 路径新增 4 个变体：

```javascript
const m3b = _extract('### Summary & Conclusions')  // LLM 最常用变体
const m3c = _extract('### Summary & Conclusion')
const m3d = _extract('### Summary Conclusions')
const m3e = _extract('### Summary')                 // 广播兜底（任何 Summary 子节）
```

**验证结果（8/8 PASS）：**

| # | 测试用例 | 结果 |
|---|---------|------|
| 1 | `### Summary & Conclusions` 变体命中 | ✅ |
| 2 | `### Summary Conclusion` 精确匹配保留 | ✅ |
| 3 | `### Summary Conclusions` 变体命中 | ✅ |
| 4 | `### Summary & Conclusion` 变体命中 | ✅ |
| 5 | zh-CN `### 摘要结论` 回归 | ✅ |
| 6 | zh-CN `一、综合结论卡片` 回归 | ✅ |
| 7 | Legacy `I. Summary` 回归 | ✅ |
| 8 | 无 `###` 时 `I. Summary` 正常回落 | ✅ |

**静态检查：** npm run build ✅ 195 modules / python compileall ✅ 0 errors
