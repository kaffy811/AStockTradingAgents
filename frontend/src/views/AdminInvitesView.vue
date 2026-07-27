<template>
  <div class="admin-invites">
    <div class="admin-header">
      <h1>Invite Management</h1>
      <span class="admin-badge">Admin</span>
    </div>

    <div v-if="authError" class="error-banner">
      {{ authError }}
    </div>

    <!-- Create invite form -->
    <section class="card create-section">
      <h2>Create Invite Code</h2>
      <form @submit.prevent="createInvite" class="create-form">
        <label>
          Bind to Email (optional)
          <input v-model="form.email" type="email" placeholder="user@example.com" />
        </label>
        <label>
          Max Uses
          <input v-model.number="form.max_uses" type="number" min="1" max="100" />
        </label>
        <label>
          Note (optional)
          <input v-model="form.note" type="text" maxlength="500" placeholder="e.g. Beta tester, Wave 1" />
        </label>
        <button type="submit" :disabled="creating">
          {{ creating ? 'Creating…' : 'Create Invite' }}
        </button>
      </form>

      <!-- Show the generated code once -->
      <div v-if="newCode" class="code-reveal">
        <p class="code-label">Copy this code now — it will not be shown again:</p>
        <div class="code-box">
          <span class="code-text">{{ newCode }}</span>
          <button class="copy-btn" @click="copyCode">{{ copied ? 'Copied!' : 'Copy' }}</button>
        </div>
        <button class="dismiss-btn" @click="newCode = null">Dismiss</button>
      </div>
    </section>

    <!-- Invite list -->
    <section class="card list-section">
      <div class="list-header">
        <h2>All Invite Codes</h2>
        <button @click="loadInvites" :disabled="loading" class="refresh-btn">
          {{ loading ? 'Loading…' : 'Refresh' }}
        </button>
      </div>

      <div v-if="invites.length === 0 && !loading" class="empty-state">
        No invite codes yet.
      </div>

      <table v-else class="invite-table">
        <thead>
          <tr>
            <th>Prefix</th>
            <th>Email</th>
            <th>Uses</th>
            <th>Status</th>
            <th>Note</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="inv in invites" :key="inv.id" :class="{ redeemed: inv.redeemed }">
            <td class="mono">{{ inv.code_prefix }}…</td>
            <td>{{ inv.email || '—' }}</td>
            <td>{{ inv.use_count }} / {{ inv.max_uses }}</td>
            <td>
              <span :class="statusClass(inv)">{{ statusLabel(inv) }}</span>
            </td>
            <td class="note-cell">{{ inv.note || '' }}</td>
            <td class="date-cell">{{ formatDate(inv.created_at) }}</td>
            <td>
              <button
                v-if="!inv.redeemed"
                class="revoke-btn"
                @click="revokeInvite(inv.id)"
              >Revoke</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const invites = ref([])
const loading = ref(false)
const creating = ref(false)
const authError = ref(null)
const newCode = ref(null)
const copied = ref(false)

const form = ref({
  email: '',
  max_uses: 1,
  note: '',
})

function getToken() {
  return localStorage.getItem('access_token') || ''
}

function authHeaders() {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${getToken()}`,
  }
}

async function loadInvites() {
  loading.value = true
  authError.value = null
  try {
    const res = await fetch(`${API_BASE}/mvp/admin/invites`, {
      headers: authHeaders(),
    })
    if (res.status === 403) {
      authError.value = 'Access denied — admin account required.'
      return
    }
    if (res.status === 401) {
      authError.value = 'Not logged in. Please log in as an admin user.'
      return
    }
    invites.value = await res.json()
  } catch (e) {
    authError.value = `Failed to load invites: ${e.message}`
  } finally {
    loading.value = false
  }
}

async function createInvite() {
  creating.value = true
  newCode.value = null
  authError.value = null
  try {
    const body = {
      max_uses: form.value.max_uses || 1,
      email: form.value.email || null,
      note: form.value.note || null,
    }
    const res = await fetch(`${API_BASE}/mvp/invites`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
    })
    if (res.status === 403) {
      authError.value = 'Access denied — admin account required.'
      return
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      authError.value = err.detail || 'Failed to create invite.'
      return
    }
    const data = await res.json()
    newCode.value = data.invite_code
    form.value = { email: '', max_uses: 1, note: '' }
    await loadInvites()
  } finally {
    creating.value = false
  }
}

async function revokeInvite(id) {
  if (!confirm('Revoke this invite code? This cannot be undone.')) return
  authError.value = null
  try {
    const res = await fetch(`${API_BASE}/mvp/admin/invites/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
    if (!res.ok && res.status !== 204) {
      authError.value = 'Failed to revoke invite.'
      return
    }
    await loadInvites()
  } catch (e) {
    authError.value = `Error: ${e.message}`
  }
}

async function copyCode() {
  if (!newCode.value) return
  try {
    await navigator.clipboard.writeText(newCode.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // fallback: select text
  }
}

function statusLabel(inv) {
  if (inv.redeemed) return 'Redeemed'
  if (inv.expires_at && new Date(inv.expires_at) < new Date()) return 'Expired'
  if (inv.use_count >= inv.max_uses) return 'Used up'
  return 'Active'
}

function statusClass(inv) {
  const label = statusLabel(inv)
  if (label === 'Active') return 'badge badge-active'
  if (label === 'Redeemed') return 'badge badge-redeemed'
  return 'badge badge-expired'
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

onMounted(loadInvites)
</script>

<style scoped>
.admin-invites {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px 16px;
  font-family: var(--font-sans, system-ui, sans-serif);
}

.admin-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.admin-header h1 {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
  color: var(--color-text-primary, #111);
}

.admin-badge {
  background: #7c3aed;
  color: #fff;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.error-banner {
  background: #fef2f2;
  border: 1px solid #fca5a5;
  color: #dc2626;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 20px;
  font-size: 0.9rem;
}

.card {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
}

.card h2 {
  font-size: 1rem;
  font-weight: 600;
  margin: 0 0 16px;
  color: var(--color-text-primary, #111);
}

.create-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.create-form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85rem;
  color: var(--color-text-secondary, #555);
}

.create-form input {
  padding: 8px 12px;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 6px;
  font-size: 0.9rem;
  background: var(--color-input-bg, #f9fafb);
  color: var(--color-text-primary, #111);
}

.create-form button[type="submit"] {
  align-self: flex-start;
  padding: 8px 20px;
  background: #7c3aed;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}

.create-form button[type="submit"]:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.code-reveal {
  margin-top: 16px;
  background: #f0fdf4;
  border: 1px solid #86efac;
  border-radius: 8px;
  padding: 16px;
}

.code-label {
  font-size: 0.85rem;
  color: #166534;
  margin: 0 0 8px;
}

.code-box {
  display: flex;
  align-items: center;
  gap: 8px;
}

.code-text {
  font-family: monospace;
  font-size: 0.95rem;
  word-break: break-all;
  color: #111;
  background: #fff;
  border: 1px solid #d1fae5;
  border-radius: 4px;
  padding: 6px 10px;
  flex: 1;
}

.copy-btn,
.dismiss-btn {
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 0.85rem;
  cursor: pointer;
  border: 1px solid #86efac;
  background: #fff;
  color: #166534;
  font-weight: 600;
}

.dismiss-btn {
  margin-top: 10px;
  display: block;
  border-color: #d1d5db;
  color: #555;
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.refresh-btn {
  padding: 6px 14px;
  border: 1px solid var(--color-border, #d1d5db);
  background: var(--color-surface, #fff);
  border-radius: 6px;
  font-size: 0.85rem;
  cursor: pointer;
  color: var(--color-text-secondary, #555);
}

.empty-state {
  text-align: center;
  padding: 32px;
  color: var(--color-text-secondary, #9ca3af);
  font-size: 0.9rem;
}

.invite-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.invite-table th {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
  color: var(--color-text-secondary, #6b7280);
  font-weight: 600;
}

.invite-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-border, #f3f4f6);
  color: var(--color-text-primary, #111);
}

.invite-table tr.redeemed td {
  opacity: 0.5;
}

.mono {
  font-family: monospace;
}

.note-cell {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.date-cell {
  white-space: nowrap;
  font-size: 0.8rem;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

.badge-active {
  background: #d1fae5;
  color: #065f46;
}

.badge-redeemed {
  background: #e0e7ff;
  color: #3730a3;
}

.badge-expired {
  background: #fee2e2;
  color: #991b1b;
}

.revoke-btn {
  padding: 4px 10px;
  border: 1px solid #fca5a5;
  background: #fff;
  color: #dc2626;
  border-radius: 4px;
  font-size: 0.8rem;
  cursor: pointer;
}

.revoke-btn:hover {
  background: #fef2f2;
}
</style>
