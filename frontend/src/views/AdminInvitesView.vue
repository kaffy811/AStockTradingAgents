<template>
  <div class="admin-page">

    <!-- ── Server auth loading ───────────────────────────────────────────── -->
    <div v-if="authLoading" class="auth-loading">
      <span class="spinner" />
      <span>正在验证身份…</span>
    </div>

    <!-- ── 403 guard (server-confirmed) ─────────────────────────────────── -->
    <div v-else-if="!serverConfirmedAdmin" class="forbidden-card card">
      <h2>403 — 权限不足</h2>
      <p>此页面仅管理员可访问。</p>
      <RouterLink to="/" class="btn btn-primary">返回首页</RouterLink>
    </div>

    <!-- ── Admin UI (only after server confirms is_admin=true) ───────────── -->
    <template v-else>
      <div class="admin-header">
        <h1 class="admin-title">管理后台 — 邀请码</h1>
        <span class="admin-badge">Admin</span>
      </div>

      <!-- Global error -->
      <div v-if="globalError" class="alert-error">{{ globalError }}</div>

      <!-- ── Create form ─────────────────────────────────────────────────── -->
      <section class="card create-section">
        <h2 class="section-title">生成邀请码</h2>
        <form @submit.prevent="createInvite" class="create-form">
          <div class="form-group">
            <label>绑定邮箱（可选）</label>
            <input v-model="form.email" type="email" placeholder="user@example.com" />
          </div>
          <div class="form-group">
            <label>最大使用次数</label>
            <input v-model.number="form.max_uses" type="number" min="1" max="100" />
          </div>
          <div class="form-group">
            <label>备注（可选）</label>
            <input v-model="form.note" type="text" maxlength="500" placeholder="e.g. 内测用户 Wave 1" />
          </div>
          <button type="submit" class="btn btn-primary" :disabled="creating">
            <span v-if="creating" class="spinner" />
            <span v-else>生成邀请码</span>
          </button>
        </form>

        <!-- ── One-time code reveal ───────────────────────────────────────── -->
        <div v-if="newCode" class="code-reveal">
          <p class="code-reveal-warning">
            ⚠️ 完整邀请码只显示一次，请立即复制并安全传递给用户。
          </p>
          <div class="code-box">
            <span class="code-text">{{ newCode }}</span>
            <button type="button" class="copy-btn" @click="copyCode">
              {{ copied ? '✓ 已复制' : '复制' }}
            </button>
          </div>
          <button type="button" class="dismiss-btn" @click="newCode = null">
            我已保存，关闭
          </button>
        </div>
      </section>

      <!-- ── Invite list ─────────────────────────────────────────────────── -->
      <section class="card list-section">
        <div class="list-header">
          <h2 class="section-title">全部邀请码</h2>
          <button type="button" class="btn-refresh" @click="loadInvites" :disabled="loading">
            {{ loading ? '加载中…' : '刷新' }}
          </button>
        </div>

        <p v-if="!loading && invites.length === 0" class="empty-state">
          暂无邀请码，点击上方生成。
        </p>

        <div v-else class="invite-list">
          <div
            v-for="inv in invites"
            :key="inv.id"
            class="invite-row"
            :class="{ 'invite-row--used': inv.redeemed || inv.use_count >= inv.max_uses }"
          >
            <div class="inv-main">
              <span class="inv-code mono">{{ inv.code_prefix }}••••</span>
              <span :class="badgeClass(inv)" class="badge">{{ statusLabel(inv) }}</span>
            </div>
            <div class="inv-meta">
              <span v-if="inv.email" class="meta-item">📧 {{ inv.email }}</span>
              <span class="meta-item">{{ inv.use_count }}/{{ inv.max_uses }} 次</span>
              <span class="meta-item date">创建 {{ formatDate(inv.created_at) }}</span>
              <span v-if="inv.redeemed_at" class="meta-item date">使用 {{ formatDate(inv.redeemed_at) }}</span>
              <span v-if="inv.note" class="meta-item note">{{ inv.note }}</span>
            </div>
            <div class="inv-actions">
              <button
                v-if="!inv.redeemed && inv.use_count < inv.max_uses"
                type="button"
                class="revoke-btn"
                @click="revokeInvite(inv)"
              >撤销</button>
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const authStore = useAuthStore()

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'

// ── Server-side admin confirmation ────────────────────────────────────────
// We always call /auth/me on mount so that a user who manually sets
// ta_is_admin=true in localStorage cannot bypass the server-side guard.
const authLoading         = ref(true)
const serverConfirmedAdmin = ref(false)

// ── State ─────────────────────────────────────────────────────────────────
const invites     = ref([])
const loading     = ref(false)
const creating    = ref(false)
const globalError = ref('')
const newCode     = ref(null)
const copied      = ref(false)

const form = ref({ email: '', max_uses: 1, note: '' })

// ── Helpers ───────────────────────────────────────────────────────────────
function authHeaders() {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${localStorage.getItem('ta_token') || ''}`,
  }
}

// ── Load invites ──────────────────────────────────────────────────────────
async function loadInvites() {
  if (!authStore.isAdmin) return
  loading.value    = true
  globalError.value = ''
  try {
    const res = await fetch(`${API_BASE}/admin/invites`, { headers: authHeaders() })
    if (res.status === 403) { globalError.value = '权限不足，请以管理员账号登录。'; return }
    if (!res.ok) { globalError.value = `加载失败 (${res.status})`; return }
    invites.value = await res.json()
  } catch (e) {
    globalError.value = `网络错误：${e.message}`
  } finally {
    loading.value = false
  }
}

// ── Create invite ─────────────────────────────────────────────────────────
async function createInvite() {
  creating.value   = true
  newCode.value    = null
  globalError.value = ''
  try {
    const body = {
      max_uses: form.value.max_uses || 1,
      email:    form.value.email    || null,
      note:     form.value.note     || null,
    }
    const res = await fetch(`${API_BASE}/admin/invites`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
    })
    if (res.status === 403) { globalError.value = '权限不足。'; return }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      globalError.value = err.detail || '生成失败'
      return
    }
    const data = await res.json()
    newCode.value = data.invite_code
    form.value    = { email: '', max_uses: 1, note: '' }
    await loadInvites()
  } finally {
    creating.value = false
  }
}

// ── Revoke invite ─────────────────────────────────────────────────────────
async function revokeInvite(inv) {
  if (!confirm(`确定撤销邀请码 ${inv.code_prefix}？此操作不可恢复。`)) return
  globalError.value = ''
  try {
    const res = await fetch(`${API_BASE}/admin/invites/${inv.id}/revoke`, {
      method: 'POST',
      headers: authHeaders(),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      globalError.value = err.detail || '撤销失败'
      return
    }
    await loadInvites()
  } catch (e) {
    globalError.value = `错误：${e.message}`
  }
}

// ── Copy code ─────────────────────────────────────────────────────────────
async function copyCode() {
  if (!newCode.value) return
  try {
    await navigator.clipboard.writeText(newCode.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2500)
  } catch { /* fallback: user selects manually */ }
}

// ── Display helpers ───────────────────────────────────────────────────────
function statusLabel(inv) {
  if (inv.redeemed) return '已使用'
  if (inv.expires_at && new Date(inv.expires_at) < new Date()) return '已过期'
  if (inv.use_count >= inv.max_uses) return '已用完'
  return '有效'
}

function badgeClass(inv) {
  const l = statusLabel(inv)
  if (l === '有效') return 'badge--active'
  if (l === '已使用') return 'badge--used'
  return 'badge--expired'
}

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

// ── Server-side admin check ───────────────────────────────────────────────
// Always call /auth/me first; only proceed if server returns is_admin=true.
// This prevents localStorage tampering from granting access.
async function verifyAdminAndLoad() {
  authLoading.value = true
  try {
    await authStore.fetchMe()
    if (authStore.isAdmin) {
      serverConfirmedAdmin.value = true
      await loadInvites()
    } else {
      serverConfirmedAdmin.value = false
    }
  } catch {
    serverConfirmedAdmin.value = false
  } finally {
    authLoading.value = false
  }
}

onMounted(verifyAdminAndLoad)
</script>

<style scoped>
.admin-page {
  max-width: 860px;
  margin: 0 auto;
  padding: 1.5rem 1rem 3rem;
}

/* ── Auth loading ───────────────────────────────────────────────────────── */
.auth-loading {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  justify-content: center;
  padding: 3rem 2rem;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

/* ── 403 ────────────────────────────────────────────────────────────────── */
.forbidden-card {
  text-align: center;
  padding: 3rem 2rem;
}

.forbidden-card h2 {
  font-size: 1.5rem;
  margin: 0 0 0.5rem;
  color: var(--text-primary);
}

.forbidden-card p {
  color: var(--text-secondary);
  margin: 0 0 1.5rem;
}

/* ── Header ─────────────────────────────────────────────────────────────── */
.admin-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.admin-title {
  font-size: 1.375rem;
  font-weight: 700;
  margin: 0;
  color: var(--text-primary);
}

.admin-badge {
  background: #7c3aed;
  color: #fff;
  font-size: 0.7rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

/* ── Alert ──────────────────────────────────────────────────────────────── */
.alert-error {
  margin-bottom: 1rem;
  padding: 0.625rem 1rem;
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.1);
  color: #f87171;
  font-size: 0.85rem;
}

/* ── Card sections ──────────────────────────────────────────────────────── */
.create-section, .list-section {
  margin-bottom: 1.25rem;
}

.section-title {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0 0 1rem;
  color: var(--text-primary);
}

/* ── Create form ────────────────────────────────────────────────────────── */
.create-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

/* ── Code reveal ────────────────────────────────────────────────────────── */
.code-reveal {
  margin-top: 1.25rem;
  padding: 1rem;
  border-radius: 8px;
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.code-reveal-warning {
  font-size: 0.82rem;
  color: #4ade80;
  margin: 0 0 0.75rem;
}

.code-box {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.code-text {
  font-family: monospace;
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: 4px;
  background: rgba(0,0,0,0.2);
  padding: 0.4rem 0.75rem;
  border-radius: 6px;
  color: #4ade80;
  flex: 1;
}

.copy-btn {
  padding: 0.4rem 0.875rem;
  border-radius: 6px;
  border: 1px solid #4ade80;
  background: transparent;
  color: #4ade80;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
}

.copy-btn:hover { background: rgba(74,222,128,0.1); }

.dismiss-btn {
  display: block;
  margin-top: 0.75rem;
  padding: 0.4rem 0.875rem;
  border-radius: 6px;
  border: 1px solid var(--border-soft);
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.82rem;
  cursor: pointer;
}

/* ── List header ────────────────────────────────────────────────────────── */
.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.btn-refresh {
  background: none;
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  padding: 0.3rem 0.75rem;
  font-size: 0.82rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }

.empty-state {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

/* ── Invite rows ────────────────────────────────────────────────────────── */
.invite-list {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.invite-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.75rem 0.875rem;
  border-radius: 8px;
  background: var(--surface-card);
  border: 1px solid var(--border-soft);
  transition: opacity 0.15s;
}

.invite-row--used {
  opacity: 0.5;
}

.inv-main {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  min-width: 0;
}

.inv-code {
  font-family: monospace;
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--text-primary);
}

.inv-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem 0.875rem;
  flex: 1;
  font-size: 0.78rem;
  color: var(--text-secondary);
}

.meta-item.note {
  font-style: italic;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inv-actions {
  flex-shrink: 0;
}

/* ── Badge ──────────────────────────────────────────────────────────────── */
.badge {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 700;
}

.badge--active  { background: rgba(74,222,128,0.15); color: #4ade80; }
.badge--used    { background: rgba(139,92,246,0.15); color: #a78bfa; }
.badge--expired { background: rgba(239,68,68,0.15);  color: #f87171; }

/* ── Revoke button ──────────────────────────────────────────────────────── */
.revoke-btn {
  padding: 0.3rem 0.7rem;
  border: 1px solid rgba(239,68,68,0.4);
  background: transparent;
  color: #f87171;
  border-radius: 5px;
  font-size: 0.78rem;
  cursor: pointer;
}

.revoke-btn:hover { background: rgba(239,68,68,0.1); }
</style>
