<template>
  <div class="card">
    <div class="loading-bar"><div class="loading-bar-fill"></div></div>
    <div class="loading-hint">
      <span class="spinner"></span>
      {{ loadingHint || '正在并行调用技术面、基本面、同行对比、新闻面四个 Agent，请稍候...' }}
    </div>
    <div v-if="elapsedSeconds > 0" class="elapsed-hint">
      已等待 {{ elapsedSeconds }} 秒
    </div>
    <div class="agent-row">
      <span v-for="name in AGENT_NAMES" :key="name" class="agent-badge badge-timeout">
        <span class="spinner" style="width:10px;height:10px;border-width:1.5px"></span>
        {{ agentLabel(name) }}
      </span>
    </div>
    <div v-if="cancellable" class="cancel-row">
      <button class="btn btn-secondary btn-sm" @click="$emit('cancel')">
        取消分析
      </button>
    </div>
  </div>
</template>

<script setup>
import { AGENT_NAMES, agentLabel } from '../utils/warningMap.js'

defineProps({
  elapsedSeconds: { type: Number, default: 0 },
  loadingHint:    { type: String, default: '' },
  cancellable:    { type: Boolean, default: false },
})

defineEmits(['cancel'])
</script>

<style scoped>
.loading-bar {
  width: 100%;
  height: 3px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 16px;
}

.loading-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent2));
  border-radius: 2px;
  animation: shimmer 1.6s ease-in-out infinite;
  width: 40%;
}

@keyframes shimmer {
  0%   { margin-left: -40%; }
  100% { margin-left: 100%; }
}

.loading-hint {
  text-align: center;
  color: var(--muted);
  font-size: 13px;
  padding: 12px 0 4px;
}

.elapsed-hint {
  text-align: center;
  color: var(--muted);
  font-size: 12px;
  padding-bottom: 8px;
  opacity: 0.75;
}

.agent-row {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.cancel-row {
  margin-top: 20px;
  display: flex;
  justify-content: center;
}
</style>
