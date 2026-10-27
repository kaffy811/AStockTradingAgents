<template>
  <div class="auth-page" :class="{ 'auth-page--embedded': embedded }">
    <section class="auth-card card" aria-label="账户登录">
      <h1 class="card-title">TradingAgents</h1>
      <p class="auth-subtitle">使用 Google 账户进入 AI 股票研究工作台</p>
      <p v-if="authStore.sessionExpired" class="auth-alert" role="status">登录已过期，请重新登录后查看行情、新闻和财报数据。</p>

      <p v-if="state === 'loading'" role="status">正在加载 Google 登录…</p>
      <div ref="googleButton" class="google-button" :inert="state !== 'ready' || undefined" :aria-hidden="state !== 'ready'" />
      <p v-if="state === 'choosing'" role="status">请在 Google 窗口中选择账户。若已关闭窗口，可停止等待后重试。</p>
      <p v-if="state === 'submitting'" role="status">正在验证身份并登录…</p>
      <p v-if="state === 'cancelled'" role="status">已停止等待。若 Google 窗口仍打开，可将其关闭后重新尝试。</p>
      <p v-if="state === 'disabled'" class="auth-error" role="alert">Google 登录暂未配置，请联系管理员。</p>
      <p v-if="errorMessage" class="auth-error" role="alert">{{ errorMessage }}</p>
      <button v-if="busy" class="btn btn-ghost" type="button" @click="cancel">停止等待</button>
      <button v-if="['error', 'cancelled', 'disabled'].includes(state)" class="btn btn-primary" type="button" @click="prepare">重新尝试 Google 登录</button>
      <p class="auth-note">首次登录将自动创建普通账户。已有旧账户需要迁移时，请联系管理员核实身份。</p>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { googleConfigApi } from '../api/auth.js'
import { loadGoogleIdentity } from '../utils/googleIdentity.js'
import { useAuthStore } from '../stores/auth.js'

defineProps({ embedded: { type: Boolean, default: false } })
const authStore = useAuthStore()
const router = useRouter()
const state = ref('loading')
const errorMessage = ref('')
const googleButton = ref(null)
const busy = computed(() => ['loading', 'choosing', 'submitting'].includes(state.value))
let disposed = false
let generation = 0
let controller
let submitTimer

function cancel() {
  generation++
  controller?.abort()
  clearTimeout(submitTimer)
  try { window.google?.accounts?.id?.cancel() } catch { /* SDK may be unavailable */ }
  state.value = 'cancelled'
  errorMessage.value = ''
}

async function prepare() {
  const current = ++generation
  controller?.abort()
  controller = new AbortController()
  errorMessage.value = ''
  state.value = 'loading'
  try {
    const config = await googleConfigApi({ signal: controller.signal })
    if (disposed || generation !== current) return
    if (!config.enabled) { state.value = 'disabled'; return }
    await loadGoogleIdentity()
    if (disposed || generation !== current) return
    state.value = 'ready'
    await nextTick()
    if (disposed || generation !== current) return
    window.google.accounts.id.initialize({
      client_id: config.client_id, nonce: config.nonce, auto_select: false,
      callback: async ({ credential }) => {
        if (disposed || generation !== current || !['ready', 'choosing'].includes(state.value)) return
        state.value = 'submitting'
        // Stop waiting on a lost HTTP response; do not claim that a server-side
        // account transaction was undone or that a Google popup was closed.
        submitTimer = setTimeout(() => controller.abort(), 15000)
        try {
          await authStore.loginGoogle(credential, { signal: controller.signal })
          if (!disposed && generation === current) await router.replace('/')
        } catch (err) {
          if (!disposed && generation === current) {
            state.value = 'error'
            errorMessage.value = err.name === 'AbortError'
              ? '登录响应等待超时，请重新尝试。' : (err.message || 'Google 登录失败，请重试。')
          }
        } finally { clearTimeout(submitTimer) }
      },
    })
    googleButton.value.replaceChildren()
    window.google.accounts.id.renderButton(googleButton.value, {
      theme: 'outline', size: 'large', locale: 'zh_CN',
      click_listener: () => { if (generation === current) state.value = 'choosing' },
    })
  } catch (err) {
    if (!disposed && generation === current) {
      state.value = 'error'
      errorMessage.value = err.message || 'Google 登录暂不可用，请重试。'
    }
  }
}

onMounted(prepare)
onBeforeUnmount(() => {
  disposed = true
  generation++
  controller?.abort()
  clearTimeout(submitTimer)
})
</script>

<style scoped>
.auth-page { min-height: 100dvh; display: flex; align-items: center; justify-content: center; padding: 1.5rem; background: var(--bg-primary); }
.auth-page--embedded { min-height: auto; }
.auth-card { width: 100%; max-width: 400px; padding: 2rem; }
.card-title { margin: 0 0 0.5rem; font-size: 1.5rem; font-weight: 700; }
.auth-subtitle, .auth-note { color: var(--text-secondary); font-size: 0.85rem; line-height: 1.7; }
.google-button { margin: 1.5rem 0; min-height: 44px; }
.google-button[aria-hidden="true"] { display: none; }
.auth-alert, .auth-error { padding: 0.75rem; border-radius: 8px; background: rgba(239,68,68,0.1); color: var(--status-warn, #f87171); font-size: 0.85rem; line-height: 1.6; }
.auth-note { margin-top: 1.5rem; }
</style>
