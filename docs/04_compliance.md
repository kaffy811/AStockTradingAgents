# 04_compliance.md — 合规与数据使用规范

> 版本：v1.0  
> 日期：2026-07-04

---

## 一、数据源合规边界

### 1.1 允许使用的数据源

| 数据源       | 使用方式                          | 合规依据                              |
|------------|----------------------------------|--------------------------------------|
| Tushare Pro | 付费 API（Token 认证），官方接口   | 已订阅付费服务，符合 Tushare 使用条款  |
| AkShare     | 开源库封装，非直接 scraping       | MIT 协议，使用公开金融接口             |
| 东方财富 (AkShare 封装) | 通过 AkShare 官方接口  | 通过 AkShare 中间层，非直接 scraping  |
| 同花顺 (AkShare 封装)  | 通过 AkShare 官方接口  | 同上                                  |

### 1.2 明确禁止的数据源

| 数据源              | 禁止原因                            |
|-------------------|------------------------------------|
| **aicaibao.com**  | 明确禁止，版权风险，数据来源不明       |
| 东方财富直接 scraping | 会触发反爬，已知 _em 系列接口损坏    |
| 雪球直接 scraping   | 需要 cookie 认证，条款禁止爬取       |
| 同花顺直接 scraping  | 同上                               |

**实施**：`aicaibao.com` 不出现在任何 HTTP 请求 URL 中。代码审查时自动 grep 检查。

---

## 二、投资建议免责声明

所有 API 响应（包括 AI 模块）**必须**包含免责声明：

### 2.1 非 AI 模块（M01-M23）

HTTP 响应头：
```
X-Data-Disclaimer: 本页面数据仅供参考，不构成投资建议。投资有风险，入市需谨慎。
```

### 2.2 AI 模块（M_AI）

响应 body 必须包含 `disclaimer` 字段（参见 `03_cost_and_refresh.md`）：
```json
{
  "rating": "...",
  "disclaimer": "本分析由 AI 模型生成，仅供参考，不构成投资建议。"
}
```

`rating` 字段不得使用"强烈推荐买入"等强诱导性语言，仅允许：`买入 / 持有 / 卖出 / 观望`。

---

## 三、用户数据处理

### 3.1 个人数据

本服务不收集用户的持仓数据或真实资金信息。自选股数据（watchlist）：
- 存储于用户账户的 PostgreSQL 记录中
- 不对外共享，不用于训练 AI 模型

### 3.2 查询记录

用户查看股票基本面的行为记录（symbol + timestamp）：
- 仅用于"最近查看"功能（Session 级别，不长期存储）
- 不用于广告定向或数据变现

### 3.3 缓存数据归属

Redis 缓存的市场数据（行情、财报）属于公开金融数据，不含个人隐私，无 GDPR 合规问题。

---

## 四、Tushare Token 安全

Tushare Pro Token 是付费凭证，安全要求：

1. **禁止提交 `.env` 文件**：`.gitignore` 已包含 `.env`，CI 检查不得打印 TUSHARE_TOKEN
2. **环境变量注入**：生产环境通过 Docker secrets 或平台环境变量注入，不硬编码
3. **Token 轮换**：Token 泄漏后立即在 Tushare 控制台重新生成，重启服务
4. **日志脱敏**：`tushare_client.py` 在日志中仅打印 Token 的前 6 位，例如：`token=abc123***`

配置示例（`.env.example`，无真实 token）：
```
TUSHARE_TOKEN=your_tushare_pro_token_here
ENABLE_AKSHARE=false
```

---

## 五、数据准确性免责

Tushare 和 AkShare 提供的数据可能存在延迟或误差：

1. 实时行情（M01）：延迟约 15 分钟（免费账户），付费账户近实时
2. 财报数据：以交易所公告为准，Tushare 可能有 1-2 天录入延迟
3. 研报评级（M19）：仅收录主流券商，不保证完整性

服务在所有涉及价格的响应中注明：
```json
"data_note": "行情数据可能存在延迟，以交易所官方数据为准。"
```

---

## 六、开源组件许可证

| 组件         | 版本      | 许可证      | 是否可商用 |
|------------|---------|-----------|----------|
| AkShare    | ≥1.18   | MIT       | 是        |
| Tushare    | ≥1.4.20 | BSD-3     | 是        |
| FastAPI    | ≥0.136  | MIT       | 是        |
| pandas     | ≥3.0    | BSD-3     | 是        |
| Redis-py   | ≥7.4    | MIT       | 是        |
| ECharts    | ≥5.x    | Apache-2  | 是        |
| Vue 3      | ≥3.x    | MIT       | 是        |

所有使用的开源库均为商业友好许可证。

---

## 七、代码审查检查清单

每次 PR 合并前确认以下合规项：

- [ ] 没有 `aicaibao.com` URL（`grep -r "aicaibao" backend/`）
- [ ] TUSHARE_TOKEN 没有硬编码（`grep -r "TUSHARE_TOKEN" backend/app/` 无明文 token）
- [ ] AI 模块响应包含 `disclaimer` 字段
- [ ] 非 AI 模块无 LLM 调用（`grep -r "llm\|deepseek\|openai" backend/app/tools/fundamental/` 无调用）
- [ ] `.env` 不在 git 追踪范围内（`git ls-files .env` 返回空）
- [ ] AkShare 调用有 ENABLE_AKSHARE guard（`grep -r "akshare" backend/app/datasource/akshare_client.py`）
