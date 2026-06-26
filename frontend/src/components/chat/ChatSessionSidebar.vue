<template>
  <div class="session-sidebar" :class="{ collapsed: isCollapsed }">
    <!-- Toggle button -->
    <button class="sidebar-toggle" @click="isCollapsed = !isCollapsed" :title="isCollapsed ? t('chat_sidebar_expand') : t('chat_sidebar_collapse')">
      <span>{{ isCollapsed ? '›' : '‹' }}</span>
    </button>

    <template v-if="!isCollapsed">
      <div class="sidebar-header">
        <span class="sidebar-title">{{ t('chat_sessions_title') }}</span>
        <button class="btn-new" @click="$emit('new-session')" :title="t('chat_sessions_new')">+</button>
      </div>

      <div class="session-list">
        <div
          v-if="sessions.length === 0"
          class="session-empty"
        >
          {{ t('chat_sessions_empty') }}
        </div>
        <div
          v-for="s in sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === activeSessionId }"
          @click="$emit('select-session', s.id)"
        >
          <div class="session-preview">{{ s.preview || t('chat_sessions_new') }}</div>
          <div class="session-meta">{{ formatDate(s.created_at) }}</div>
          <button
            class="session-delete"
            @click.stop="$emit('delete-session', s.id)"
            :title="t('chat_sessions_delete')"
          >×</button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from '../../utils/i18n.js'

const { t } = useI18n()

defineProps({
  sessions: { type: Array, default: () => [] },
  activeSessionId: { type: String, default: null },
})

defineEmits(['new-session', 'select-session', 'delete-session'])

const isCollapsed = ref(false)

function formatDate(dateStr) {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}
</script>

<style scoped>
.session-sidebar {
  position: relative;
  width: 200px;
  flex-shrink: 0;
  background: var(--surface-card, var(--surface));
  border-right: 1px solid var(--border-soft);
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease;
  overflow: hidden;
}

.session-sidebar.collapsed {
  width: 28px;
}

.sidebar-toggle {
  position: absolute;
  top: 8px;
  right: 4px;
  width: 20px;
  height: 20px;
  border: none;
  background: none;
  cursor: pointer;
  color: var(--muted);
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  z-index: 1;
  padding: 0;
}

.sidebar-toggle:hover {
  background: var(--border-soft);
  color: var(--text);
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px 8px 10px;
  padding-right: 28px;
  border-bottom: 1px solid var(--border-soft);
}

.sidebar-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
}

.btn-new {
  width: 20px;
  height: 20px;
  border: 1px solid var(--border-soft);
  background: none;
  border-radius: 4px;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 16px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.btn-new:hover {
  background: var(--status-info-bg);
  color: var(--accent);
  border-color: var(--accent);
}

.session-list {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: thin;
}

.session-empty {
  font-size: 12px;
  color: var(--muted);
  text-align: center;
  padding: 16px 8px;
}

.session-item {
  position: relative;
  padding: 8px 28px 8px 10px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-soft);
  transition: background 0.15s;
}

.session-item:hover {
  background: var(--surface);
}

.session-item.active {
  background: var(--status-info-bg);
  border-left: 2px solid var(--accent);
}

.session-preview {
  font-size: 12px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-meta {
  font-size: 10px;
  color: var(--muted);
  margin-top: 2px;
}

.session-delete {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  border: none;
  background: none;
  color: var(--muted);
  font-size: 14px;
  cursor: pointer;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  opacity: 0;
  transition: opacity 0.15s;
}

.session-item:hover .session-delete {
  opacity: 1;
}

.session-delete:hover {
  background: var(--status-down-bg, #fee2e2);
  color: var(--danger);
}

@media (max-width: 640px) {
  .session-sidebar {
    display: none;
  }
}
</style>
