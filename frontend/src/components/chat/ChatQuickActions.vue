<template>
  <div class="quick-actions">
    <div class="qa-header">
      <span class="qa-label">{{ t('chat_quick_start') }}</span>
      <button class="qa-shuffle" @click="shuffle" :title="t('chat_qa_shuffle')">
        <span>↻</span> {{ t('chat_qa_shuffle') }}
      </button>
    </div>
    <div class="qa-chips">
      <button
        v-for="q in currentSet"
        :key="q.prompt"
        class="qa-chip"
        @click="$emit('fill', q.prompt)"
      >
        <span class="qa-chip-icon">{{ q.icon }}</span>
        <span class="qa-chip-text">{{ q.prompt }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from '../../utils/i18n.js'

defineEmits(['fill'])

const { t } = useI18n()

// 3 sets of 5 curated questions, cycling through on each shuffle
const SETS = [
  [
    { icon: '📊', prompt: '中船特气最近为什么涨这么多？' },
    { icon: '📈', prompt: '今天哪些行业值得重点研究？' },
    { icon: '🔍', prompt: '贵州茅台最新财报表现如何？' },
    { icon: '💡', prompt: 'AI 热潮带动了哪些半导体设备公司？' },
    { icon: '📋', prompt: '帮我解读最近一份历史报告' },
  ],
  [
    { icon: '⚠️', prompt: '688146 最大的投资风险有哪些？' },
    { icon: '📰', prompt: '新能源行业最近有什么重要新闻？' },
    { icon: '🏢', prompt: '当前哪个行业热度最高？' },
    { icon: '🔎', prompt: '帮我分析贵州茅台的基本面' },
    { icon: '💾', prompt: '分析 688146 并保存到历史报告' },
  ],
  [
    { icon: '📉', prompt: '半导体行业最近有哪些热门股？' },
    { icon: '🌏', prompt: '港股最近哪些板块值得关注？' },
    { icon: '⭐', prompt: '查看我的自选股' },
    { icon: '⚖️', prompt: '对比宁德时代和比亚迪的基本面' },
    { icon: '🗞️', prompt: '最近哪些公司有业绩超预期？' },
  ],
]

const setIndex = ref(0)

const currentSet = computed(() => SETS[setIndex.value])

function shuffle() {
  setIndex.value = (setIndex.value + 1) % SETS.length
}
</script>

<style scoped>
.quick-actions {
  width: 100%;
  max-width: 640px;
}

.qa-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.qa-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}

.qa-shuffle {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted);
  background: none;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  padding: 3px 8px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.qa-shuffle:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.qa-chips {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.qa-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  text-align: left;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--surface-card, var(--surface));
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  padding: 9px 14px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.qa-chip:hover {
  background: var(--status-info-bg);
  border-color: var(--accent);
  color: var(--accent);
}

.qa-chip:active { transform: scale(0.99); }

.qa-chip-icon {
  font-size: 15px;
  flex-shrink: 0;
}

.qa-chip-text {
  flex: 1;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 640px) {
  .qa-chip { font-size: 12px; padding: 8px 12px; }
  .qa-chip-icon { font-size: 14px; }
}
</style>
