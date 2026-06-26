<template>
  <div class="agent-trace" v-if="agentTrace && agentTrace.length">
    <!-- Header (collapsible) -->
    <button class="agent-trace-header" @click="collapsed = !collapsed" type="button">
      <span class="agent-trace-icon-header">🔬</span>
      <span class="agent-trace-title">多 Agent 研究过程</span>
      <span class="agent-trace-count">{{ agentTrace.length }} 步</span>
      <span class="agent-trace-chevron" :class="{ rotated: !collapsed }">▶</span>
    </button>

    <!-- Step list -->
    <Transition name="trace-expand">
      <div v-if="!collapsed" class="agent-trace-list">
        <div
          v-for="(item, i) in agentTrace"
          :key="i"
          class="agent-trace-item"
          :class="`trace-item--${item.status}`"
        >
          <!-- Status icon -->
          <span class="trace-status-icon">{{ statusIcon(item.status) }}</span>

          <!-- Content -->
          <div class="trace-content">
            <div class="trace-name">{{ item.displayName || item.name }}</div>
            <div v-if="item.summary" class="trace-summary">{{ item.summary }}</div>
            <div v-if="item.riskFlags && item.riskFlags.length" class="trace-flags">
              <span
                v-for="flag in item.riskFlags.slice(0, 3)"
                :key="flag"
                class="trace-flag-badge"
              >{{ flag }}</span>
            </div>
          </div>

          <!-- Running indicator -->
          <span v-if="item.status === 'running'" class="trace-spinner"></span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  agentTrace: {
    type: Array,
    default: () => [],
  },
})

const collapsed = ref(false)

function statusIcon(status) {
  const map = {
    running:  '⟳',
    success:  '✅',
    partial:  '⚠️',
    failed:   '❌',
    error:    '❌',
    warning:  '⚠️',
    skipped:  '⏭',
  }
  return map[status] ?? '●'
}
</script>

<style scoped>
.agent-trace {
  margin: 8px 0;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  overflow: hidden;
  background: var(--surface2);
  font-size: 13px;
}

/* ── Header ──────────────────────────────────────────────────────────────────── */
.agent-trace-header {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 7px 12px;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
  transition: background 0.15s;
}
.agent-trace-header:hover { background: var(--surface3, rgba(0,0,0,0.04)); }

.agent-trace-icon-header { font-size: 14px; }
.agent-trace-title { flex: 1; color: var(--muted); }
.agent-trace-count {
  font-size: 11px;
  color: var(--muted);
  background: var(--surface3, rgba(0,0,0,0.06));
  border-radius: 10px;
  padding: 1px 7px;
}
.agent-trace-chevron {
  color: var(--muted);
  font-size: 10px;
  transition: transform 0.2s;
  display: inline-block;
}
.agent-trace-chevron.rotated { transform: rotate(90deg); }

/* ── Step list ───────────────────────────────────────────────────────────────── */
.agent-trace-list {
  border-top: 1px solid var(--border-soft);
  padding: 6px 0;
}

.agent-trace-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 5px 12px;
  transition: background 0.1s;
}
.agent-trace-item:hover { background: var(--surface3, rgba(0,0,0,0.03)); }

.trace-status-icon {
  font-size: 14px;
  width: 20px;
  text-align: center;
  flex-shrink: 0;
  margin-top: 1px;
}

.trace-content { flex: 1; min-width: 0; }

.trace-name {
  font-weight: 600;
  color: var(--text);
  font-size: 12px;
  line-height: 1.4;
}

.trace-summary {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.4;
  margin-top: 2px;
  word-break: break-word;
}

.trace-flags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 3px;
}

.trace-flag-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--status-warn-bg, rgba(234,179,8,0.12));
  color: var(--status-warn, #b45309);
  border: 1px solid var(--status-warn-ring, rgba(234,179,8,0.25));
}

/* Running spinner */
.trace-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--border-soft);
  border-top-color: var(--accent, #4a90e2);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
  margin-top: 3px;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Status-specific row tints */
.trace-item--failed   { opacity: 0.85; }
.trace-item--partial  { opacity: 0.9; }
.trace-item--error    { opacity: 0.85; }

/* Expand/collapse transition */
.trace-expand-enter-active,
.trace-expand-leave-active {
  transition: max-height 0.25s ease, opacity 0.2s ease;
  overflow: hidden;
}
.trace-expand-enter-from,
.trace-expand-leave-to {
  max-height: 0;
  opacity: 0;
}
.trace-expand-enter-to,
.trace-expand-leave-from {
  max-height: 600px;
  opacity: 1;
}
</style>
