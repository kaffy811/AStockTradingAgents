# TradingAgents — 安全检查清单

> 版本：M24 最终部署准备（2026-06-06）  
> 用途：部署前安全审计、代码审查、交接文档

---

## 一、密钥管理

### 1.1 环境变量

| 检查项 | 状态 | 说明 |
|--------|------|------|
| `.env` 未提交到 Git | ✅ | `.gitignore` 中有 `.env` |
| `.env.example` 只含 placeholder | ✅ | 无真实值 |
| `backend/.env.example` 只含 placeholder | ✅ | 无真实值 |
| `frontend/.env.example` 只含 `VITE_API_BASE` | ✅ | 无密钥 |
| `frontend/.env.production.example` 只含路径 | ✅ | 无密钥 |
| 文档中无真实密钥 | ✅ | docs/ 仅 placeholder |

### 1.2 SECRET_KEY（JWT 签名密钥）

- **生产必须更换**：不得使用 `change-this-to-a-random-64-char-string`
- 生成方式：`python3 -c "import secrets; print(secrets.token_hex(32))"`
- 最小长度：16 字符；推荐：64 字符
- 密钥轮换：轮换后所有已发行 JWT 立即失效（用户需重新登录）

### 1.3 DATABASE_URL

- 使用 Supabase **Transaction Pooler**（端口 6543），不使用 Direct Connection（端口 5432）
- 连接字符串格式：`postgresql+asyncpg://user:password@host:6543/postgres`
- 密码应足够复杂（Supabase 自动生成的密码满足要求）
- 不得在代码、日志、文档中打印连接字符串

### 1.4 DEEPSEEK_API_KEY / OPENAI_API_KEY

- 存储在 `.env`，后端通过 `pydantic-settings` 读取
- 不得在前端代码或 bundle 中暴露（前端无 LLM 直连）
- 不得在日志中打印

---

## 二、.gitignore 覆盖范围

当前 `.gitignore`（根目录）覆盖：

```
# Python
__pycache__/
*.py[cod]
.venv/
.env          ← 覆盖所有子目录的 .env

# IDE
.vscode/
.idea/

# OS
.DS_Store

# Node / frontend
node_modules/
dist/
build/

# Cache
.pytest_cache/
.mypy_cache/
.ruff_cache/
```

`frontend/.gitignore` 额外覆盖：`node_modules/ dist/ .env *.local`

**验证命令：**

```bash
# 确认 .env 未被 track
git ls-files backend/.env frontend/.env .env

# 确认 dist/ 未被 track
git ls-files frontend/dist | head -3

# 确认 node_modules/ 未被 track
git ls-files frontend/node_modules | head -3

# 预期：以上命令无输出
```

---

## 三、代码安全

### 3.1 前端

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 无 LLM API Key 暴露在前端 | ✅ | 前端无直连 LLM |
| 无数据库连接字符串 | ✅ | 前端只调用后端 REST API |
| Markdown 渲染 XSS 防护 | ✅ | `marked` + `DOMPurify` |
| `VITE_API_BASE` 为相对路径（生产） | ✅ | `/api/v1` 不含域名 |
| 前端 bundle 无 `localhost:8000` 硬编码 | ✅ | Docker build 时注入 `/api/v1` |

### 3.2 后端

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 密钥从环境变量读取（pydantic-settings） | ✅ | `backend/app/core/config.py` |
| 无硬编码 SECRET_KEY | ✅ | 已验证 config.py |
| 无硬编码 DATABASE_URL | ✅ | 已验证 config.py |
| JWT 验证中间件正确 | ✅ | 受保护路由需有效 token |
| CORS_ORIGINS 白名单（非 `*`） | ✅ | `.env.example` 示例为具体域名 |
| SQL 注入防护 | ✅ | SQLAlchemy ORM 参数化查询 |
| Alembic 管理 schema（非 create_all） | ✅ | `ENABLE_CREATE_ALL=false` |

### 3.3 投资建议文案安全

| 检查项 | 状态 |
|--------|------|
| 前端 .vue 文件无"买入/卖出"等禁止词 | ✅ M23 审计通过，0 matches |
| 所有报告末尾有免责声明 | ✅ |
| HomeHeroPanel 有风险提示 | ✅ "仅供研究参考，不构成投资建议" |
| TechnicalInsightCard 无投资判断文案 | ✅ |
| StockMiniTrend 无投资建议 | ✅ |

---

## 四、日志安全

- **禁止**在日志中打印 JWT token、密码、API Key
- **禁止**在错误响应中向前端暴露 stack trace（生产模式下 FastAPI 返回通用错误信息）
- **允许**记录请求路径、status code、耗时（不含 auth header 值）

---

## 五、传输安全

- 生产部署应在 Nginx 前配置 HTTPS（证书可用 Let's Encrypt）
- 当前 Compose 配置仅 HTTP:80，适合内网/演示环境
- HTTPS 配置参见 `deployment_docker.md` §反向代理与 HTTPS

---

## 六、部署前安全检查项

```bash
# 1. 确认 .env 无 placeholder
grep -E "change-this|sk-your|user:password" .env && echo "PLACEHOLDER FOUND" || echo "OK"

# 2. 确认 .env 未被 git track
git ls-files .env backend/.env frontend/.env 2>/dev/null | wc -l
# 预期：0

# 3. 确认 dist/ 未被 track
git ls-files frontend/dist | wc -l
# 预期：0

# 4. 文案安全扫描（前端无禁止词）
grep -r "买入\|卖出\|强烈建议\|必涨\|必跌\|推荐股票" frontend/src --include="*.vue" 2>/dev/null | wc -l
# 预期：0

# 5. 前端 bundle 无 localhost:8000
grep -r "localhost:8000" frontend/dist/assets/ 2>/dev/null | wc -l
# 预期：0（生产 build 后）

# 6. 运行完整 deploy smoke check
./scripts/deploy_smoke_check.sh
```

---

## 七、已知限制与接受的风险

| 限制 | 说明 | 处理方式 |
|------|------|----------|
| HTTP only（无 HTTPS） | Compose 仅 :80 | 生产应加 HTTPS 反代 |
| 单 uvicorn worker | 单进程，无多核并行 | 可增加 `--workers N` 或水平扩展 |
| Redis 无密码 | 内部网络隔离 | 生产可配置 `requirepass` |
| JWT 无刷新黑名单 | 登出后 token 在 TTL 内仍有效 | 接受，TTL 已配置为合理时长 |
| 无速率限制 | 可能被爆破 | 生产建议在 Nginx 层配置限速 |

---

## M26 最终安全审计确认（2026-06-06）

### git check-ignore 结果

| 文件 | 状态 |
|------|------|
| `.env` | ✅ git ignored |
| `backend/.env` | ✅ git ignored |
| `frontend/dist` | ✅ git ignored |
| `__pycache__` | ✅ git ignored（via `*.pyc` / `__pycache__/`）|
| `node_modules` | ✅ git ignored |

### 前端文案安全扫描

```bash
grep -r "买入\|卖出\|强烈建议\|必涨\|必跌" frontend/src --include="*.vue" --include="*.js"
# 结果: 0 匹配
```

### 后端 prompt 扫描

```bash
grep -r "买入\|卖出\|强烈建议\|必涨\|必跌" backend/app --include="*.py"
# 结果: 仅在 prompt 的"禁止词清单"规则段落中出现，为限制性说明，非业务输出，✅ 合规
```

### 文档扫描

```bash
grep -r "guaranteed\|must buy\|must sell" docs/
# 结果: 0 匹配
```

### API Smoke Test 文档安全

- 所有 curl 示例使用 `<TOKEN>` placeholder，不打印真实 token ✅
- DATABASE_URL / SECRET_KEY / DEEPSEEK_API_KEY 在文档中仅以 placeholder 出现 ✅

### 日志安全

- `log.error` / `log.info` 无打印 token / SECRET_KEY / DATABASE_URL ✅（已在代码 review 中确认）

### M26 安全结论

本项目通过最终安全审计。部署前必须：
1. 在生产 `.env` 中设置真实 `SECRET_KEY`（最少 32 字节随机串）
2. 确认 `DATABASE_URL` 不出现在任何日志
3. 使用 HTTPS 访问生产环境
