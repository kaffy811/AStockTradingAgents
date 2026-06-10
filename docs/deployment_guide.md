# TradingAgents — 部署指南

> 版本：M24 最终部署准备（2026-06-06）  
> 适用场景：本地开发、生产 Docker 部署、面试演示

---

## 一、前提条件

| 工具 | 版本要求 | 说明 |
|------|----------|------|
| Docker Engine | ≥ 24 | 生产部署必需 |
| Docker Compose v2 | 内置于 Docker Desktop | `docker compose`（非旧版 `docker-compose`） |
| Python | ≥ 3.12 | 后端本地开发 |
| uv | 最新版 | Python 包管理器（`curl -LsSf https://astral.sh/uv/install.sh \| sh`） |
| Node.js | ≥ 20 | 前端本地开发 |
| Supabase 账号 | — | 云端 PostgreSQL（Transaction Pooler，端口 6543） |
| DeepSeek API Key | — | LLM 报告生成 |

---

## 二、本地开发启动

### 2.1 后端

```bash
cd backend

# 复制并填写环境变量
cp .env.example .env
# 编辑 .env，填写 DATABASE_URL / SECRET_KEY / DEEPSEEK_API_KEY

# 安装依赖（首次）
uv sync

# 执行数据库迁移（首次或有新 migration）
uv run alembic upgrade head

# 导入基础数据（首次）
uv run python scripts/import_industry_map.py
uv run python scripts/import_stock_master.py

# 启动（带热重载）
uv run uvicorn app.main:app --reload --port 8000
```

后端 API 文档：`http://localhost:8000/docs`

### 2.2 前端

```bash
cd frontend

# 安装依赖（首次）
npm install

# 启动开发服务器
npm run dev
# 默认：http://localhost:3001
```

开发模式下，前端直连后端 `http://localhost:8000/api/v1`（由 `frontend/.env` 中 `VITE_API_BASE` 控制）。

### 2.3 Redis（可选，本地开发）

```bash
# macOS
brew install redis && redis-server

# 或 Docker
docker run -d -p 6379:6379 redis:7-alpine
```

Redis 可选——后端在 Redis 不可用时降级到无缓存模式，不报错。

---

## 三、生产构建

### 3.1 前端生产构建

```bash
cd frontend
npm run build
# 产物在 dist/ 目录
# 当前：181 modules，~419 KB JS（gzip ~147 KB）
```

### 3.2 后端静态检查

```bash
cd /path/to/TradingAgents
python -m compileall backend/app -q
# 无输出 = 无语法错误
```

---

## 四、Docker Compose 部署

### 4.1 首次部署

```bash
# 在项目根目录
cp .env.example .env
# 填写 .env 中的以下字段（必需）：
#   DATABASE_URL    — Supabase Transaction Pooler URL（port 6543）
#   SECRET_KEY      — 64位随机字符串（见下方生成命令）
#   DEEPSEEK_API_KEY— DeepSeek API Key

# 生成 SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"

# 启动 Redis
docker compose up -d redis

# 执行数据库迁移
docker compose run --rm migrate

# 启动后端 + 前端
docker compose up -d backend frontend
```

访问 `http://localhost`（Nginx 在 80 端口提供服务）。

### 4.2 后续更新部署

```bash
git pull
docker compose build
docker compose run --rm migrate   # 仅当有新 migration 时必需
docker compose up -d
```

### 4.3 日常重启（无代码/schema 变更）

```bash
docker compose up -d
```

### 4.4 服务架构

```
浏览器 :80
  → frontend (nginx:alpine)
      ├── GET /         → Vue SPA (dist/)
      └── /api/v1/*     → proxy → backend:8000
                                → redis:6379 (内部)
                                → Supabase PostgreSQL (云端，不在 compose 中)
```

**安全设计：**
- 只有 `frontend:80` 对外暴露
- `backend` 和 `redis` 仅在内部 Docker 网络可见
- 浏览器同源访问 `/api/v1`，无 CORS 问题
- `VITE_API_BASE=/api/v1` 在 build 时注入，镜像可跨域名复用

详细文档参见 [`deployment_docker.md`](./deployment_docker.md)。

---

## 五、Alembic 数据库迁移

```bash
# 查看当前状态
uv run alembic current

# 查看所有 revision
uv run alembic history

# 升级到最新
uv run alembic upgrade head

# 降级（谨慎）
uv run alembic downgrade -1
```

**当前 migration 链：**

```
<base> → 4b49004d01a6 (baseline existing schema)
       → 76fe066db8b1 (add stock master)
       → 3a2f8b4c1d9e (add stock_name to analysis_reports)
       → a7c3f91e2b85 (add auto_saved to analysis_reports)
       → b4d8e2f1a6c9 (HEAD: add analysis_scope to analysis_reports)
```

- **单 head**，线性链，无分叉
- 空库执行 `alembic upgrade head` 安全
- 已有库通过 `alembic stamp head`（一次性）后正常运行

---

## 六、环境变量说明

### 必需变量

| 变量 | 说明 | 示例格式 |
|------|------|----------|
| `DATABASE_URL` | Supabase Transaction Pooler URL | `postgresql+asyncpg://user:pass@host:6543/postgres` |
| `SECRET_KEY` | JWT 签名密钥（≥ 16字符，生产建议 64字符） | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `DEEPSEEK_API_KEY` | DeepSeek LLM API Key | `sk-...` |

### 可选变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_ENV` | `production` | 环境标识 |
| `DEBUG` | `false` | 调试模式（生产必须 false） |
| `ENABLE_CREATE_ALL` | `false` | 生产必须 false，用 Alembic 管理 schema |
| `REDIS_URL` | `redis://redis:6379` | Redis 连接（Docker compose 内部 service name） |
| `LLM_PROVIDER` | `deepseek` | LLM 提供商 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API 基础 URL |
| `OPENAI_API_KEY` | 空 | OpenAI 备用（留空则不使用） |
| `CORS_ORIGINS` | `["http://localhost"]` | CORS 白名单，**必须为 JSON 数组格式** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT access token 有效期 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | JWT refresh token 有效期 |

**重要：** `CORS_ORIGINS` 必须是 JSON 数组：
```
# 正确
CORS_ORIGINS=["https://yourdomain.com","http://localhost"]

# 错误（会导致启动崩溃）
CORS_ORIGINS=https://yourdomain.com,http://localhost
```

---

## 七、部署验证

### 快速验证（推荐）

```bash
# 运行完整的 Docker Deploy Smoke Check
chmod +x scripts/deploy_smoke_check.sh
./scripts/deploy_smoke_check.sh
```

该脚本自动检查：
1. Docker / docker compose 版本
2. `.env` 存在且无 placeholder 值
3. `docker compose config` 验证
4. 镜像构建
5. Redis healthcheck
6. Alembic migration
7. 后端健康检查
8. 前端 bundle 无硬编码 `localhost:8000`

### 手动验证

```bash
# 后端健康检查
curl http://localhost/api/v1/health

# 前端
curl -s -o /dev/null -w "%{http_code}" http://localhost/
# 预期：200
```

---

## 八、常见问题

### Q1：DATABASE_URL 格式错误

使用 `postgresql+asyncpg://` 前缀（不是 `postgresql://`）。  
端口必须是 6543（Transaction Pooler），不是 5432（Direct Connection）。

### Q2：CORS_ORIGINS 导致启动崩溃

```
pydantic_core.ValidationError: CORS_ORIGINS must be a valid JSON array
```
修复：`CORS_ORIGINS=["http://localhost"]`（包含方括号和双引号）。

### Q3：Alembic `Multiple head revisions` 错误

```bash
uv run alembic heads  # 应该只有一个 head
```
当前项目为单线性 head，不应出现此错误。

### Q4：前端 bundle 硬编码 `localhost:8000`

原因：使用了 `.env` 中的开发配置构建。  
修复：Docker build 会自动注入 `VITE_API_BASE=/api/v1`，无需手动处理。

### Q5：Redis 连接失败但后端仍运行

Redis 连接失败时后端降级到无缓存模式，分析功能仍可用，但响应会慢（每次都访问上游数据源）。

---

## 九、数据初始化（首次部署必需）

```bash
# 导入申万行业映射（30个行业，5166只股票）
docker compose exec backend uv run python scripts/import_industry_map.py

# 导入股票主数据（stock_master 搜索主数据表）
docker compose exec backend uv run python scripts/import_stock_master.py

# 刷新行业热门股（可选，生成初始 snapshot）
docker compose exec backend uv run python scripts/refresh_industry_hot_stocks.py
```

---

## 十、SSE 实时分析进度说明（M25-a）

### 工作原理

1. 前端 `POST /api/v1/analysis/runs` 创建分析任务（返回 `run_id`）
2. 前端 `GET /api/v1/analysis/runs/{run_id}/events`（`text/event-stream`）订阅进度
3. 后端在 asyncio 后台运行分析，逐 Agent 推送事件
4. 前端收到 `report_ready` 事件后渲染报告

### 关键事件类型

| 事件 | 说明 |
|------|------|
| `analysis_started` | 任务开始，progress=5 |
| `identity_resolved` | 股票名称解析完成，progress=10 |
| `agent_started` | 单个 Agent 开始运行 |
| `agent_completed` | Agent 完成，含 progress 更新 |
| `agent_failed` | Agent 失败（已降级，分析继续） |
| `synthesis_started` | 综合 LLM 调用开始，progress=80 |
| `synthesis_completed` | 综合 LLM 完成，progress=95 |
| `report_ready` | 报告就绪，progress=100，含完整 result |
| `analysis_failed` | 顶层异常 |
| `cancelled` | 用户取消 |

### Nginx SSE 配置要点

`frontend/nginx.conf` 的 `/api/v1/` location 已配置：
```nginx
proxy_buffering      off;
proxy_cache          off;
add_header           X-Accel-Buffering no;
proxy_read_timeout   300s;
```
这是 SSE 在 Nginx 反代下正常工作的必要配置。

### engine=langgraph SSE 灰度入口（M25-c）

选择 LangGraph 引擎时（开发者模式），前端走同一套 SSE 路径（`POST /analysis/runs?engine=langgraph`）。  
SSE 失败时自动 fallback 到 `/analysis/comprehensive-v2`（阻塞接口）。

**生产环境注意：**
- 默认 engine 为 `custom_coordinator`，普通用户不会触发 LangGraph 路径
- EngineSelector 仅在 `import.meta.env.DEV` 或 `localStorage.tradingagents:dev_mode=true` 时显示
- LangGraph SSE 路径与 custom_coordinator 共享同一套 run registry / event_id / after_event_id 机制

---

## Redis Run Registry 模式（M40-b，多 worker 生产部署）

默认模式为内存（`ANALYSIS_RUN_REGISTRY=memory`，单 worker）。多 worker 部署需切换为 Redis 模式：

### 环境变量

```env
ANALYSIS_RUN_REGISTRY=redis
REDIS_URL=redis://redis:6379/0          # Docker Compose 内网地址
ANALYSIS_RUN_TTL_SECONDS=3600           # run 过期时间（秒），默认 3600
ANALYSIS_RUN_EVENT_MAXLEN=500           # 每个 run 最多保留事件数，默认 500
```

### 验证步骤（M40-c 验证通过）

```bash
# 1. 确认 Redis 服务运行
redis-cli ping  # → PONG

# 2. 启动 Redis 模式服务
ANALYSIS_RUN_REGISTRY=redis uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# 3. 健康检查
curl http://localhost:8000/api/v1/health  # → {"status":"ok"}

# 4. 创建分析运行，验证 SSE 事件流
curl -X POST http://localhost:8000/api/v1/analysis/runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"600519","market":"CN","analysis_scope":"technical_only"}'
# → {"run_id":"...","status":"queued",...}

# 5. 接入 SSE 流
curl -N http://localhost:8000/api/v1/analysis/runs/<run_id>/events \
  -H "Authorization: Bearer $TOKEN"
# → 应看到 analysis_started ... report_ready 事件序列

# 6. Redis 不可用 fail-fast 验证
ANALYSIS_RUN_REGISTRY=redis REDIS_URL=redis://localhost:9999 uvicorn ...
curl -X POST .../analysis/runs ...  # → HTTP 503
```

### Docker Compose Redis 模式启用

在 `docker-compose.yml` 的 backend 服务 environment 中取消注释：

```yaml
- ANALYSIS_RUN_REGISTRY=redis
```

确保 redis 服务也已启动（`docker-compose up redis`）。

### 注意事项

- Redis 不可用时，服务启动成功（`/health` 正常），但所有 `/analysis/runs` 端点返回 503
- 内存模式（默认）仍然支持全部功能，仅限单 worker
- `event_maxlen` 满后最旧事件被 LTRIM 淘汰；`after_event_id` replay 仅回放剩余事件

---

## DEFAULT_ANALYSIS_ENGINE 灰度配置（M42 G2）

控制当请求体未显式传 `engine` 字段时，后端使用哪个分析引擎。

### 环境变量

```env
DEFAULT_ANALYSIS_ENGINE=custom_coordinator   # 默认值，稳定路径
DEFAULT_ANALYSIS_ENGINE=langgraph            # LangGraph 灰度路径（M42 G2）
```

### 优先级规则

```
请求 body 中的 engine 字段 > DEFAULT_ANALYSIS_ENGINE > custom_coordinator（硬编码 fallback）
```

- 请求显式传 `engine=custom_coordinator`：始终使用 custom，即使 env=langgraph
- 请求显式传 `engine=langgraph`：始终使用 LangGraph，即使 env=custom_coordinator
- 请求不传 `engine`（生产用户默认）：使用 `DEFAULT_ANALYSIS_ENGINE`
- `DEFAULT_ANALYSIS_ENGINE` 非法值：静默 fallback 至 `custom_coordinator`，服务不崩

### 前端行为

- 非开发者模式（生产用户）：请求 body 不含 `engine` 字段 → 走 env 配置
- 开发者模式（DEV / `localStorage:dev_mode=true`）：手动选择的 engine 写入请求 body → 优先于 env

### Docker Compose 启用方式

取消 `docker-compose.yml` 中的注释：

```yaml
- DEFAULT_ANALYSIS_ENGINE=langgraph
```

### 验证步骤（M42 验证通过）

```bash
# 1. 启动 langgraph 默认模式服务
DEFAULT_ANALYSIS_ENGINE=langgraph uvicorn app.main:app --port 8000

# 2. 创建运行（不传 engine）
curl -X POST .../analysis/runs \
  -d '{"symbol":"000001","market":"CN","analysis_scope":"technical_only"}'
# → metadata.workflow_engine 应为 "langgraph"

# 3. 验证显式覆盖
curl -X POST .../analysis/runs \
  -d '{"symbol":"000001","market":"CN","analysis_scope":"technical_only","engine":"custom_coordinator"}'
# → metadata.workflow_engine 应为 "custom_coordinator"（即使 env=langgraph）

# 4. bad_value fallback
DEFAULT_ANALYSIS_ENGINE=garbage uvicorn ...
curl -X POST .../analysis/runs -d '{...}'
# → metadata.workflow_engine 应为 "custom_coordinator"，服务正常运行
```

### G2 → G4 升级路径

staging 稳定 1-2 周 + 50 次 comprehensive 无异常后，可直接在 `app/core/config.py` 将默认值改为：

```python
default_analysis_engine: str = "langgraph"
```

或在生产 docker-compose.yml 中取消 `DEFAULT_ANALYSIS_ENGINE=langgraph` 注释。

---

## M43：多 worker 生产部署验证（RC）

### 推荐生产部署配置

```bash
# docker-compose.yml backend environment 中启用：
ANALYSIS_RUN_REGISTRY=redis
# DEFAULT_ANALYSIS_ENGINE=custom_coordinator  # 默认不设置即为 custom_coordinator
# DEFAULT_ANALYSIS_ENGINE=langgraph          # staging 灰度 LangGraph 时取消注释
```

### 多 worker 压测结果（M43 RC）

| 配置 | 并发 | 总 run 数 | 结果 |
|------|------|---------|------|
| Redis + custom_coordinator | 4 workers | 8 | 8/8 PASS |
| Redis + langgraph | 4 workers | 8 | 8/8 PASS |

- event_id 无重复（smoke_multi_worker_runs.py 自动校验）
- 首事件延迟 < 500ms（协议层）；LLM 处理时间 7-42s（正常范围）
- 4-worker × Redis registry 跨进程状态共享正常

### 生产部署检查清单（RC）

- [ ] Redis 服务健康（`redis-cli ping` → PONG）
- [ ] alembic current → c5e9f12a3b87 (head)
- [ ] npm run build → 195 modules
- [ ] compileall → 0 errors
- [ ] ANALYSIS_RUN_REGISTRY=redis 已启用（多 worker）
- [ ] DEFAULT_ANALYSIS_ENGINE 按环境配置（生产=custom_coordinator）
