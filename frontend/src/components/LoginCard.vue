<template>
  <div class="app-shell">
    <div class="login-card card">
      <div class="card-title">🤖 TradingAgents — 登录</div>
      <div class="login-form">
        <div class="form-group">
          <label>用户名</label>
          <input
            v-model="form.username"
            placeholder="username"
            @keyup.enter="handleLogin"
            :disabled="loading"
          />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input
            v-model="form.password"
            type="password"
            placeholder="password"
            @keyup.enter="handleLogin"
            :disabled="loading"
          />
        </div>
        <button class="btn btn-primary" @click="handleLogin" :disabled="loading">
          <span v-if="loading"><span class="spinner"></span>登录中...</span>
          <span v-else>登录</span>
        </button>
        <div v-if="error" class="error-box">{{ error }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useAuthStore } from '../stores/auth.js'

const authStore = useAuthStore()
const form      = reactive({ username: '', password: '' })
const loading   = ref(false)
const error     = ref('')

async function handleLogin() {
  if (!form.username || !form.password) return
  loading.value = true
  error.value   = ''
  try {
    await authStore.login(form.username, form.password)
  } catch (e) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-card {
  max-width: 400px;
  margin: 60px auto 0;
}

.login-card :deep(.card-title) {
  font-size: 17px;
  text-align: center;
  margin-bottom: 22px;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.login-form .form-group {
  width: 100%;
}

.login-form input {
  width: 100%;
}
</style>
