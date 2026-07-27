<template>
  <div class="auth-page">
    <div class="auth-card card">
      <h1 class="card-title">Create Account</h1>
      <p class="auth-subtitle">You need an invite code to register.</p>

      <form @submit.prevent="handleRegister" class="auth-form">
        <div class="form-group">
          <label for="username">Username</label>
          <input
            id="username"
            v-model="username"
            type="text"
            autocomplete="username"
            placeholder="choose a username"
            required
          />
        </div>

        <div class="form-group">
          <label for="email">Email</label>
          <input
            id="email"
            v-model="email"
            type="email"
            autocomplete="email"
            placeholder="you@example.com"
            required
          />
        </div>

        <div class="form-group">
          <label for="password">Password</label>
          <input
            id="password"
            v-model="password"
            type="password"
            autocomplete="new-password"
            placeholder="请输入密码（至少8位）"
            minlength="8"
            required
          />
        </div>

        <div class="form-group">
          <label for="invite_code">8位邀请码</label>
          <input
            id="invite_code"
            v-model="inviteCode"
            type="text"
            autocomplete="off"
            placeholder="请输入8位邀请码"
            spellcheck="false"
            @input="onInviteInput"
            required
          />
          <p v-if="inviteFormatHint" class="field-hint">{{ inviteFormatHint }}</p>
        </div>

        <div v-if="errorMsg" class="auth-error">{{ errorMsg }}</div>

        <button type="submit" class="btn btn-primary auth-submit" :disabled="loading">
          <span v-if="loading" class="spinner" />
          <span v-else>Create Account</span>
        </button>
      </form>

      <p class="auth-footer">
        Already have an account?
        <RouterLink to="/login">Log in</RouterLink>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const authStore  = useAuthStore()
const router     = useRouter()

const username        = ref('')
const email           = ref('')
const password        = ref('')
const inviteCode      = ref('')
const loading         = ref(false)
const errorMsg        = ref('')

// Valid new-format character set (uppercase letters + digits, no O/0/I/1)
const NEW_CODE_CHARS = /^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]+$/

// Live format hint for the invite code field (only for 8-char new-format input)
const inviteFormatHint = computed(() => {
  const v = inviteCode.value.trim()
  if (!v || v.length !== 8) return ''
  if (!NEW_CODE_CHARS.test(v.toUpperCase())) {
    return '邀请码包含无效字符，请检查后重新输入'
  }
  return ''
})

function onInviteInput() {
  const v = inviteCode.value
  // Auto-uppercase only when input looks like a new 8-char code (short input)
  // Preserve original case for longer legacy codes (> 8 chars)
  if (v.length <= 8) {
    inviteCode.value = v.toUpperCase()
  }
}

async function handleRegister() {
  errorMsg.value = ''
  loading.value  = true
  try {
    await authStore.register(username.value.trim(), email.value.trim(), password.value, inviteCode.value.trim())
    router.push('/login')
  } catch (err) {
    errorMsg.value = err.message || '注册失败，请检查邀请码是否有效'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  background: var(--bg-primary);
}

.auth-card {
  width: 100%;
  max-width: 400px;
  padding: 2rem 2rem 1.5rem;
}

.card-title {
  margin: 0 0 0.25rem;
  font-size: 1.5rem;
  font-weight: 700;
  background: var(--accent-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.auth-subtitle {
  margin: 0 0 1.5rem;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.field-hint {
  margin: 0.25rem 0 0;
  font-size: 0.78rem;
  color: #f87171;
}

.auth-error {
  padding: 0.5rem 0.875rem;
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.12);
  color: #f87171;
  font-size: 0.82rem;
}

.auth-submit {
  width: 100%;
  margin-top: 0.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  min-height: 2.6rem;
}

.auth-footer {
  margin: 1.25rem 0 0;
  text-align: center;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.auth-footer a {
  color: var(--accent-primary);
  text-decoration: none;
}

.auth-footer a:hover {
  text-decoration: underline;
}
</style>
