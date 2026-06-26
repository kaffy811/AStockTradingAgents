<template>
  <div v-if="steps.length > 0" class="reasoning-steps">
    <button class="rs-toggle" @click="open = !open">
      <span class="rs-icon">{{ open ? '▾' : '▸' }}</span>
      <span class="rs-label">{{ t('chat_research_steps') }}</span>
      <span class="rs-count">({{ steps.length }})</span>
    </button>

    <transition name="rs-fade">
      <div v-if="open" class="rs-list">
        <div
          v-for="(step, idx) in steps"
          :key="idx"
          class="rs-item"
          :class="`rs-status-${step.status || 'success'}`"
        >
          <span class="rs-step-icon">{{ statusIcon(step.status) }}</span>
          <div class="rs-step-body">
            <span class="rs-step-name">{{ step.name }}</span>
            <span v-if="step.detail" class="rs-step-detail">{{ step.detail }}</span>
          </div>
          <span v-if="step.duration_ms" class="rs-duration">{{ step.duration_ms }}ms</span>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from '../../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  steps: { type: Array, default: () => [] },
})

// Open by default when any step is in progress (shows research steps immediately)
const open = ref(props.steps.some(s => s.status === 'running' || s.status === 'pending'))

function statusIcon(status) {
  if (status === 'failed' || status === 'error')  return '✕'
  if (status === 'running')   return '◌'
  if (status === 'pending')   return '○'
  if (status === 'skipped')   return '—'
  if (status === 'partial')   return '◑'
  if (status === 'stopped')   return '□'
  return '✓'   // completed / success / default
}
</script>

<style scoped>
.reasoning-steps {
  margin: 4px 0;
}

.rs-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  font-size: 11px;
  color: var(--muted);
  transition: color 0.15s, background 0.15s;
}

.rs-toggle:hover {
  color: var(--accent);
  background: var(--status-info-bg);
}

.rs-icon { font-size: 10px; }
.rs-label { font-weight: 600; }
.rs-count { color: var(--muted); }

.rs-list {
  margin-top: 4px;
  border-left: 2px solid var(--border-soft);
  padding-left: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rs-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 11px;
}

.rs-step-icon {
  font-size: 10px;
  width: 14px;
  flex-shrink: 0;
  margin-top: 1px;
}

.rs-status-success .rs-step-icon { color: var(--status-up, #16a34a); }
.rs-status-error   .rs-step-icon { color: var(--danger, #dc2626); }
.rs-status-running .rs-step-icon { color: var(--accent); }
.rs-status-pending  .rs-step-icon { color: var(--muted); }
.rs-status-failed   .rs-step-icon { color: var(--danger, #dc2626); }
.rs-status-skipped  .rs-step-icon { color: var(--muted); opacity: 0.5; }
.rs-status-partial  .rs-step-icon { color: var(--warning, #d97706); }
.rs-status-stopped  .rs-step-icon { color: var(--muted); }

.rs-step-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.rs-step-name {
  color: var(--text-secondary);
  font-weight: 500;
}

.rs-status-skipped .rs-step-name { text-decoration: line-through; opacity: 0.6; }

.rs-step-detail {
  color: var(--muted);
  font-size: 10px;
}

.rs-duration {
  color: var(--muted);
  font-size: 10px;
  flex-shrink: 0;
}

.rs-fade-enter-active,
.rs-fade-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}
.rs-fade-enter-from,
.rs-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
