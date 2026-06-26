<template>
  <div class="context-panel">
    <div class="cp-section">
      <h3 class="cp-title">{{ t('chat_title') }}</h3>
      <p class="cp-subtitle">{{ t('chat_subtitle') }}</p>
    </div>

    <!-- ── C9 Agent Skills ─────────────────────────────────────────────────── -->
    <div class="cp-section">
      <div class="cp-section-label">{{ t('chat_skills_title') }}</div>
      <div v-if="skillsError" class="cp-skills-unavailable">
        {{ t('chat_skills_unavailable') }}
      </div>
      <ul v-else class="cp-list">
        <li v-for="skill in displaySkills" :key="skill.name">
          🔹 {{ skill.display_name }}
        </li>
      </ul>
    </div>

    <!-- ── Session Memory (C8) ─────────────────────────────────────────────── -->
    <div v-if="sessionId" class="cp-section cp-memory-section">
      <div class="cp-memory-header">
        <div class="cp-section-label">{{ t('chat_mem_title') }}</div>
        <button
          v-if="recentSymbols.length > 0"
          class="cp-mem-clear-btn"
          :disabled="clearing"
          @click="onClearMemory"
        >{{ clearing ? '…' : t('chat_mem_clear') }}</button>
      </div>

      <div class="cp-memory-body">
        <div class="cp-mem-label">{{ t('chat_mem_recent_stocks') }}</div>
        <div v-if="recentSymbols.length === 0" class="cp-mem-empty">
          {{ t('chat_mem_empty') }}
        </div>
        <div v-else class="cp-mem-chips">
          <span
            v-for="sym in recentSymbols"
            :key="sym"
            class="cp-mem-chip"
          >{{ sym }}</span>
        </div>

        <div class="cp-mem-safety">{{ t('chat_mem_safety') }}</div>
      </div>
    </div>

    <div class="cp-section cp-demo-notice">
      <span class="cp-demo-icon">ℹ</span>
      <p class="cp-demo-text">{{ t('chat_demo_notice') }}</p>
    </div>

    <div class="cp-disclaimer">
      {{ t('chat_disclaimer') }}
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import { useI18n } from '../../utils/i18n.js'
import { getChatSkills, getChatSessionMemory, clearChatSessionMemory } from '../../api/chat.js'

const { t } = useI18n()

const props = defineProps({
  sessionId: { type: String, default: null },
})

// ── Skills (C9) ───────────────────────────────────────────────────────────────
const allSkills  = ref([])
const skillsError = ref(false)

const displaySkills = computed(() =>
  allSkills.value.filter(s => s.enabled && s.available).slice(0, 6)
)

async function loadSkills() {
  try {
    const data = await getChatSkills()
    allSkills.value = data?.items ?? []
    skillsError.value = false
  } catch {
    skillsError.value = true
  }
}

// ── Memory (C8) ───────────────────────────────────────────────────────────────
const recentSymbols = ref([])
const clearing      = ref(false)

async function loadMemory() {
  if (!props.sessionId) return
  try {
    const data = await getChatSessionMemory(props.sessionId)
    recentSymbols.value = (data?.memory?.recent_symbols ?? []).slice(0, 3)
  } catch {
    // memory load failure is non-critical
  }
}

async function onClearMemory() {
  if (!props.sessionId || clearing.value) return
  clearing.value = true
  try {
    await clearChatSessionMemory(props.sessionId)
    recentSymbols.value = []
  } catch {
    // ignore
  } finally {
    clearing.value = false
  }
}

// Reload memory whenever sessionId changes or on mount
watch(() => props.sessionId, (id) => { if (id) loadMemory() })
onMounted(() => {
  loadSkills()
  if (props.sessionId) loadMemory()
})
</script>

<style scoped>
.context-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.cp-section {
  background: var(--surface-card, var(--surface));
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-card);
  padding: 14px 16px;
  box-shadow: var(--shadow-card);
}

.cp-title {
  font-size: 15px;
  font-weight: 700;
  background: var(--accent-gradient, var(--accent));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 4px;
}

.cp-subtitle {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
}

.cp-section-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin-bottom: 8px;
}

.cp-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cp-list li {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.cp-skills-unavailable {
  font-size: 12px;
  color: var(--muted);
  font-style: italic;
}

/* Memory section */
.cp-memory-section {
  padding: 12px 16px;
}

.cp-memory-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.cp-memory-header .cp-section-label {
  margin-bottom: 0;
}

.cp-mem-clear-btn {
  font-size: 11px;
  color: var(--accent);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  opacity: 0.8;
}
.cp-mem-clear-btn:hover { opacity: 1; }
.cp-mem-clear-btn:disabled { opacity: 0.4; cursor: default; }

.cp-memory-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cp-mem-label {
  font-size: 11px;
  color: var(--muted);
}

.cp-mem-empty {
  font-size: 12px;
  color: var(--muted);
  font-style: italic;
}

.cp-mem-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.cp-mem-chip {
  font-size: 11px;
  background: var(--status-info-bg);
  color: var(--text-secondary);
  border: 1px solid var(--border-soft);
  border-radius: 4px;
  padding: 2px 6px;
}

.cp-mem-safety {
  font-size: 10px;
  color: var(--muted);
  line-height: 1.4;
  margin-top: 2px;
}

.cp-demo-notice {
  display: flex;
  gap: 8px;
  background: var(--status-info-bg);
  border-color: var(--status-info-ring);
}

.cp-demo-icon {
  font-size: 16px;
  color: var(--accent);
  flex-shrink: 0;
}

.cp-demo-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.cp-disclaimer {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.5;
  padding: 0 4px;
}
</style>
