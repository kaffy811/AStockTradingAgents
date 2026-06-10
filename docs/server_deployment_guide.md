# TradingAgents 服务器部署文档

> 版本：RC（Phase M45）  
> 适用环境：Ubuntu 22.04 / 24.04，云服务器 / VPS / Linux 物理机  
> 前置：Docker、Docker Compose、Git

---

## 关于双引擎架构与 LangGraph 封装状态

TradingAgents 已完成 LangGraph 封装，采用双引擎并行架构：

| 引擎 | 状态 | 说明 |
|------|------|------|
| `custom_coordinator` | ✅ 默认稳定引擎 | 纯 Python，易 debug，M43 RC 生产验证 |
| `langgraph` | ✅ 已封装，env 灰度 | Send API fan-out，shape 100% 兼容，M41 验证 |

**优先级链：**

```
请求 body 显式 engine > DEFAULT_ANALYSIS_ENGINE 环境变量 > "custom_coordinator"
```

**生产推荐：**

```env
DEFAULT_ANALYSIS_ENGINE=custom_coordinator   # 不设置则自动使用此默认值
```

**staging 灰度 LangGraph：**

```env
DEFAULT_ANALYSIS_ENGINE=langgraph
```

**Run Registry 模式：**

| 模式 | 适用场景 | 说明 |
|------|---------|------|
| `ANALYSIS_RUN_REGISTRY=memory` | 本地开发 / 单 worker | 默认值，进程重启后 run 状态丢失 |
| `ANALYSIS_RUN_REGISTRY=redis` | 生产多 worker | 跨进程共享，Redis 不可用时 fail-fast HTTP 503 |

**生产推荐：**

```env
ANALYSIS_RUN_REGISTRY=redis
DEFAULT_ANALYSIS_ENGINE=custom_coordinator
```

---

## 一、部署架构概览

```
用户浏览器
    │ HTTP/HTTPS :80 / :443
    ▼
Nginx（frontend 容器）
    ├── /* → Vue3 SPA 静态文件（dist/）
    └── /api/v1/* → backend:8000（内部网络）
                        │
                    FastAPI Backend（backend 容器）
                        │
              ┌─────────┴──────────┐
              │                    │
           Redis 7              PostgreSQL
       （redis 容器，内部）   （Supabase 外部托管）
              │
        AnalysisRunRegistry
        LLM API（DeepSeek / OpenAI）
        数据源（AkShare / yfinance / Sina）
```

**核心服务：**

| 服务 | 角色 |
|------|------|
| `frontend` | Nginx：Vue3 SPA 静态文件 + `/api/v1` 反向代理 |
| `backend` | FastAPI API 服务，analysis runner，SSE 事件流 |
| `redis` | AnalysisRunRegistry 后端（多 worker 模式），行情缓存 |
| `migrate` | 一次性 Alembic 迁移容器，运行后退出 |
| PostgreSQL | **外部托管**（Supabase），不在 docker-compose 内 |

> PostgreSQL 使用 Supabase Transaction Pooler（端口 6543），需在 .env 中配置 `DATABASE_URL`。

---

## 二、服务器环境要求

### 系统要求

- Ubuntu 22.04 LTS 或 24.04 LTS（推荐）
- 最低：2 vCPU / 2GB RAM / 20GB SSD
- 推荐生产：4 vCPU / 4GB RAM / 40GB SSD
- 公网 IP（如需 HTTPS，还需域名）

### 初始化系统

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl vim ufw
```

### 安装 Docker 与 Docker Compose

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# 重新登录或执行：
newgrp docker
# 验证
docker --version
docker compose version
```

### 防火墙配置

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
sudo ufw status
```

> Redis 端口（6379）不要对公网开放。Redis 只在 Docker 内部网络中访问。

---

## 三、拉取项目代码

```bash
cd /opt
sudo mkdir -p tradingagents
sudo chown -R $USER:$USER /opt/tradingagents
cd /opt/tradingagents

git clone <your-repo-url> .
```

如果是私有仓库，需要先配置 SSH key 或 Personal Access Token：

```bash
# 方式一：SSH key
ssh-keygen -t ed25519 -C "your-email@example.com"
cat ~/.ssh/id_ed25519.pub   # 复制公钥到 GitHub/GitLab SSH Keys

# 方式二：HTTPS Token（推荐 CI）
git clone https://<token>@github.com/yourname/TradingAgents.git .
```

---

## 四、环境变量配置

```bash
cp .env.example .env
vim .env
```

**.env 完整模板（基于项目 .env.example）：**

```env
# ── Application ───────────────────────────────────────────────────────────────
APP_NAME=TradingAgents Backend
APP_ENV=production
DEBUG=false
ENABLE_CREATE_ALL=false

# ── Database ──────────────────────────────────────────────────────────────────
# Supabase Transaction Pooler URL（端口 6543，NullPool 兼容 PgBouncer）
# 格式：postgresql+asyncpg://<user>:<password>@<host>:6543/<db>
DATABASE_URL=postgresql+asyncpg://postgres.xxxx:your_password@aws-0-region.pooler.supabase.com:6543/postgres

# ── Authentication ─────────────────────────────────────────────────────────────
# 生成方式：python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=please-change-this-to-a-random-64-char-string
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30

# ── Redis ─────────────────────────────────────────────────────────────────────
# docker-compose.yml 中 backend 服务的 environment 会覆盖此值为 redis://redis:6379
REDIS_URL=redis://redis:6379

# ── Analysis Run Registry（生产多 worker 推荐 redis）────────────────────────────
ANALYSIS_RUN_REGISTRY=redis
ANALYSIS_RUN_TTL_SECONDS=21600
ANALYSIS_RUN_EVENT_MAXLEN=200

# ── Default Analysis Engine ───────────────────────────────────────────────────
# 不设置则默认 custom_coordinator
DEFAULT_ANALYSIS_ENGINE=custom_coordinator
# 灰度 LangGraph：取消下行注释
# DEFAULT_ANALYSIS_ENGINE=langgraph

# ── LLM ───────────────────────────────────────────────────────────────────────
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
# 如果使用 OpenAI 兼容接口
OPENAI_API_KEY=

# ── CORS ──────────────────────────────────────────────────────────────────────
# 必须是 JSON 数组格式，逗号分隔字符串会导致启动崩溃
# 使用 Nginx 反向代理时，浏览器走同源，CORS 不强制。仍建议填写具体 origin。
CORS_ORIGINS=["https://your-domain.com","http://your-server-ip"]
```

**安全要求（生产必须执行）：**

1. `SECRET_KEY` 必须修改，不能使用示例值
2. `DATABASE_URL` 密码不要使用默认值
3. `.env` 文件权限收紧：`chmod 600 .env`
4. 不要将 `.env` 提交到 Git（已在 `.gitignore` 中排除）
5. `DEEPSEEK_API_KEY` 不要写入代码，只在 `.env` 中配置

---

## 五、Docker Compose 部署

### 首次部署

```bash
# 1. 启动 Redis（其他服务依赖 Redis 健康检查）
docker compose up -d redis

# 2. 等待 Redis 健康
docker compose ps redis
# 应看到 health: healthy

# 3. 运行 Alembic 迁移（一次性容器）
docker compose run --rm migrate

# 4. 启动后端与前端
docker compose up -d backend frontend

# 5. 查看所有服务状态
docker compose ps
```

### 后续部署（代码变更后）

```bash
git pull
docker compose build
docker compose run --rm migrate
docker compose up -d
```

### 仅重启（无 schema 变更）

```bash
docker compose up -d
```

### 查看日志

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f redis
docker compose logs -f migrate
```

---

## 六、数据库迁移验证

```bash
# 查看当前 migration 状态
docker compose exec backend uv run alembic current
```

预期输出（RC 版本）：

```
c5e9f12a3b87 (head)
```

如果不是 `(head)`，说明存在未执行的 migration：

```bash
docker compose run --rm migrate
# 等价于：docker compose exec backend uv run alembic upgrade head
```

---

## 七、Redis Registry 验证

```bash
# 基本连通性
docker compose exec redis redis-cli ping
# 预期：PONG

# 运行集成验证脚本（T1-T10 全量验证）
docker compose exec backend uv run python scripts/verify_redis_run_registry.py
# 预期：10/10 PASS
```

脚本验证内容：create_run / get_run_snapshot / push_event / event_id replay / None sentinel / update_status / cancel / subscribe_events / TTL 共 10 个场景。

---

## 八、LangGraph 引擎验证

### 默认模式（custom_coordinator）

**不需要额外配置**，默认即为 `custom_coordinator`。

```bash
# 获取 JWT token（先注册/登录）
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"your_user","password":"your_password"}' | python3 -c "
import sys,json; d=json.load(sys.stdin); print(d.get('access_token','ERROR'))
"
# 保存 token
TOKEN="<上面输出的 token>"

# 创建分析任务（不传 engine，使用 DEFAULT_ANALYSIS_ENGINE）
curl -s -X POST http://localhost:8000/api/v1/analysis/runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"market":"CN","symbol":"000001","analysis_scope":"technical_only","output_language":"zh-CN"}'
```

### 切换到 LangGraph

修改 `.env`：

```env
DEFAULT_ANALYSIS_ENGINE=langgraph
```

重启后端：

```bash
docker compose restart backend
```

或修改 `docker-compose.yml` backend 的 environment 块（注释已预留）：

```yaml
# - DEFAULT_ANALYSIS_ENGINE=custom_coordinator
- DEFAULT_ANALYSIS_ENGINE=langgraph
```

验证：创建任务后检查 `metadata.workflow_engine` 字段应为 `"langgraph"`。

```bash
# 获取 run 状态（等待完成后）
curl "http://localhost:8000/api/v1/analysis/runs/<run_id>" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'status={d.get(\"status\")}')
print(f'wfe={d.get(\"result\",{}).get(\"metadata\",{}).get(\"workflow_engine\")}')
print(f'ol={d.get(\"result\",{}).get(\"output_language\")}')
"
```

预期：`wfe=langgraph`

### 显式传 engine 覆盖 env

```bash
# 即使 env=langgraph，显式传 engine=custom_coordinator 时仍使用 custom_coordinator
curl -s -X POST http://localhost:8000/api/v1/analysis/runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"market":"CN","symbol":"000001","analysis_scope":"technical_only","engine":"custom_coordinator"}'
```

---

## 九、SSE 实时分析验证

```bash
# 第一步：创建分析任务
RUN_RESP=$(curl -s -X POST http://localhost:8000/api/v1/analysis/runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"market":"CN","symbol":"000001","analysis_scope":"technical_only","output_language":"en-US"}')

RUN_ID=$(echo $RUN_RESP | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
echo "run_id: $RUN_ID"

# 第二步：订阅 SSE 事件流
curl -N "http://localhost:8000/api/v1/analysis/runs/$RUN_ID/events" \
  -H "Authorization: Bearer $TOKEN"
```

预期事件序列：

```
event: analysis_started
event: identity_resolved
event: agent_started
event: agent_completed
event: synthesis_started
event: synthesis_completed
event: report_ready
: stream-end
```

收到 `report_ready` 后检查报告语言：

```bash
curl "http://localhost:8000/api/v1/analysis/runs/$RUN_ID" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
d=json.load(sys.stdin)
r=d.get('result',{})
print(f'status={d[\"status\"]}')
print(f'output_language={r.get(\"output_language\")}')   # 应为 en-US
print(f'workflow_engine={r.get(\"metadata\",{}).get(\"workflow_engine\")}')
"
```

---

## 十、多 worker 部署建议

### 开发 / 单 worker

```env
ANALYSIS_RUN_REGISTRY=memory
```

直接 `docker compose up -d` 即可，单 worker 默认。

### 生产 / 多 worker（推荐）

```env
ANALYSIS_RUN_REGISTRY=redis
```

`docker-compose.yml` 中开启（取消注释）：

```yaml
# - ANALYSIS_RUN_REGISTRY=redis
```

或在 `.env` 中设置（`.env` 优先级低于 compose 内 environment 块直接设置）。

多 worker 启动命令（如手动启动，不通过 Docker）：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**注意：**

- `memory` registry 不支持多 worker（worker 间 run 状态不共享）
- `redis` registry 支持跨 worker run state / event replay / cancel 请求
- 取消操作无法强制终止已进入 `asyncio.to_thread` 的同步 agent 线程，取消语义为"停止等待"

---

## 十一、Nginx 配置

### 基础配置（HTTP）

```nginx
server {
    listen 80;
    server_name your-domain.com;  # 或 _;（不限制域名）

    client_max_body_size 20M;

    # Vue3 SPA 静态文件
    # 如果由 Docker 前端容器提供，此 location 可省略（frontend 容器已内置 Nginx）
    # 如果手动部署静态文件到宿主机，则配置此路径
    location / {
        root /var/www/tradingagents;
        try_files $uri $uri/ /index.html;
    }

    # 常规 API 代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 60s;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # SSE 专用配置（必须关闭 buffering，否则进度推送会卡顿）
    location /api/v1/analysis/runs/ {
        proxy_pass http://127.0.0.1:8000/api/v1/analysis/runs/;
        proxy_http_version 1.1;

        # SSE 关键配置
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;

        # 保持长连接
        proxy_set_header Connection '';

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> **重要**：SSE 路由必须配置 `proxy_buffering off` 和足够长的 `proxy_read_timeout`，否则前端 SSE 进度条会延迟甚至收不到事件。

配置测试：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

注意：如果使用 Docker Compose 中的 `frontend` 容器，该容器已内置 Nginx 并处理反向代理，宿主机的 Nginx 可以直接将流量转发至 frontend 容器端口，或不使用宿主机 Nginx。

---

## 十二、HTTPS 配置（Let's Encrypt）

```bash
sudo apt install -y certbot python3-certbot-nginx

# 申请证书（需要域名已指向服务器 IP）
sudo certbot --nginx -d your-domain.com

# 测试自动续期
sudo certbot renew --dry-run

# certbot 会自动修改 Nginx 配置，添加 SSL 相关配置
sudo nginx -t
sudo systemctl reload nginx
```

---

## 十三、前端构建与部署（无 Docker 模式）

如果不使用 Docker Compose 的前端容器，手动构建并部署静态文件：

```bash
cd frontend
npm install
npm run build
# 产物在 dist/ 目录
```

部署到 Nginx 静态目录：

```bash
sudo mkdir -p /var/www/tradingagents
sudo cp -r dist/* /var/www/tradingagents/
sudo chown -R www-data:www-data /var/www/tradingagents
sudo chmod -R 755 /var/www/tradingagents
```

构建时 `VITE_API_BASE` 决定前端 API 请求的 base path（在 `docker-compose.yml` 的 frontend build args 中配置）：

```yaml
args:
  - VITE_API_BASE=/api/v1   # 使用相对路径，适配 Nginx 同源反向代理
```

---

## 十四、生产 Smoke Test

```bash
# 基础健康检查
curl http://localhost:8000/health    # → {"status":"ok"}
curl http://your-domain.com/         # → Vue3 SPA 首页

# API 文档（生产模式如 debug=false 则可能禁用）
curl http://localhost:8000/docs      # Swagger UI

# 创建任务 + SSE（见第九节）

# 历史报告保存
curl -s -X POST http://localhost:8000/api/v1/reports/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "market":"CN", "symbol":"000001",
    "report_type":"comprehensive_v2",
    "stock_name":"平安银行",
    "auto_saved":true,
    "analysis_scope":"technical_only",
    "output_language":"zh-CN",
    "report_md":"# 测试报告\n\n风险提示：仅供研究参考。",
    "sections":{"technical":"测试内容"},
    "report_metadata":{"workflow_engine":"custom_coordinator"},
    "warnings":[], "agents":{"technical_analyst":{"status":"completed"}}
  }' -w "\nHTTP:%{http_code}"
# 预期：HTTP:201

# 报告列表
curl "http://localhost:8000/api/v1/reports/?limit=5" \
  -H "Authorization: Bearer $TOKEN"
# 预期：{"total":1,"items":[...]}
```

---

## 十五、常见问题排查

### 1. SSE 没有实时刷新（进度条卡住）

**原因**：Nginx `proxy_buffering` 默认为 `on`，缓冲了 SSE 数据。

**修复**：

```nginx
location /api/v1/analysis/runs/ {
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    proxy_set_header Connection '';
    ...
}
```

---

### 2. HTTP 503 — Analysis run registry is unavailable

**原因**：`ANALYSIS_RUN_REGISTRY=redis` 但 Redis 不可达。

**检查**：

```bash
docker compose exec redis redis-cli ping    # 应返回 PONG
docker compose logs redis | tail -20
```

**修复**：确认 Redis 容器健康，`depends_on` 条件满足；或临时改为 `ANALYSIS_RUN_REGISTRY=memory`（单 worker 开发用）。

---

### 3. Alembic migration 报错

```bash
# 查看详细错误
docker compose logs migrate

# 手动运行
docker compose exec backend uv run alembic upgrade head

# 查看当前 revision
docker compose exec backend uv run alembic current

# 查看 migration 历史
docker compose exec backend uv run alembic history
```

常见原因：`DATABASE_URL` 格式错误（需 `postgresql+asyncpg://`，端口 6543 for Supabase Transaction Pooler）。

---

### 4. LLM API key 失效

**症状**：分析任务卡在 `agent_started`，最终收到 `analysis_failed` 事件。

**检查**：

```bash
docker compose logs backend | grep -i "api\|llm\|key\|error" | tail -20
```

**修复**：更新 `.env` 中的 `DEEPSEEK_API_KEY`，重启 backend：

```bash
docker compose restart backend
```

---

### 5. 数据源超时（AkShare/Sina/yfinance）

**症状**：Agent 报告超时，报告降级（`_fallback_report`）。

**说明**：AkShare / Sina / yfinance 为第三方接口，网络波动不可控。系统已有降级路径，不会崩溃。

**建议**：确保服务器可访问中国大陆金融数据接口（如 AkShare），或在离接口更近的云服务商部署。

---

### 6. 端口冲突

```bash
# 查看 80 / 443 / 8000 / 6379 是否被占用
sudo ss -tlnp | grep -E ":80|:443|:8000|:6379"
sudo lsof -i :80
```

停止冲突进程后重启 Docker 服务。

---

### 7. CORS 问题

**症状**：浏览器 Console 报 `CORS policy` 错误。

**原因**：`CORS_ORIGINS` 未包含前端 origin，或格式不正确。

**检查 .env**：

```env
# 正确（JSON 数组）：
CORS_ORIGINS=["https://your-domain.com","http://your-server-ip"]

# 错误（逗号字符串，会导致启动崩溃）：
CORS_ORIGINS=https://your-domain.com,http://your-server-ip
```

使用 Nginx 同源反向代理时（`VITE_API_BASE=/api/v1`），浏览器不会触发 CORS，但仍建议填写具体 origin。

---

### 8. Nginx 代理路径不一致

**症状**：`/api/v1/...` 返回 404。

**检查**：

```bash
# 测试 Nginx 能否转发到后端
curl -v http://localhost/api/v1/health
```

确认 `proxy_pass` URL 与后端实际监听地址（端口 8000）一致，以及路径前缀不重复（`/api/` → `http://127.0.0.1:8000/api/`，注意末尾斜杠）。

---

### 9. Docker 容器无法连接 Redis

**症状**：backend 日志报 `ConnectionRefusedError` 或 `Redis connection failed`。

**原因**：`REDIS_URL` 使用了 `localhost:6379`，但在 Docker 容器中应使用服务名。

**注意**：`docker-compose.yml` backend 的 environment 块已硬覆盖为 `redis://redis:6379`，优先于 `.env`。如果手动启动（非 Docker），需将 `REDIS_URL` 改为正确地址。

---

### 10. Docker 容器无法连接 PostgreSQL

**说明**：本项目 PostgreSQL 使用 **Supabase 外部托管**，不在 Docker Compose 内。

**检查**：

```bash
# 测试 DATABASE_URL 是否可访问
docker compose exec backend python3 -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def test():
    eng = create_async_engine(settings.database_url)
    async with eng.connect() as conn:
        result = await conn.execute(sqlalchemy.text('SELECT 1'))
        print('DB OK:', result.scalar())

import sqlalchemy
asyncio.run(test())
"
```

常见原因：Supabase 密码或 host 有误；Transaction Pooler 端口应为 6543，非 5432。

---

## 十六、推荐生产配置总结

### 生产环境

```env
APP_ENV=production
DEBUG=false
ENABLE_CREATE_ALL=false

ANALYSIS_RUN_REGISTRY=redis
DEFAULT_ANALYSIS_ENGINE=custom_coordinator

ANALYSIS_RUN_TTL_SECONDS=21600
ANALYSIS_RUN_EVENT_MAXLEN=200

REDIS_URL=redis://redis:6379
SECRET_KEY=<64字符随机字符串>
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<supabase-host>:6543/<db>

DEEPSEEK_API_KEY=<your-key>
CORS_ORIGINS=["https://your-domain.com"]
```

### staging（LangGraph 灰度）

```env
# 仅改这一行
DEFAULT_ANALYSIS_ENGINE=langgraph
```

### 本地开发

```env
APP_ENV=development
DEBUG=true
ENABLE_CREATE_ALL=false

ANALYSIS_RUN_REGISTRY=memory
DEFAULT_ANALYSIS_ENGINE=custom_coordinator
```

---

## 十七、安全建议

1. **不要提交 `.env`**：已在 `.gitignore` 中排除，确认 `git status` 不含 `.env`
2. **生产必须修改 SECRET_KEY**：生成命令 `python3 -c "import secrets; print(secrets.token_hex(32))"`
3. **数据库密码不要使用默认值**：Supabase 控制台修改 DB 密码后同步更新 `DATABASE_URL`
4. **Redis 不要暴露公网**：Redis 只在 Docker 内部网络中，不要添加 `ports:` 节
5. **Nginx 只暴露 80/443**：backend 使用 `expose:` 而非 `ports:`，仅内部可达
6. **API key 使用服务器环境变量管理**：不要 hardcode 在代码中
7. **定期备份 PostgreSQL**：见下方运维命令
8. **开启 HTTPS**：`certbot --nginx` 免费证书，自动续期
9. **日志不要输出 API key**：确认日志级别不包含请求 body 中的敏感字段
10. **AI 报告仅供研究参考**：系统所有报告不构成投资建议

---

## 十八、运维命令

### 日常运维

```bash
# 查看所有服务状态
docker compose ps

# 实时日志
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f redis

# 重启单个服务
docker compose restart backend

# 停止所有服务
docker compose down

# 重新构建并启动（代码变更后）
docker compose up -d --build
```

### 数据库备份与恢复

本项目使用 Supabase 托管 PostgreSQL，推荐通过 Supabase 控制台进行备份。

如需手动备份（连接 Supabase 外部）：

```bash
# 备份（需本地安装 pg_dump，或使用 Docker）
DATABASE_URL="postgresql://postgres:password@supabase-host:5432/postgres"
pg_dump "$DATABASE_URL" > backup_$(date +%Y%m%d_%H%M%S).sql

# 恢复
psql "$DATABASE_URL" < backup_20260609_120000.sql
```

### Redis 运维

```bash
# 检查 Redis 健康
docker compose exec redis redis-cli ping

# 查看 TradingAgents run keys（格式：ta:v1:run:<run_id>:...）
docker compose exec redis redis-cli keys "ta:*"

# 查看指定 run 状态
docker compose exec redis redis-cli hgetall "ta:v1:run:<run_id>:state"

# 查看 Redis 内存占用
docker compose exec redis redis-cli info memory | grep used_memory_human
```

---

## 十九、最终部署检查清单

```markdown
## 部署前
- [ ] .env 已从 .env.example 复制并填写
- [ ] SECRET_KEY 已修改（非示例值）
- [ ] DATABASE_URL 已填写（Supabase Transaction Pooler，端口 6543）
- [ ] DEEPSEEK_API_KEY 有效
- [ ] CORS_ORIGINS 已填写（JSON 数组格式）
- [ ] .env 权限已收紧：chmod 600 .env

## 服务启动
- [ ] docker compose up -d redis → health: healthy
- [ ] docker compose run --rm migrate → alembic current: c5e9f12a3b87 (head)
- [ ] docker compose up -d backend frontend → 两服务均 running
- [ ] docker compose logs backend → 无启动报错
- [ ] curl http://localhost:8000/health → {"status":"ok"}

## 功能验证
- [ ] 首页可访问（curl http://your-domain.com/）
- [ ] 用户注册/登录正常
- [ ] POST /analysis/runs 可创建任务（HTTP 201）
- [ ] SSE 可实时收到事件（analysis_started → report_ready）
- [ ] report_ready 事件中 metadata.workflow_engine 正确
- [ ] 历史报告保存正常（POST /reports/ → HTTP 201）
- [ ] 报告列表查询正常（GET /reports/ → total > 0）

## Registry 与 Engine
- [ ] docker compose exec redis redis-cli ping → PONG
- [ ] docker compose exec backend uv run python scripts/verify_redis_run_registry.py → 10/10 PASS
- [ ] DEFAULT_ANALYSIS_ENGINE=custom_coordinator 验证（默认）
- [ ] 如需灰度：DEFAULT_ANALYSIS_ENGINE=langgraph 验证

## Nginx 与 HTTPS
- [ ] sudo nginx -t → 配置语法正确
- [ ] SSE 不缓冲验证（进度条实时更新，无明显延迟）
- [ ] HTTPS 证书已配置（如有域名）
- [ ] certbot renew --dry-run 通过

## 安全
- [ ] .env 不在 git 追踪中（git status 确认）
- [ ] Redis 端口未对公网暴露（sudo ss -tlnp | grep 6379 仅内部）
- [ ] backend 端口未对公网暴露（docker compose ps 确认 expose 非 ports）
```
