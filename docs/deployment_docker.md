# Phase D1 — Docker 部署指南

**版本：** MVP v0.8  
**架构：** Frontend Nginx + Backend FastAPI + Redis（Supabase 云端 PostgreSQL）  
**更新日期：** 2026-05-30

---

## 架构概览

```
浏览器 / 小程序 / App
        │
        ▼ :80
┌─────────────────────────────────────────────────────┐
│  Docker Compose                                      │
│                                                      │
│  frontend (nginx:alpine)                             │
│  ├── GET /          → serve dist/ (Vue SPA)          │
│  └── /api/v1/*      → proxy → backend:8000           │
│                              │                       │
│  backend (python:3.12-slim)  │                       │
│  ├── FastAPI + uvicorn       │                       │
│  └── → redis:6379            │                       │
│                              │                       │
│  redis (redis:7-alpine)      │                       │
│  └── 仅内网，不对外暴露       │                       │
└─────────────────────────────────────────────────────┘
        │
        ▼ (外部云端)
Supabase PostgreSQL
（不在 Docker Compose 中自托管）
```

**设计原则：**
- 只有 `frontend:80` 对外暴露，`backend` 和 `redis` 仅在内部 Docker 网络可见
- 浏览器通过 Nginx 同源访问 `/api/v1`，不产生 CORS 跨域请求
- `VITE_API_BASE=/api/v1`（相对路径）在 build 时注入 JS bundle，镜像可跨域名复用
- PostgreSQL 继续使用 Supabase 托管，Docker Compose 不管理数据库生命周期

---

## 前提条件

- Docker Engine ≥ 24
- Docker Compose v2（`docker compose` 命令，不是旧版 `docker-compose`）
- Supabase 项目已创建，获取 Transaction Pooler 连接字符串（端口 6543）
- DeepSeek API Key

---

## 推荐生产启动顺序

> **为什么分步？** `migrate` 是一次性 Alembic 容器，必须在 `backend` 启动前完成 schema 迁移，否则 FastAPI 启动时可能因表不存在而报错。

### 首次部署（全新服务器）

```bash
# 1. 克隆项目、准备环境变量
git clone <repo>
cd TradingAgents
cp .env.example .env
# 编辑 .env，填入 DATABASE_URL、SECRET_KEY、DEEPSEEK_API_KEY

# 2. 构建所有镜像
docker compose build

# 3. 启动 Redis（migrate 依赖它做健康检查）
docker compose up -d redis

# 4. 运行 Alembic 迁移（成功后容器自动退出）
docker compose run --rm migrate

# 5. 启动应用服务
docker compose up -d backend frontend
```

迁移输出示例（成功）：

```
INFO  [alembic.runtime.migration] Running upgrade  -> 4b49004d01a6, baseline: existing schema
```

### 后续部署（代码更新 + 可能含 schema 变更）

```bash
git pull
docker compose build          # 重新构建有变化的镜像
docker compose run --rm migrate   # 应用新迁移（幂等，无新迁移时无操作）
docker compose up -d          # 滚动更新所有服务
```

### 日常重启（无代码变更）

```bash
docker compose up -d
```

---

## 首次部署步骤（开发环境 / 快速验证）

### 1. 克隆项目并准备环境变量

```bash
git clone <repo>
cd TradingAgents

# 从模板复制 .env
cp .env.example .env
```

### 2. 填写 `.env`

用编辑器打开 `.env`，至少填写以下三项（其余可保留默认值）：

```dotenv
# Supabase Transaction Pooler URL（端口 6543）
DATABASE_URL=postgresql+asyncpg://user:password@host:6543/postgres

# JWT 密钥，64 字符随机串
# 生成命令：python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your-64-char-random-secret

# DeepSeek API Key
DEEPSEEK_API_KEY=sk-your-key
```

> **注意：** `CORS_ORIGINS` 必须是 JSON 数组格式，不能是逗号分隔字符串（见常见问题 5）。

### 3. 构建并启动（含迁移）

```bash
# 生产推荐：分步执行迁移（见上方"推荐生产启动顺序"）
docker compose build
docker compose up -d redis
docker compose run --rm migrate
docker compose up -d backend frontend
```

### 4. 验证部署

```bash
# 前端可访问
curl http://localhost/

# 后端健康检查（通过 Nginx 代理）
curl http://localhost/api/v1/health

# 查看所有容器状态
docker compose ps

# 实时查看后端日志
docker compose logs -f backend

# Redis 连通性
docker compose exec redis redis-cli ping
# 预期输出：PONG
```

---

## 浏览器端验证清单

打开 `http://localhost`，按以下顺序验证：

| # | 操作 | 预期结果 |
|---|------|---------|
| 1 | 打开首页 | 显示登录界面，无 Console 报错 |
| 2 | 注册 / 登录 | 成功，跳转综合分析页 |
| 3 | 分析 CN/600519 | 约 35–45s 返回分析报告 |
| 4 | 技术面图表 | K线 + MA + 成交量图表显示 |
| 5 | 保存报告 | 保存成功，显示"已保存" |
| 6 | 打开历史报告 | 报告详情页含图表和正文 |
| 7 | 自选股页面 | 添加 CN/600519，卡片显示 |
| 8 | DevTools Network | 所有 `/api/v1/*` 请求 HTTP 200，无 `CORS policy` 红字 |
| 9 | DevTools Console | 无红色 JS error，无 Vue warning |

---

## 日常运维

```bash
# 停止（保留数据卷）
docker compose down

# 停止并删除所有卷（Redis 缓存清空）
docker compose down -v

# 只重启某个服务
docker compose restart backend

# 强制重新构建某个服务（不影响其他服务）
docker compose build --no-cache frontend
docker compose up -d frontend

# 查看所有日志
docker compose logs -f

# 进入容器调试
docker compose exec backend bash
docker compose exec redis redis-cli
```

---

## 常见问题

### 1. 前端仍然请求 `http://localhost:8000/api/v1`

**原因：** `VITE_API_BASE` 在 build 时没有正确注入，JS bundle 用了 `http.js` 中的 fallback 值。

**排查：**

```bash
# 检查 dist 中的实际 API base URL
docker compose exec frontend grep -r "api/v1" /usr/share/nginx/html/assets/*.js | head -3
# 应看到 "/api/v1"，而不是 "http://localhost:8000/api/v1"
```

**修复：**

```bash
docker compose build --no-cache frontend
docker compose up -d frontend
```

---

### 2. `/api/v1` 返回 404，或路径变成 `/api/v1/api/v1/...`

**原因：** `nginx.conf` 中 `proxy_pass` 路径写错。

**错误写法（会导致路径重复）：**
```nginx
location /api/v1/ {
    proxy_pass http://backend:8000/api/v1;  ← 错
}
```

**正确写法：**
```nginx
location /api/v1/ {
    proxy_pass http://backend:8000;  ← 正确，不加路径
}
```

**检查：**
```bash
docker compose exec frontend cat /etc/nginx/conf.d/default.conf
```

---

### 3. Redis 不可用

```bash
# 检查 Redis 容器状态
docker compose ps redis

# 检查 Redis 是否响应
docker compose exec redis redis-cli ping

# 查看 backend 日志中的 Redis warning
docker compose logs backend | grep -i redis
```

后端在 Redis 不可用时会静默降级（无缓存运行），不会崩溃。  
若 Redis 容器健康但 backend 连不上，确认 `REDIS_URL=redis://redis:6379`（服务名必须是 `redis`）。

---

### 4. Supabase 数据库连接失败

常见错误日志：
```
asyncpg.exceptions.InvalidPasswordError: password authentication failed
asyncpg.exceptions.TooManyConnectionsError
sqlalchemy.exc.OperationalError: connection refused
```

排查步骤：
1. 确认 `DATABASE_URL` 格式：`postgresql+asyncpg://user:password@host:6543/postgres`
2. 确认使用 **Transaction Pooler 端口 6543**，不是 Direct Connection 5432
3. 在 Supabase Dashboard → Settings → Database → Connection Pooling 复制完整 URL
4. 免费版连接数上限 60，容器重启频繁时注意连接未释放

---

### 5. `CORS_ORIGINS` 解析失败导致 backend 启动报错

**错误日志：**
```
pydantic_settings.errors: error parsing value for field "cors_origins" from source "EnvSettingsSource"
```

**原因：** `CORS_ORIGINS` 必须是 JSON 数组格式。

```dotenv
# 正确
CORS_ORIGINS=["http://localhost","https://yourdomain.com"]

# 错误（逗号分隔字符串不被接受）
CORS_ORIGINS=http://localhost,https://yourdomain.com
```

---

### 6. Alembic 迁移管理（D2-c 已完成）

Alembic 已接入（baseline revision `4b49004d01a6`）。生产部署应使用 Alembic 而非 `create_all`。

#### 6.1 首次部署（全新空数据库）

```bash
# 数据库为空，运行所有迁移
docker compose exec backend uv run alembic upgrade head
```

#### 6.2 已有数据库迁移到 Alembic 管理（一次性操作）

```bash
# 数据库已由 create_all 建立，stamp 告诉 Alembic 当前状态已是最新版本
docker compose exec backend uv run alembic stamp head
```

#### 6.3 后续表结构变更标准流程

```bash
# 1. 在本地修改 ORM model 后，生成 migration
cd backend
uv run alembic revision --autogenerate -m "add foo column to bar table"

# 2. 检查生成文件（backend/alembic/versions/）
#    确保没有误生成 drop_table / drop_column
#    如有误生成，立即停止，不要 upgrade

# 3. 应用到生产 DB
docker compose exec backend uv run alembic upgrade head

# 4. 验证
docker compose exec backend uv run alembic current
```

#### 6.4 运维命令速查

```bash
# 查看当前版本
docker compose exec backend uv run alembic current

# 查看迁移历史
docker compose exec backend uv run alembic history --verbose

# 回滚一步
docker compose exec backend uv run alembic downgrade -1

# 离线生成 SQL（不连接 DB）
uv run alembic upgrade head --sql
```

#### 6.5 create_all 与 Alembic 的边界

| 场景 | 推荐方式 |
|------|---------|
| 本地开发（`ENABLE_CREATE_ALL=true`，默认） | `create_all` 自动创建新表，快速开发 |
| 生产部署（`ENABLE_CREATE_ALL=false`） | `alembic upgrade head` 精确控制每次变更 |
| 表结构变更（新增列/重命名/删列） | 必须用 Alembic；`create_all` 不处理已有表结构 |
| 全新 schema 初始化 | `alembic upgrade head`（包含 baseline revision） |

> ⚠️ **注意**：不要直接修改已存在的列定义，除非同步创建 Alembic migration。

---

## 环境变量参考

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `DATABASE_URL` | ✅ 必需 | — | Supabase Transaction Pooler URL，`postgresql+asyncpg://...` |
| `SECRET_KEY` | ✅ 必需 | — | JWT 密钥，≥16 字符，推荐 64 字符随机串 |
| `DEEPSEEK_API_KEY` | ✅ 必需 | — | LLM 分析必须 |
| `REDIS_URL` | 推荐 | `redis://localhost:6379` | Docker 内覆盖为 `redis://redis:6379` |
| `APP_ENV` | 推荐 | `development` | 设为 `production` |
| `DEBUG` | 推荐 | `true` | 设为 `false` 关闭 SQLAlchemy echo |
| `ENABLE_CREATE_ALL` | 推荐 | `true` | 生产设为 `false`，用 Alembic 管理 schema |
| `CORS_ORIGINS` | 推荐 | `["*"]` | JSON 数组格式，生产设为具体域名 |
| `LLM_PROVIDER` | 可选 | `deepseek` | — |
| `DEEPSEEK_BASE_URL` | 可选 | `https://api.deepseek.com` | — |
| `OPENAI_API_KEY` | 可选 | — | 不用 OpenAI 时留空 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 可选 | `60` | — |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 可选 | `30` | — |

---

## D2-f 一键验证脚本

`scripts/deploy_smoke_check.sh` 是配套 Docker 环境的完整验证脚本，在 Docker Engine 安装就绪后直接运行。

### 运行方式

```bash
# 从仓库根目录运行
cd /path/to/TradingAgents
chmod +x scripts/deploy_smoke_check.sh
./scripts/deploy_smoke_check.sh
```

### 脚本执行逻辑（9 个步骤）

| 步骤 | 内容 | 失败处理 |
|------|------|---------|
| 1 | 检查 docker、docker compose v2、curl 是否存在 | docker/compose 缺失则立即 abort |
| 2 | 检查 `.env` 存在，检测 DATABASE_URL / SECRET_KEY / DEEPSEEK_API_KEY 是否仍为 placeholder | 检测到 placeholder 则 abort（不会打印真实值） |
| 3 | `docker compose config` 验证 YAML 语法和环境变量插值 | 失败则 abort |
| 4 | `docker compose build` 构建所有镜像 | 失败则 abort |
| 5 | `up -d redis` → `run --rm migrate` → `up -d backend frontend` | migrate 失败记录但不 abort（继续检查 Nginx） |
| 6 | `docker compose ps` 打印容器状态 | 仅展示 |
| 7 | `curl localhost/`、`curl localhost/api/v1/health`、`redis-cli ping` | 失败记录到 FAIL 列表 |
| 8 | 扫描 frontend JS bundle 是否含 `localhost:8000` | 发现则 FAIL |
| 9 | 输出 PASS / FAIL 汇总 + 失败项列表 | — |

### 预期输出（全通过）

```
TradingAgents — Docker Deploy Smoke Check
Working directory: /path/to/TradingAgents
Started: 2026-06-01 10:00:00

Step 1 — Pre-flight: toolchain
  ✓  docker found (server version: 27.x.x)
  ✓  docker compose v2 found (2.x.x)
  ✓  curl found

Step 2 — Pre-flight: .env file
  ✓  .env file exists
  ✓  DATABASE_URL is set (value hidden)
  ✓  SECRET_KEY is set (value hidden)
  ✓  DEEPSEEK_API_KEY is set (value hidden)
  ✓  ENABLE_CREATE_ALL=false (production mode)
  ✓  CORS_ORIGINS appears to be JSON array format

Step 3 — Validate docker compose config
  ✓  docker compose config OK — YAML is valid, all env vars interpolated

Step 4 — Build images
  ✓  docker compose build completed successfully

Step 5 — Start stack (redis → migrate → backend + frontend)
  ✓  redis is healthy
  ✓  migrate completed successfully (exit 0)
  ✓  backend is reachable via Nginx proxy

Step 7 — Health checks
  ✓  Frontend: HTTP 200
  ✓  Backend health: HTTP 200 — {"status":"ok"}
  ✓  Redis: PONG

Step 8 — Frontend bundle check (no hardcoded localhost:8000)
  ✓  Bundle clean — no 'localhost:8000' found in JS assets
  ✓  Bundle contains '/api/v1' — VITE_API_BASE correctly injected

Step 9 — Summary
✓ PASS — All checks passed. Stack is healthy.
```

### 常见失败原因

| 失败信息 | 原因 | 修复 |
|---------|------|------|
| `DATABASE_URL still contains a placeholder` | .env 未填写真实 Supabase URL | 编辑 .env，填入 Transaction Pooler URL（端口 6543） |
| `migrate failed (exit 1)` | DB 连接失败 / 密码错误 | `docker compose logs migrate`，检查 DATABASE_URL |
| `Frontend: HTTP 502` | backend 还在启动 | 等待 10s 后重试；`docker compose logs backend` |
| `bundle contains localhost:8000` | VITE_API_BASE 未注入 | `docker compose build --no-cache frontend` 后重试 |
| `bundle missing /api/v1` | 同上 | 同上 |
| `Redis: FAILED` | redis 容器未就绪 | `docker compose logs redis`；`docker compose exec redis redis-cli ping` |

### 查看各服务日志

```bash
# 实时跟踪所有服务
docker compose logs -f

# 按服务查看
docker compose logs backend   # FastAPI 启动错误 / DB 连接错误
docker compose logs frontend  # Nginx 访问日志 / 配置错误
docker compose logs migrate   # Alembic 迁移输出（失败时最重要）
docker compose logs redis     # Redis 启动日志

# 只看最近 50 行
docker compose logs --tail=50 backend
```

---

## 下一步（D2 计划）

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| D2-a | HTTPS + 域名：Nginx 接入 Let's Encrypt（Certbot）或托管平台 SSL | 高 |
| D2-b | Alembic 迁移：替换 `create_all`，建立 migration history | ✅ D2-c 已完成 |
| D2-c | Alembic `migrate` service + 生产启动流程收口 | ✅ D2-d 已完成 |
| D2-e | 静态审计（nginx `^~`、Dockerfile alembic 复制）| ✅ D2-e 已完成 |
| D2-f | 一键验证脚本 `scripts/deploy_smoke_check.sh` | ✅ D2-f 已完成（待 Docker 环境执行） |
| D2-g | CI/CD：GitHub Actions `docker compose build + push` | 中 |
| D2-h | 云主机部署：阿里云 / 腾讯云 ECS，或 Railway / Render | 中 |
| D2-i | Redis persistence：AOF 持久化，防止容器重启后缓存完全冷启动 | 低 |
| D2-j | 多 worker / 水平扩缩：uvicorn workers 或 Kubernetes replica | 低 |
