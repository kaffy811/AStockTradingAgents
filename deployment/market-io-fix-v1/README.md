# 行情 I/O 修复候选补丁（本地交付，未部署）

`market-io.patch` 只包含本次 21 个文件的增量；不包含 Google 登录、依赖锁文件、Dockerfile、Compose 配置、数据库迁移或其他并行任务。`manifest.json` 给出文件范围、补丁校验和，以及已检查的源码指纹。不要把整个当前工作区或本地 dist 复制到服务器。

**尚未取得服务器当前 commit/源码，不能声称已完成线上兼容验证。** 本地 HEAD 为 `98c111b684cb19de0e0e92cb46e1d675ef3e8d0a`。补丁已在该 HEAD 的隔离源码副本及本地已有修改版本上检查；这两个版本均不被假定为服务器版本。服务器指纹不匹配时须先导出相关源码、针对该版本重整补丁并重跑测试；不要强制应用或覆盖文件。

## 修复内容与证据边界

- `stocks.py` quote/kline，聊天 `stock_tools.py` quote/kline/news，`financial_runtime/tool_runtime.py` quote，缓存 `get_or_set_json` 的同步 loader 统一使用 `asyncio.to_thread`。自选股、profile、新闻路由、基本面及同行查询原有卸载保留。行业分类/热股/同行发现链为异步 SQLAlchemy 和异步缓存调用，无同步行情请求需要卸载。
- `cache_service.py` 在创建协程前拒绝目标事件循环中的同步桥接调用；误调用立即返回 miss/False，不触发 Redis 断路器。工作线程保持原有桥接。等待超时取消 future，让取消传播至 Redis 协程；调度失败关闭未提交的协程。Redis get/set/exists 的真实异常计入已有断路器，避免异常已被 async 层吞掉、sync 层又误记成功。缓存失败仍降级。
- `database.py` Redis 连接/读超时均为 1 秒，池上限 32，无自动重试；池耗尽立即失败并走已有缓存降级；启动探测失败关闭客户端。此前默认没有明确 socket 超时/池上限，但**没有证据证明线上发生过连接池耗尽**。
- 东方财富 quote/kline **每次最多 1 次尝试、0 次重试**，不跟随重定向；连接上限 2 秒，quote total/read 6/4 秒，kline 8/6 秒；`Session` 与响应关闭。每进程最多 4 个并发请求，容量不足立即使用既有备用链；HTTP/连接/JSON 失败后对应 endpoint 冷却 15 秒，其他代码的请求共用此冷却。未把 502/断连认定为限流。
- 保留 CN quote 东方财富→新浪→腾讯、CN kline 东方财富→腾讯→AkShare、HK 腾讯→AkShare 及最终 stale/503 分支。Redis 命中的行情也保留为本进程 stale 候选；内存缓存回填 Redis 只使用剩余 TTL，避免重新获得完整保鲜期。K 线代理补齐 price 字段，并补查默认 120 条/空复权键；仍标记 `kline_proxy`、stale 和非实时。
- profile、自选股新增可选来源/cached/stale 字段，保留原状态值与数据形状。股票详情和自选卡显示“过期缓存 · 来源”。quote/kline 原有 200 stale / 503 不可用契约保留。
- `response.js` 捕获 JSON 解析失败，v1 行情/新闻/行业/自选通用 fetch、v2 fetch、已有密码登录/注册/验证码/me 接口展示通用可理解提示，不展示非 JSON 正文。401/204 和合法 JSON 的错误码保留。未纳入独立开发中的 Google 功能。
- `config.py` 默认 DEBUG=false；`main.py` 仅明确 development/dev/local 环境允许 debug，production/staging 即使误配 DEBUG=true 也不输出调试堆栈；未处理异常返回安全 JSON 500，详细异常仍写服务日志。

确认的是代码缺陷及模拟复现，不是线上调用栈归因。同步等待自身事件循环、同步 HTTP 占用该循环可直接解释应用层 Redis 超时；基础 PING 正常不排除这种情况。东方财富 502/断连属于独立上游故障，具体触发原因仍未知。

## 测试结果

1. 当前工作区相关后端回归：**217 passed，5 warnings，47.14s**。
   ```bash
   backend/.venv/bin/python -m pytest -q \
     backend/tests/test_market_io_resilience.py \
     backend/tests/test_phase6n5_auth_cache_rag.py \
     backend/tests/test_phase6n6_data_architecture.py \
     backend/tests/test_c16_financial_agent_phase1.py \
     backend/tests/test_c23_financial_orchestrator_phase2e.py \
     backend/tests/test_c254_hot_stock_realtime_routing.py \
     backend/tests/test_cors.py backend/tests/test_google_identity.py
   ```
   Google 测试仅验证现有工作未被破坏，不在补丁中。上述 warnings 为已有 passlib/utcnow 弃用提示。
2. 新增后端 **43 项**：三种缓存桥接的工作线程/同循环误用、重复超时取消清理、Redis 断路与启动失败清理、慢 quote/kline/news 下其他 HTTP 请求继续、聊天及 runtime 卸载、CN/HK 备用/stale/503、路由 HTTP/JSON 契约、聚合 stale 元数据、K 线代理、安全 JSON 500、东方财富单次尝试/资源关闭/冷却恢复/并发拒绝。
3. **实际交付补丁隔离验证**：从本地 HEAD 导出干净源码，仅应用本补丁，后端新测试 **43 passed，1 warning，1.74s**；前端 **70 files / 781 passed，5.98s**；`VITE_API_BASE=/api/v1 npm run build` **成功，948 modules，5.59s**。不依赖 Google 登录或其他未提交功能。首次隔离运行因缺少测试环境变量收集失败，已为新增测试提供无真实连接的测试默认配置后通过。
4. 工作区前端全量 **70 files / 781 passed**；生产构建成功。曾因旧测试 fetch mock 没有 headers 而出现 3 个失败，JSON helper 改为直接解析并捕获失败，既兼容有效 JSON 又安全处理非 JSON，相关 **43 passed**。最终隔离全量测试再次通过。
5. 扩展后端曾运行 **218 passed / 1 failed**：`test_c4_orchestrator.py::test_industry_intent` 期待旧行业工具调用，但当前策略在没有获批行业新闻源时拒绝执行，tool_events=[]。在还原本次代码的隔离副本复现相同失败（1 failed），属于既有测试/策略不一致，未擅自修改。后续新增 runtime 测试中漏填 trace_id 的测试构造错误已修正；最终 217 项相关测试通过。
6. `APP_ENV=production DEBUG=true` 导入实际 app，验证 `app.debug is False`；兼容脚本验证已应用识别/源码漂移拒绝；Compose 检查用模拟 JSON 验证 Supabase 通过、本地 PostgreSQL 和 DEBUG=true 被拒绝，输出不含凭据。

未运行真实东方财富、线上 Redis 压测、线上调用栈采样、完整后端全库、生产 Docker 镜像构建及浏览器人工视觉验收。Vite 有既有 CJS API 与 echarts chunk >500 kB 警告；非构建失败。

## 限制

- `requests` 的 Timeout(total=...) 限制连接和初始读取预算，不是 DNS/持续小流量响应的硬墙钟终止。没有增加重试循环，因此没有重试放大；备用源的累计耗时另计。
- `to_thread` 释放事件循环但不能强制终止同步线程。第三方 AkShare 的 HK/新闻等函数没有统一可注入的硬超时，原有代理绕过还会临时修改进程环境；本次未重构 SDK 隔离。这些源极慢时仍可占用工作线程，不能把本修复宣称为所有数据源均有整链硬截止或全局并发隔离。
- 东方财富并发门限和冷却为每进程；多实例数量会乘算。stale 保留沿用进程内策略，重启后不保证保留；没有新增跨重启过期缓存持久化或最大陈旧年龄。API 会标注 stale/source，不声称实时。
- 行情下游适配器、Supabase、线上配置与容器运行状态未从生产实际核实。无法凭本地结果证明线上唯一根因或线上已恢复。

## 线上更新步骤（仅供后续执行，本次没有执行）

在服务器当前源码核对及对应测试通过后，上传整个本目录到 `/tmp/market-io-fix-v1`。**不要上传本地 compose 覆盖服务器文件。** 本地 staging 文件仍定义 PostgreSQL/DATABASE_URL 覆盖，与已知线上状态不同；本地还缺少 mvp-server 文件。

以下在同一个 Bash 会话执行，任何校验失败立即停止：

```bash
set -euo pipefail
cd /opt/tradingagents
bundle=/tmp/market-io-fix-v1
git rev-parse HEAD
git status --short
python3 "$bundle/check_compatibility.py" /opt/tradingagents

dc() {
  docker compose -p aastock-mvp \
    -f docker-compose.yml \
    -f docker-compose.staging.yml \
    -f docker-compose.mvp-server.yml "$@"
}
# 只读检查三份实际配置合并结果，不把含密钥的 config 写入日志。
dc config --format json | python3 "$bundle/check_compose.py"
```

兼容脚本只接受已审阅源码指纹；若服务器已升级或有其他源码修改会拒绝。需基于实际源码重整并重测后再继续，不能只凭 commit 或 `git apply --check` 通过便认为行为兼容。若使用自定义 Supabase 域名，Compose 检查会拒绝，需人工核实域名再调整检查器；不要更换 DATABASE_URL。

备份现有源码、配置与镜像，备份目录保留在项目外，不影响构建上下文：

```bash
release_id=$(date -u +%Y%m%dT%H%M%SZ)
backup=/opt/tradingagents-release-backups/market-io-$release_id
mkdir -p "$backup"
chmod 700 "$backup"
python3 - "$bundle/manifest.json" "$backup/source.tar.gz" <<'PY'
import json,sys,tarfile
from pathlib import Path
entries=json.load(open(sys.argv[1]))['files']
with tarfile.open(sys.argv[2], 'w:gz') as archive:
    for e in entries:
        p=Path(e['path'])
        if p.is_file(): archive.add(p, arcname=e['path'])
    for name in ['docker-compose.yml','docker-compose.staging.yml','docker-compose.mvp-server.yml']:
        archive.add(name, arcname=name)
PY
backend_cid=$(dc ps -q backend)
frontend_cid=$(dc ps -q frontend)
test -n "$backend_cid"
test -n "$frontend_cid"
backend_before=$(docker inspect --format '{{.Image}}' "$backend_cid")
frontend_before=$(docker inspect --format '{{.Image}}' "$frontend_cid")
docker image tag "$backend_before" "local/market-backend-rollback:$release_id"
docker image tag "$frontend_before" "local/market-frontend-rollback:$release_id"
python3 - "$release_id" "$backup/rollback.json" <<'PY'
import json,sys
r=sys.argv[1]
json.dump({'services': {
    'backend': {'image': 'local/market-backend-rollback:'+r},
    'frontend': {'image': 'local/market-frontend-rollback:'+r}
}}, open(sys.argv[2], 'w'), indent=2)
PY
cp "$bundle/market-io.patch" "$backup/market-io.patch"
git apply --check "$bundle/market-io.patch"
git apply "$bundle/market-io.patch"
python3 "$bundle/check_compatibility.py" /opt/tradingagents
# 在与服务器当前源码相匹配的测试环境重跑上述后端回归及前端 npm test/build。
# 此补丁没有依赖/迁移变化；下面只构建、更新两个服务。
dc build backend frontend
dc up -d --no-deps --no-build backend frontend
dc ps backend frontend
dc exec -T backend uv run python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5).read().decode())'
dc exec -T backend uv run python -c 'from app.main import app; assert not app.debug; print("debug disabled")'
dc logs --since 5m --tail 100 backend
```

本次不运行 migrate，不操作 Redis/PostgreSQL/Supabase，不执行 compose down、--remove-orphans、全量 up、数据库重建。更新前后核对 PostgreSQL/Redis 容器 ID 不变。保持现有环境变量和 Supabase 连接；不要用本地 .env 替换线上文件。

发布后用已有登录账号检查 quote/kline/news/profile/watchlist/行业接口，确认字段形状及认证不变；上游故障时检查备用 source、stale 明示、无数据 JSON 503。并发拉取慢行情期间观察 /health 响应和 cache timeout 日志，不以健康检查通过代替行情正确性验收。浏览器确认非 JSON 网关错误只展示友好提示。

## 回滚步骤

保留以上 Bash 会话或重建 dc 函数，设置实际 `backup` 路径。不要先删除原有镜像标签。先检查补丁逆向能否应用；若有后续源码编辑则停止，按备份逐文件审阅恢复，不做 git reset：

```bash
cd /opt/tradingagents
git apply -R --check "$backup/market-io.patch"
git apply -R "$backup/market-io.patch"
docker compose -p aastock-mvp \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  -f docker-compose.mvp-server.yml \
  -f "$backup/rollback.json" \
  up -d --no-deps --no-build backend frontend
dc ps backend frontend
dc exec -T backend uv run python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5).read().decode())'
```

源码回滚保留 Google 登录等本次以外改动；镜像回滚恢复更新前实际运行的两个镜像，不运行数据库迁移。若 Compose 有源码 bind mount，源码逆补丁同样必须完成；更新前应检查实际挂载。`source.tar.gz` 作为进一步人工恢复依据，不直接整包覆盖并行修改。
