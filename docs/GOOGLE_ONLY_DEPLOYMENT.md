# Google-only 独立发布与回滚步骤（尚未执行）

本次仅本地修改与验证。没有部署、变更共享 Supabase、执行迁移或旧账户绑定，也没有修改 Google 控制台、DNS、Vercel。工作区已有 Google 登录、行情缓存与分析报告修改均保留。

## 发布边界

候选增量位于 `deployment/google-only-v1/`，只包含本次 Google-only 改动。基线是本次开始时**已有 Google 实现的未提交工作区**，不是假定服务器仍处于 Git HEAD。包中记录本地参考 HEAD、精确前后源码 SHA256 和 Google 先决文件指纹，并提供只读兼容检查。

**服务器当前源码尚未提供，候选补丁未完成线上兼容验收，不可直接覆盖发布。** 先在 `/opt/tradingagents` 取得 `git rev-parse HEAD`、`git status --short` 和相关文件实际内容；核对后在隔离副本应用/重整本次增量并重跑测试。源码指纹不同就停止，不能通过丢弃修改、整目录上传或强制套用补丁消除差异。

`google-login/google-login.patch` 是历史的密码＋Google/邀请码实现，不能代表新策略；`market-io-fix-v1` 只包含行情缓存。不要用本地 dist（可能混有其他未发布功能）替换服务器前端，也不要把整个脏工作区构建后当成本次独立产物。

本次运行时修改范围包括 auth 路由、Google 账户解析/验签、认证限流、旧邀请码写接口停用、启动验证、Google-only 页面与客户端。没有修改报告、自选股、权限模型或持久化逻辑。测试及文档同时更新，完整白名单见候选目录 `manifest.json`。

## 数据库与管理员先决条件

- `app_users.google_sub` 必须存在且有有效唯一约束。已有列/约束的环境**无新增必需数据库迁移**。
- 如果缺失，只有在另获明确批准后才能审阅/执行已有 `2026_10_25_0001_google_identity.py`；该迁移只加 nullable 字段与唯一约束。先在隔离副本验证，不能先发新后端再等待数据库修复。
- 原 NOT NULL 密码字段保留，Google 新账户写随机未知密码的 bcrypt hash；不删除密码或邀请码表，不变更现有用户、报告、自选股、角色。
- 保持服务器当前 `SECRET_KEY`、Supabase DATABASE_URL、Redis、`.env.staging.local` 和三份 Compose。不因停用密码而轮换 JWT key；旧有效会话仍按原生命周期工作，refresh 会重新检查账户状态。
- 发布前确认管理员已绑定正确 Google sub；未绑定管理员只能走单独受审的 [迁移方案](GOOGLE_ACCOUNT_MIGRATION.md)。本次没有绑定管理员，也没有创建应急管理员。

在得到只读检查授权的环境，管理员可检查以下信息；**本次没有执行这些 SQL**：

```sql
SELECT column_name, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'app_users'
  AND column_name IN ('id', 'google_sub', 'hashed_password', 'is_admin', 'email_verified_at');
SELECT indexname, indexdef FROM pg_indexes
WHERE schemaname = 'public' AND tablename = 'app_users';
```

还需核对 Alembic 版本与唯一索引有效性、旧账户冲突；不要按邮箱批量回填 google_sub。

## 配置检查

- Google Web client 的 authorized origin、实际前端来源、受众/测试模式；只有 Google 入口，所以配置缺失不再能退回密码登录。
- production/staging 要求 GOOGLE_CLIENT_ID，DEBUG=false、ENABLE_CREATE_ALL=false；保留服务器其他设置，不用本地环境文件覆盖。
- 认证需要 Redis GETDEL/EVAL/INCR/EXPIRE/TTL/SET 权限。Lua 计数原子执行，Redis 不可用返回 503，不放开注册。
- 准确设置 TRUSTED_PROXY_IPS，核对现有 Nginx 追加 X-Forwarded-For 的行为；默认严格忽略不可信来源的该头。合理调整共享代理/NAT 下的认证限额，不把所有来源列为可信代理。
- Google 测试/受众与 Workspace 策略不由项目邀请码控制，控制台调整需要独立处理。本次只做文档说明。

## 本地/CI 构建（发布批准后）

从**核对过的服务器源码副本＋本次增量**构建，保留该副本原有其他已发布修复。在隔离测试库执行 Google、报告、历史、自选股、管理员鉴权回归；真实 Google 弹窗验证需要测试 OAuth client 与隔离账号，不访问共享用户数据。

先确认服务器架构（下例只是 `linux/amd64` 示例，不能假定）：

```bash
# Mac/CI：以下是未来获准后的操作，不由本次任务执行。
release_id=替换为已审阅版本标识
platform=linux/amd64

docker buildx build --platform "$platform" --load \
  -t "tradingagents-google-backend:$release_id" -f backend/Dockerfile backend
docker buildx build --platform "$platform" --load \
  --build-arg VITE_API_BASE=/api/v1 \
  -t "tradingagents-google-frontend:$release_id" -f frontend/Dockerfile frontend
docker save -o "google-only-$release_id.tar" \
  "tradingagents-google-backend:$release_id" "tradingagents-google-frontend:$release_id"
```

本次未执行 Docker 构建/推送。既有 Dockerfile/依赖锁文件的其他改动不在本账户补丁中；应使用与服务器核实后的文件。避免 2 GB 服务器同时构建镜像。

## 服务器发布（须用户另行明确批准）

上传候选目录及已批准源码补丁到独立路径；校验来源与 hash。以下使用既有三份配置和真实项目名，不复制本地 Compose 文件：

```bash
set -euo pipefail
cd /opt/tradingagents
bundle=/tmp/google-only-v1
python3 "$bundle/check_compatibility.py" /opt/tradingagents

dc() {
  docker compose -p aastock-mvp \
    -f docker-compose.yml \
    -f docker-compose.staging.yml \
    -f docker-compose.mvp-server.yml "$@"
}
# 在受控终端审阅合并配置，避免把含密钥的 config 内容保存到普通日志。
# 确认 DATABASE_URL 仍指向原 Supabase，DEBUG=false、ENABLE_CREATE_ALL=false。
dc ps
```

记录 Redis/PostgreSQL/前后端容器 ID，后两者的镜像 ID 和精确标签；在项目目录外以 0700 权限备份本次白名单源码及服务器三份配置，保留环境文件与审核清单。不要将环境文件或数据库导出放进发布包。

```bash
release_id=替换为批准的版本标识
backup=/opt/tradingagents-release-backups/google-only-$release_id
mkdir -p "$backup"
chmod 700 "$backup"
backend_cid=$(dc ps -q backend)
frontend_cid=$(dc ps -q frontend)
test -n "$backend_cid"
test -n "$frontend_cid"
backend_before=$(docker inspect --format '{{.Image}}' "$backend_cid")
frontend_before=$(docker inspect --format '{{.Image}}' "$frontend_cid")
docker image tag "$backend_before" "local/google-backend-rollback:$release_id"
docker image tag "$frontend_before" "local/google-frontend-rollback:$release_id"
python3 - "$bundle/manifest.json" "$backup/source.tar.gz" <<'PY'
import json,sys,tarfile
from pathlib import Path
with tarfile.open(sys.argv[2], 'w:gz') as archive:
    for entry in json.load(open(sys.argv[1]))['files']:
        path=Path(entry['path'])
        if path.is_file(): archive.add(path, arcname=str(path))
    for name in ['docker-compose.yml','docker-compose.staging.yml','docker-compose.mvp-server.yml']:
        archive.add(name, arcname=name)
PY
cp "$bundle/google-only.patch" "$backup/google-only.patch"
git apply --check "$bundle/google-only.patch"
git apply "$bundle/google-only.patch"
# 不在服务器 build；加载核对过架构、源码与 hash 的两个镜像。
docker load -i "/tmp/google-only-$release_id.tar"
python3 - "$release_id" "$backup/release.json" "$backup/rollback.json" <<'PY'
import json,sys
r=sys.argv[1]
for filename,prefix in [(sys.argv[2],'tradingagents-google-'),(sys.argv[3],'local/google-')]:
    suffix='-rollback' if prefix.startswith('local/') else ''
    json.dump({'services':{service:{'image':prefix+service+suffix+':'+r}
                         for service in ['backend','frontend']}}, open(filename,'w'), indent=2)
PY
# 合并已批准镜像 override，仅更新两个服务。
docker compose -p aastock-mvp \
  -f docker-compose.yml -f docker-compose.staging.yml -f docker-compose.mvp-server.yml \
  -f "$backup/release.json" up -d --no-deps --no-build backend frontend
dc ps backend frontend
```

本次没有数据库迁移，因此不要运行 migrate；不要执行 down、--remove-orphans、全量 up、数据库重建或备份恢复。PostgreSQL 当前不在配置服务定义中但仍运行，必须保留；Redis/PostgreSQL 容器 ID 应与发布前一致。

## 发布验收

1. /health、Google 配置、安全 cookie、实际 Google 验签与新用户普通权限。
2. 旧已绑定账号仍为原 UUID，报告、历史、自选股、管理员鉴权不变；旧邮箱未绑定返回 409 联系管理员，不做自动合并；停用用户无法新登录/refresh。
3. 密码/验证码/邀请码写入口在完整应用返回安全 JSON 410；管理入口未认证/普通用户仍被拒绝，历史 GET 仅管理员可读。
4. 验证 nonce 过期/重复、错误 audience/nonce、限流与 Retry-After；失败重试取得新 nonce；没有凭证/数据库/堆栈正文泄露。
5. 登录页只有 Google，取消等待后迟到回调不登录；注册/邀请码旧路由不再呈现旧表单。刷新、退出及会话过期提示正常。

## 回滚

先停止新账户准入并确认流量已受控，再执行代码/镜像回滚；保留期间新增账户和全部 Google 绑定。**旧镜像可能重新提供密码注册/邀请码/密码绑定，不能直接恢复公网服务。** 优先使用已保留 Google-only 保护的已知良好镜像。若只能退回本次之前的旧镜像，需先把 Google 与旧准入路径置于维护状态，直到前向修复通过审核。

可在现有 Nginx server 内审阅加入下列精确 location 维护保护（不替换整份服务器配置，先 `nginx -t`；本次未应用）：

```nginx
location = /api/v1/auth/google { return 503; }
location = /api/v1/auth/login { return 410; }
location = /api/v1/auth/register { return 410; }
location = /api/v1/auth/email-verification/request { return 410; }
location = /mvp/invites { return 410; }
location = /mvp/invites/check { return 410; }
location ~ ^/(api/v1/admin/invites|mvp/admin/invites) { return 410; }
```

确认后端无公网绕过路径；维护规则必须持续存在于回滚后的网关，不能放在将被旧前端镜像覆盖且不挂载的容器文件中。若做不到，先暂停该站入口，不冒险重新开放旧登录机制。

```bash
cd /opt/tradingagents
# 后续有其他源码修改则停止，按备份逐文件审阅，禁止 reset 或整包覆盖。
git apply -R --check "$backup/google-only.patch"
git apply -R "$backup/google-only.patch"
docker compose -p aastock-mvp \
  -f docker-compose.yml -f docker-compose.staging.yml -f docker-compose.mvp-server.yml \
  -f "$backup/rollback.json" up -d --no-deps --no-build backend frontend
```

回滚后复核健康、现有会话读取及维护保护；不执行 Alembic downgrade，不删除新用户/密码字段/邀请码表，不回退数据库。源文件逆补丁只用于本次增量；历史账户迁移的撤销需另行批准，不能随应用回滚自动清空 google_sub。
