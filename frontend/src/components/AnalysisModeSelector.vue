<template>
  <div class="mode-selector card">
    <div class="mode-header">
      <span class="mode-title">{{ t('mode_title') }}</span>
      <span class="mode-hint">{{ t('mode_hint') }}</span>
    </div>
    <div class="mode-grid">
      <button
        v-for="mode in MODES"
        :key="mode.value"
        :class="['mode-chip', { 'mode-chip--active': modelValue === mode.value }]"
        :title="mode.desc"
        @click="emit('update:modelValue', mode.value)"
      >
        <span class="mode-icon">{{ mode.icon }}</span>
        <span class="mode-label">{{ mode.label }}</span>
        <span class="mode-desc">{{ mode.desc }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../utils/i18n.js'

const props = defineProps({
  modelValue: { type: String, default: 'comprehensive' },
})

const emit = defineEmits(['update:modelValue'])

const { t } = useI18n()

const MODES = computed(() => [
  {
    value: 'comprehensive',
    label: t('mode_comprehensive'),
    icon:  '🔬',
    desc:  t('mode_comprehensive_desc'),
  },
  {
    value: 'technical_only',
    label: t('mode_technical'),
    icon:  '📈',
    desc:  t('mode_technical_desc'),
  },
  {
    value: 'fundamental_only',
    label: t('mode_fundamental'),
    icon:  '📊',
    desc:  t('mode_fundamental_desc'),
  },
  {
    value: 'peer_only',
    label: t('mode_peer'),
    icon:  '🏢',
    desc:  t('mode_peer_desc'),
  },
  {
    value: 'news_only',
    label: t('mode_news'),
    icon:  '📰',
    desc:  t('mode_news_desc'),
  },
  {
    value: 'technical_fundamental',
    label: t('mode_tech_fund'),
    icon:  '🔭',
    desc:  t('mode_tech_fund_desc'),
  },
])
</script>

<style scoped>
.mode-selector {
  padding: 14px 16px 12px;
}

.mode-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
}

.mode-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.mode-hint {
  font-size: 11px;
  color: var(--muted);
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}

.mode-chip {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  background: var(--surface2);
  border: 1.5px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
  text-align: left;
}

.mode-chip:hover {
  border-color: var(--accent);
  background: var(--surface-hover);
}

.mode-chip--active {
  border-color: var(--accent);
  background: var(--status-info-bg);
}

.mode-icon {
  font-size: 15px;
  line-height: 1;
  margin-bottom: 2px;
}

.mode-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.3;
}

.mode-chip--active .mode-label {
  color: var(--accent);
}

.mode-desc {
  font-size: 10px;
  color: var(--muted);
  line-height: 1.4;
}

/* ── Mobile: 2 columns on narrow screens ── */
@media (max-width: 480px) {
  .mode-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* ── Very narrow: 1 column ── */
@media (max-width: 300px) {
  .mode-grid {
    grid-template-columns: 1fr;
  }
}
</style>
