<template>
  <div class="auth-page">
    <div class="auth-card card">
      <h1 class="card-title">创建账号</h1>
      <p class="auth-subtitle">需要邀请码才能注册。</p>

      <form @submit.prevent="handleRegister" class="auth-form" autocomplete="off">

        <!-- ── 邮箱 ── -->
        <div class="form-group">
          <label for="reg-email">邮箱</label>
          <input
            id="reg-email"
            v-model="email"
            type="email"
            autocomplete="email"
            placeholder="请输入邮箱"
            :disabled="codeSent"
            required
          />
        </div>

        <!-- ── 8位邀请码 ── -->
        <div class="form-group">
          <label for="reg-invite">8位邀请码</label>
          <input
            id="reg-invite"
            v-model="inviteCode"
            type="text"
            autocomplete="off"
            placeholder="请输入8位邀请码"
            spellcheck="false"
            :disabled="codeSent"
            @input="onInviteInput"
            required
          />
          <p v-if="inviteFormatHint" class="field-hint">{{ inviteFormatHint }}</p>
        </div>

        <!-- ── 发送验证码 ── -->
        <div class="code-row">
          <div class="form-group code-input-group">
            <label for="reg-code">邮箱验证码</label>
            <input
              id="reg-code"
              v-model="verificationCode"
              type="text"
              inputmode="numeric"
              autocomplete="one-time-code"
              placeholder="6位数字"
              maxlength="6"
              pattern="\d{6}"
              required
            />
          </div>
          <button
            type="button"
            class="btn send-code-btn"
            :disabled="sendDisabled"
            @click="handleSendCode"
          >
            <span v-if="sendLoading" class="spinner" />
            <span v-else-if="countdown > 0">{{ countdown }}s 后重发</span>
            <span v-else>{{ codeSent ? '重新发送' : '发送验证码' }}</span>
          </button>
        </div>

        <div v-if="sendError" class="auth-error">{{ sendError }}</div>

        <!-- ── 分隔线 ── -->
        <div class="divider" />

        <!-- ── 用户名 ── -->
        <div class="form-group">
          <label for="reg-username">用户名</label>
          <input
            id="reg-username"
            v-model="username"
            type="text"
            autocomplete="username"
            placeholder="3–32 个字符"
            minlength="3"
            maxlength="32"
            required
          />
        </div>

        <!-- ── 密码 ── -->
        <div class="form-group">
          <label for="reg-password">密码</label>
          <input
            id="reg-password"
            v-model="password"
            type="password"
            autocomplete="new-password"
            placeholder="请输入密码（至少8位）"
            minlength="8"
            required
          />
        </div>

        <!-- ── 确认密码 ── -->
        <div class="form-group">
          <label for="reg-confirm">确认密码</label>
          <input
            id="reg-confirm"
            v-model="confirmPassword"
            type="password"
            autocomplete="new-password"
            placeholder="再次输入密码"
            required
          />
          <p v-if="passwordMismatch" class="field-hint">两次密码不一致</p>
        </div>

        <div v-if="errorMsg" class="auth-error">{{ errorMsg }}</div>

        <button
          type="submit"
          class="btn btn-primary auth-submit"
          :disabled="loading || passwordMismatch"
        >
          <span v-if="loading" class="spinner" />
          <span v-else>注 册</span>
        </button>
      </form>

      <p class="auth-footer">
        已有账号？<RouterLink to="/login">登录</RouterLink>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const authStore = useAuthStore()
const router    = useRouter()

// ── Form state ─────────────────────────────────────────────────────────────
const email            = ref('')
const inviteCode       = ref('')
const verificationCode = ref('')
const username         = ref('')
const password         = ref('')
const confirmPassword  = ref('')

// ── UI state ───────────────────────────────────────────────────────────────
const codeSent   = ref(false)
const sendLoading = ref(false)
const loading    = ref(false)
const sendError  = ref('')
const errorMsg   = ref('')
const countdown  = ref(0)

let countdownTimer = null

// ── Computed ───────────────────────────────────────────────────────────────
const NEW_CODE_RE = /^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]+$/

const inviteFormatHint = computed(() => {
  const v = inviteCode.value.trim()
  if (!v || v.length !== 8) return ''
  if (!NEW_CODE_RE.test(v.toUpperCase())) return '邀请码包含无效字符，请重新检查'
  return ''
})

const passwordMismatch = computed(() =>
  confirmPassword.value.length > 0 && password.value !== confirmPassword.value
)

const sendDisabled = computed(() =>
  sendLoading.value || countdown.value > 0 || !email.value || !inviteCode.value
)

// ── Invite code auto-uppercase ─────────────────────────────────────────────
function onInviteInput() {
  if (inviteCode.value.length <= 8) {
    inviteCode.value = inviteCode.value.toUpperCase()
  }
}

// ── Countdown ─────────────────────────────────────────────────────────────
function startCountdown(seconds = 60) {
  countdown.value = seconds
  clearInterval(countdownTimer)
  countdownTimer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) clearInterval(countdownTimer)
  }, 1000)
}

onUnmounted(() => clearInterval(countdownTimer))

// ── Send verification code ─────────────────────────────────────────────────
async function handleSendCode() {
  sendError.value  = ''
  sendLoading.value = true
  try {
    await authStore.requestEmailVerification(email.value.trim(), inviteCode.value.trim())
    codeSent.value = true
    startCountdown(60)
  } catch (err) {
    sendError.value = err.message || '发送失败，请检查邀请码是否有效'
  } finally {
    sendLoading.value = false
  }
}

// ── Register ───────────────────────────────────────────────────────────────
async function handleRegister() {
  errorMsg.value = ''
  if (passwordMismatch.value) return
  loading.value = true
  try {
    await authStore.register(
      username.value.trim(),
      email.value.trim(),
      password.value,
      inviteCode.value.trim(),
      verificationCode.value.trim() || undefined,
    )
    router.push('/login')
  } catch (err) {
    errorMsg.value = err.message || '注册失败，请检查填写内容'
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
  max-width: 440px;
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
  gap: 0.875rem;
}

/* Verification code row: input + button side by side */
.code-row {
  display: flex;
  gap: 0.625rem;
  align-items: flex-end;
}

.code-input-group {
  flex: 1;
}

.send-code-btn {
  flex-shrink: 0;
  min-width: 108px;
  height: 2.4rem;
  font-size: 0.82rem;
  padding: 0 0.75rem;
  background: var(--surface-card);
  color: var(--accent-primary);
  border: 1px solid var(--accent-primary);
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
}

.send-code-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.send-code-btn:not(:disabled):hover {
  background: var(--accent-primary);
  color: #fff;
}

.divider {
  border-top: 1px solid var(--border-soft);
  margin: 0.25rem 0;
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
