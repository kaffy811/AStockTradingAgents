#!/usr/bin/env bash
# ── TradingAgents — Docker Deploy Smoke Check ─────────────────────────────────
#
# Purpose:
#   End-to-end validation that the Docker Compose stack builds and runs correctly.
#   Run this script from the repository root after installing Docker Engine ≥ 24.
#
# Usage:
#   cd /path/to/TradingAgents
#   chmod +x scripts/deploy_smoke_check.sh
#   ./scripts/deploy_smoke_check.sh
#
# What it does (in order):
#   1.  Pre-flight: verify docker, docker compose, .env exist
#   2.  Pre-flight: warn if .env still contains placeholder values
#   3.  Validate compose config (yaml parse + interpolation)
#   4.  Build all images
#   5.  Start redis, run Alembic migration, start backend + frontend
#   6.  Health-check: frontend HTTP, backend /health, Redis PING
#   7.  Bundle check: confirm frontend JS does NOT hardcode localhost:8000
#   8.  Print PASS / FAIL summary
#
# Security:
#   - .env is read only to detect placeholder strings; values are never printed.
#   - SECRET_KEY, DEEPSEEK_API_KEY, DATABASE_URL contents are never echoed.
#   - The script exits before build if placeholders are detected (prevents
#     starting with insecure/broken config).
#
# Requirements:
#   - Docker Engine ≥ 24
#   - Docker Compose v2  (docker compose, not docker-compose)
#   - curl
#   - Running from repo root (directory containing docker-compose.yml)

set -euo pipefail

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

pass()  { echo -e "  ${GREEN}✓${RESET}  $*"; }
fail()  { echo -e "  ${RED}✗${RESET}  $*"; }
warn()  { echo -e "  ${YELLOW}!${RESET}  $*"; }
info()  { echo -e "  ${CYAN}→${RESET}  $*"; }
header(){ echo -e "\n${BOLD}$*${RESET}"; }

# ── Failure tracking ───────────────────────────────────────────────────────────
FAILURES=()
record_fail() { FAILURES+=("$1"); }

# ── Locate repo root ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ ! -f "${REPO_ROOT}/docker-compose.yml" ]]; then
  echo -e "${RED}ERROR: docker-compose.yml not found in ${REPO_ROOT}${RESET}"
  echo "Run this script from the repository root, or ensure the scripts/ directory"
  echo "is one level below the repo root."
  exit 1
fi

cd "${REPO_ROOT}"
echo -e "\n${BOLD}TradingAgents — Docker Deploy Smoke Check${RESET}"
echo "Working directory: ${REPO_ROOT}"
echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"

# ══════════════════════════════════════════════════════════════════════════════
header "Step 1 — Pre-flight: toolchain"
# ══════════════════════════════════════════════════════════════════════════════

# 1a. docker binary
if command -v docker &>/dev/null; then
  DOCKER_VER=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
  pass "docker found (server version: ${DOCKER_VER})"
else
  fail "docker not found — install Docker Engine ≥ 24 first"
  record_fail "docker binary missing"
  echo -e "\n${RED}Cannot continue without Docker. Aborting.${RESET}"
  exit 1
fi

# 1b. docker compose (v2 plugin)
if docker compose version &>/dev/null; then
  COMPOSE_VER=$(docker compose version --short 2>/dev/null || echo "unknown")
  pass "docker compose v2 found (${COMPOSE_VER})"
else
  fail "docker compose v2 not found — run: docker compose version"
  record_fail "docker compose v2 missing"
  echo -e "\n${RED}Cannot continue without Docker Compose v2. Aborting.${RESET}"
  exit 1
fi

# 1c. curl
if command -v curl &>/dev/null; then
  pass "curl found"
else
  fail "curl not found — install curl (brew install curl / apt install curl)"
  record_fail "curl missing"
fi

# ══════════════════════════════════════════════════════════════════════════════
header "Step 2 — Pre-flight: .env file"
# ══════════════════════════════════════════════════════════════════════════════

ENV_FILE="${REPO_ROOT}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  pass ".env file exists"
else
  fail ".env file not found"
  warn "Run: cp .env.example .env  then fill in DATABASE_URL, SECRET_KEY, DEEPSEEK_API_KEY"
  record_fail ".env missing"
  echo -e "\n${RED}Cannot continue without .env. Aborting.${RESET}"
  exit 1
fi

# 2a. Check for placeholder values WITHOUT printing the actual values.
#     We grep for the placeholder strings from .env.example.
PLACEHOLDER_FOUND=false

check_placeholder() {
  local field="$1"
  local placeholder_pattern="$2"
  if grep -q "^${field}=${placeholder_pattern}" "${ENV_FILE}" 2>/dev/null; then
    fail "${field} still contains a placeholder value — update .env"
    record_fail "${field} is placeholder"
    PLACEHOLDER_FOUND=true
  else
    # Field exists and is not the placeholder
    if grep -q "^${field}=" "${ENV_FILE}" 2>/dev/null; then
      pass "${field} is set (value hidden)"
    else
      fail "${field} not found in .env"
      record_fail "${field} missing from .env"
      PLACEHOLDER_FOUND=true
    fi
  fi
}

# Match exact placeholder strings from .env.example (no real values printed)
check_placeholder "DATABASE_URL"     "postgresql+asyncpg://user:password@host:6543/postgres"
check_placeholder "SECRET_KEY"       "change-this-to-a-random-64-char-string"
check_placeholder "DEEPSEEK_API_KEY" "sk-your-deepseek-api-key"

# 2b. Warn if ENABLE_CREATE_ALL is not false (won't abort, but warn)
if grep -q "^ENABLE_CREATE_ALL=true" "${ENV_FILE}" 2>/dev/null; then
  warn "ENABLE_CREATE_ALL=true in .env — production should use false (Alembic manages schema)"
elif grep -q "^ENABLE_CREATE_ALL=false" "${ENV_FILE}" 2>/dev/null; then
  pass "ENABLE_CREATE_ALL=false (production mode)"
else
  warn "ENABLE_CREATE_ALL not set in .env — will default to true (development mode)"
fi

# 2c. Warn if CORS_ORIGINS is not a JSON array
if grep -q "^CORS_ORIGINS=" "${ENV_FILE}" 2>/dev/null; then
  CORS_LINE=$(grep "^CORS_ORIGINS=" "${ENV_FILE}" | head -1)
  if echo "${CORS_LINE}" | grep -q 'CORS_ORIGINS=\['; then
    pass "CORS_ORIGINS appears to be JSON array format"
  else
    warn "CORS_ORIGINS may not be a JSON array — must be: CORS_ORIGINS=[\"http://...\"]"
    record_fail "CORS_ORIGINS format"
  fi
fi

if [[ "${PLACEHOLDER_FOUND}" == "true" ]]; then
  echo -e "\n${RED}ERROR: Placeholder values detected in .env.${RESET}"
  echo "Edit .env and replace all placeholder values before deploying."
  echo "Aborting to prevent starting with broken configuration."
  exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
header "Step 3 — Validate docker compose config"
# ══════════════════════════════════════════════════════════════════════════════

info "Running: docker compose config (parse + interpolation check)"
if docker compose config --quiet 2>/dev/null; then
  pass "docker compose config OK — YAML is valid, all env vars interpolated"
else
  fail "docker compose config failed — check docker-compose.yml and .env"
  record_fail "compose config invalid"
  echo -e "\n${RED}Fix compose config errors before proceeding. Aborting.${RESET}"
  exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
header "Step 4 — Build images"
# ══════════════════════════════════════════════════════════════════════════════

info "Running: docker compose build"
info "This may take 3–8 minutes on first run (downloading base images + installing deps)"
echo ""

if docker compose build 2>&1; then
  pass "docker compose build completed successfully"
else
  fail "docker compose build failed"
  record_fail "docker compose build"
  echo -e "\n${RED}Build failed. Check output above. Aborting.${RESET}"
  exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
header "Step 5 — Start stack (redis → migrate → backend + frontend)"
# ══════════════════════════════════════════════════════════════════════════════

# Tear down any previous run to ensure clean state
info "Stopping any existing containers..."
docker compose down --remove-orphans 2>/dev/null || true

# 5a. Start Redis and wait for healthcheck
info "Starting redis..."
docker compose up -d redis
info "Waiting for redis healthcheck (up to 30s)..."
REDIS_READY=false
for i in $(seq 1 30); do
  STATUS=$(docker compose ps redis --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0].get('Health','') if isinstance(d,list) else d.get('Health',''))" 2>/dev/null || echo "")
  if [[ "${STATUS}" == "healthy" ]]; then
    REDIS_READY=true
    break
  fi
  sleep 1
done

if [[ "${REDIS_READY}" == "true" ]]; then
  pass "redis is healthy"
else
  warn "redis healthcheck timed out (30s) — proceeding anyway"
  docker compose logs redis 2>/dev/null | tail -5 || true
fi

# 5b. Run Alembic migration
info "Running Alembic migration (docker compose run --rm migrate)..."
MIGRATE_EXIT=0
docker compose run --rm migrate 2>&1 || MIGRATE_EXIT=$?

if [[ ${MIGRATE_EXIT} -eq 0 ]]; then
  pass "migrate completed successfully (exit 0)"
else
  fail "migrate failed (exit ${MIGRATE_EXIT})"
  record_fail "alembic migrate"
  warn "Check DATABASE_URL in .env — must be Supabase Transaction Pooler (port 6543)"
  warn "Check: docker compose logs migrate"
  # Don't abort — backend will fail to serve DB requests but we can still check nginx
fi

# 5c. Start backend and frontend
info "Starting backend and frontend..."
docker compose up -d backend frontend

# Wait for backend to be reachable (up to 30s)
info "Waiting for backend to accept connections (up to 30s)..."
BACKEND_READY=false
for i in $(seq 1 30); do
  if curl --noproxy '*' -sf http://localhost/api/v1/health &>/dev/null; then
    BACKEND_READY=true
    break
  fi
  sleep 1
done

if [[ "${BACKEND_READY}" == "true" ]]; then
  pass "backend is reachable via Nginx proxy"
else
  warn "backend not reachable after 30s (may still be starting)"
fi

# ══════════════════════════════════════════════════════════════════════════════
header "Step 6 — Container status"
# ══════════════════════════════════════════════════════════════════════════════

docker compose ps
echo ""

# ══════════════════════════════════════════════════════════════════════════════
header "Step 7 — Health checks"
# ══════════════════════════════════════════════════════════════════════════════

# 7a. Frontend (Nginx serves index.html on /)
info "GET http://localhost/"
HTTP_STATUS=$(curl --noproxy '*' -so /dev/null -w "%{http_code}" http://localhost/ 2>/dev/null || echo "000")
if [[ "${HTTP_STATUS}" == "200" ]]; then
  pass "Frontend: HTTP ${HTTP_STATUS}"
else
  fail "Frontend: HTTP ${HTTP_STATUS} (expected 200)"
  record_fail "frontend HTTP ${HTTP_STATUS}"
fi

# 7b. Backend health endpoint (through Nginx proxy)
info "GET http://localhost/api/v1/health"
HEALTH_BODY=$(curl --noproxy '*' -sf http://localhost/api/v1/health 2>/dev/null || echo "")
HEALTH_HTTP=$(curl --noproxy '*' -so /dev/null -w "%{http_code}" http://localhost/api/v1/health 2>/dev/null || echo "000")
if [[ "${HEALTH_HTTP}" == "200" ]]; then
  pass "Backend health: HTTP ${HEALTH_HTTP} — ${HEALTH_BODY}"
else
  fail "Backend health: HTTP ${HEALTH_HTTP}"
  record_fail "backend health HTTP ${HEALTH_HTTP}"
fi

# 7c. Redis PING
info "docker compose exec redis redis-cli ping"
REDIS_PONG=$(docker compose exec -T redis redis-cli ping 2>/dev/null || echo "FAILED")
if [[ "${REDIS_PONG}" == "PONG" ]]; then
  pass "Redis: PONG"
else
  fail "Redis: got '${REDIS_PONG}' (expected PONG)"
  record_fail "redis ping"
fi

# ══════════════════════════════════════════════════════════════════════════════
header "Step 8 — Frontend bundle check (no hardcoded localhost:8000)"
# ══════════════════════════════════════════════════════════════════════════════

info "Scanning compiled JS bundle for hardcoded 'localhost:8000'..."
BUNDLE_CHECK=$(docker compose exec -T frontend \
  sh -c 'grep -r "localhost:8000" /usr/share/nginx/html/assets/*.js 2>/dev/null | head -3' \
  || echo "")

if [[ -z "${BUNDLE_CHECK}" ]]; then
  pass "Bundle clean — no 'localhost:8000' found in JS assets"
else
  fail "Bundle contains hardcoded 'localhost:8000':"
  echo "    ${BUNDLE_CHECK}"
  record_fail "bundle hardcodes localhost:8000"
  warn "Fix: rebuild with VITE_API_BASE=/api/v1 — see deployment_docker.md §常见问题 1"
fi

# Also confirm /api/v1 is present (sanity check that VITE_API_BASE was injected)
info "Scanning bundle for '/api/v1' (VITE_API_BASE injection check)..."
API_BASE_CHECK=$(docker compose exec -T frontend \
  sh -c 'grep -l "api/v1" /usr/share/nginx/html/assets/*.js 2>/dev/null | head -1' \
  || echo "")

if [[ -n "${API_BASE_CHECK}" ]]; then
  pass "Bundle contains '/api/v1' — VITE_API_BASE correctly injected"
else
  fail "Bundle does not contain '/api/v1' — VITE_API_BASE may not have been injected"
  record_fail "bundle missing /api/v1"
fi

# ══════════════════════════════════════════════════════════════════════════════
header "Step 9 — Summary"
# ══════════════════════════════════════════════════════════════════════════════

echo ""
if [[ ${#FAILURES[@]} -eq 0 ]]; then
  echo -e "${GREEN}${BOLD}✓ PASS — All checks passed. Stack is healthy.${RESET}"
  echo ""
  echo "Next steps:"
  echo "  • Open http://localhost in a browser and verify the login page loads"
  echo "  • Register/login and run a CN stock analysis (e.g. CN/600519)"
  echo "  • Check browser DevTools Network — all /api/v1/* should return HTTP 200"
  echo "  • See docs/deployment_docker.md §浏览器端验证清单 for the full checklist"
  FINAL_EXIT=0
else
  echo -e "${RED}${BOLD}✗ FAIL — ${#FAILURES[@]} check(s) failed:${RESET}"
  for f in "${FAILURES[@]}"; do
    echo -e "    ${RED}•${RESET} ${f}"
  done
  echo ""
  echo "Troubleshooting:"
  echo "  docker compose logs backend   # FastAPI startup errors"
  echo "  docker compose logs frontend  # Nginx errors"
  echo "  docker compose logs migrate   # Alembic migration errors"
  echo "  docker compose logs redis     # Redis startup errors"
  echo "  docker compose ps             # Container exit codes"
  echo ""
  echo "See docs/deployment_docker.md §常见问题 for known failure patterns."
  FINAL_EXIT=1
fi

echo ""
echo "Completed: $(date '+%Y-%m-%d %H:%M:%S')"
exit ${FINAL_EXIT}
