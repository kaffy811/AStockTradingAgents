<template>
  <div class="card">
    <div class="card-title">📂 各维度子报告（点击展开）</div>
    <p v-if="visibleSections.length === 0" class="section-empty">本次分析无可展示的子报告。</p>
    <div class="section-accordion">
      <div v-for="sec in visibleSections" :key="sec.key" class="section-item">

        <div class="section-header" @click="toggleSection(sec.key)">
          <div class="section-header-left">
            <span class="section-icon">{{ sec.icon }}</span>
            <span class="section-name">{{ sec.label }}</span>
            <span class="section-chars">
              ({{ (sections[sec.key] || '').length }} 字)
            </span>
          </div>
          <div class="section-header-right">
            <span
              :class="['agent-badge', badgeClass(agents[sec.key]?.status)]"
              style="padding:2px 8px;font-size:11px"
            >
              {{ agents[sec.key]?.status || 'unknown' }}
            </span>
            <span :class="['section-chevron', openSections[sec.key] ? 'open' : '']">▼</span>
          </div>
        </div>

        <div v-if="openSections[sec.key]" class="section-body">
          <MarkdownReport :content="sections[sec.key] || '（无内容）'" />
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { SECTION_DEFS, badgeClass } from '../utils/warningMap.js'
import MarkdownReport from './MarkdownReport.vue'

const props = defineProps({
  sections: { type: Object, required: true },
  agents:   { type: Object, required: true },
})

const openSections = ref({})

function toggleSection(key) {
  openSections.value[key] = !openSections.value[key]
}

// Only show sections that were actually run (have content and are not skipped)
const visibleSections = computed(() =>
  SECTION_DEFS.filter(sec => {
    const content = props.sections[sec.key]
    const status  = props.agents[sec.key]?.status
    return content && status !== 'skipped'
  })
)
</script>

<style scoped>
.section-empty {
  font-size: 13px;
  color: var(--muted);
  padding: 8px 0;
  margin: 0;
}

.section-accordion {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 20px;
}

.section-item {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.15s;
}

.section-item:hover { border-color: #3a4060; }

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
}

.section-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-icon { font-size: 16px; }

.section-name {
  font-size: 14px;
  font-weight: 600;
}

.section-chars {
  font-size: 11px;
  color: var(--muted);
}

.section-chevron {
  font-size: 12px;
  color: var(--muted);
  transition: transform 0.2s;
}

.section-chevron.open { transform: rotate(180deg); }

.section-body {
  padding: 16px;
  border-top: 1px solid var(--border);
  max-height: 520px;
  overflow-y: auto;
}
</style>
