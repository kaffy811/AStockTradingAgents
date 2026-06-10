<template>
  <div class="meta-bar">
    <div class="generated-at">
      📅 生成时间：{{ formatTime(metadata.generated_at) }}
      &nbsp;·&nbsp; {{ market }} / {{ symbol }}
    </div>
  </div>

  <div class="agent-badges">
    <span
      v-for="(info, name) in metadata.agents"
      :key="name"
      :class="['agent-badge', badgeClass(info.status)]"
    >
      <span class="dot"></span>
      {{ agentLabel(name) }}
      <span style="opacity:0.7;font-weight:400">({{ info.status }})</span>
      <span v-if="info.message" :title="info.message" style="cursor:help">ⓘ</span>
    </span>
  </div>
</template>

<script setup>
import { agentLabel, badgeClass, formatTime } from '../utils/warningMap.js'

defineProps({
  metadata: { type: Object, required: true },
  market:   { type: String, required: true },
  symbol:   { type: String, required: true },
})
</script>

<style scoped>
.meta-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 16px;
}

.generated-at {
  font-size: 12px;
  color: var(--muted);
}

.agent-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
</style>
