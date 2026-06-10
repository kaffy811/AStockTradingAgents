<template>
  <!-- Dev mode only: collapsible SSE event log -->
  <div class="aet-wrap">
    <div class="aet-toolbar">
      <button class="aet-toggle btn btn-secondary btn-sm" @click="open = !open">
        {{ open ? '▾' : '▸' }} SSE 事件日志 ({{ events.length }})
      </button>
      <button v-if="open && events.length > 0" class="aet-clear btn btn-secondary btn-sm" @click="$emit('clear')">
        清空
      </button>
    </div>
    <div v-if="open" class="aet-list">
      <div
        v-for="(evt, i) in displayEvents"
        :key="evt.event_id ?? i"
        class="aet-row"
        :class="`aet-row--${evt.event}`"
      >
        <span class="aet-eid" title="event_id">#{{ evt.event_id ?? i }}</span>
        <span class="aet-type">{{ evt.event }}</span>
        <span v-if="evt.agent" class="aet-agent">{{ evt.agent }}</span>
        <span v-if="evt.progress !== undefined" class="aet-pct">{{ evt.progress }}%</span>
        <span v-if="evt.error" class="aet-err">{{ evt.error }}</span>
        <span v-if="elapsedMs(evt) !== null" class="aet-elapsed">+{{ elapsedMs(evt) }}ms</span>
        <span class="aet-ts">{{ shortTs(evt.timestamp) }}</span>
      </div>
      <div v-if="events.length > MAX_DISPLAY" class="aet-more">
        … 共 {{ events.length }} 条，仅显示最新 {{ MAX_DISPLAY }} 条
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  events: { type: Array, default: () => [] },
})

defineEmits(['clear'])

const open = ref(false)
const MAX_DISPLAY = 30

const displayEvents = computed(() => {
  const all = props.events
  if (all.length <= MAX_DISPLAY) return all
  return all.slice(all.length - MAX_DISPLAY)
})

// Compute elapsed ms from first event's timestamp
const _firstTs = computed(() => {
  const first = props.events[0]
  if (!first?.timestamp) return null
  try { return new Date(first.timestamp).getTime() } catch { return null }
})

function elapsedMs(evt) {
  if (_firstTs.value === null || !evt.timestamp) return null
  try {
    const ms = new Date(evt.timestamp).getTime() - _firstTs.value
    return ms >= 0 ? ms : null
  } catch { return null }
}

function shortTs(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toTimeString().slice(0, 8)
  } catch {
    return iso
  }
}
</script>

<style scoped>
.aet-wrap {
  margin-top: 8px;
  font-size: 12px;
}

.aet-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
}

.aet-toggle,
.aet-clear {
  font-size: 11px;
  padding: 2px 8px;
  opacity: 0.7;
}

.aet-list {
  margin-top: 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  max-height: 280px;
  overflow-y: auto;
  background: var(--bg-alt, var(--bg));
}

.aet-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
  border-bottom: 1px solid var(--border);
  font-family: monospace;
  flex-wrap: wrap;
}

.aet-row:last-child { border-bottom: none; }

.aet-eid     { color: var(--muted); min-width: 36px; }
.aet-type    { font-weight: 600; min-width: 140px; color: var(--accent); }
.aet-agent   { color: var(--text); min-width: 80px; }
.aet-pct     { color: var(--success, #4caf50); min-width: 36px; }
.aet-err     { color: var(--error, #e53935); flex: 1; }
.aet-elapsed { color: var(--muted); font-size: 10px; min-width: 56px; }
.aet-ts      { color: var(--muted); margin-left: auto; white-space: nowrap; }

.aet-row--analysis_failed .aet-type,
.aet-row--agent_failed    .aet-type { color: var(--error, #e53935); }
.aet-row--report_ready    .aet-type,
.aet-row--agent_completed .aet-type { color: var(--success, #4caf50); }

.aet-more {
  color: var(--muted);
  font-size: 11px;
  padding-top: 4px;
  text-align: center;
}
</style>
