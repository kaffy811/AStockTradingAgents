<template>
  <!-- Mobile: horizontal chips at top -->
  <nav class="cfan-root" ref="navRef">
    <div class="cfan-list">
      <button
        v-for="sec in sections"
        :key="sec.id"
        :data-section="sec.id"
        :class="[
          'cfan-item',
          { 'cfan-item--active': sec.id === resolvedActive },
          { 'cfan-item--planned': sec.planned },
        ]"
        @click="onNavClick(sec)"
      >
        {{ sec.label }}
        <span v-if="sec.planned" class="cfan-planned-badge">即将</span>
      </button>
    </div>
  </nav>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  sections: { type: Array, default: () => [] },
  activeSectionId: { type: String, default: '' },
})

const emit = defineEmits(['navigate'])

const navRef = ref(null)
const immediateActive = ref(null)

const resolvedActive = computed(() => immediateActive.value || props.activeSectionId)

function onNavClick(sec) {
  if (sec.planned) return
  emit('navigate', sec.id)
  // Immediately set active — observer will confirm later
  immediateActive.value = sec.id
  setTimeout(() => { immediateActive.value = null }, 1000)
}

// Auto-scroll active chip into view on mobile
watch(() => props.activeSectionId, (id) => {
  nextTick(() => {
    const chip = navRef.value?.querySelector(`[data-section="${id}"]`)
    chip?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
  })
})
</script>

<style scoped>
.cfan-root {
  width: 180px;
  flex-shrink: 0;
  position: sticky;
  top: 16px;
  align-self: flex-start;
  max-height: calc(100vh - 120px);
  /* overflow: clip prevents scroll-container creation so wheel events reach the page */
  overflow: clip;
}

.cfan-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.cfan-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  background: none;
  border: none;
  border-radius: 6px;
  padding: 7px 10px;
  font-size: 13px;
  color: var(--color-text-secondary, #555);
  cursor: pointer;
  text-align: left;
  transition: background 0.15s, color 0.15s;
  line-height: 1.3;
}

.cfan-item:hover {
  background: #f0f4fd;
  color: #1a73e8;
}

.cfan-item--active {
  background: #e8f0fe;
  color: #1a73e8;
  font-weight: 600;
}

.cfan-item--planned {
  color: var(--color-text-secondary, #aaa);
  opacity: 0.65;
}

.cfan-item--planned:hover {
  background: #f5f5f5;
  color: #aaa;
}

.cfan-planned-badge {
  font-size: 10px;
  background: #e0e0e0;
  color: #888;
  border-radius: 3px;
  padding: 1px 4px;
  flex-shrink: 0;
  margin-left: 4px;
}

/* Mobile: horizontal scrollable chips */
@media (max-width: 640px) {
  .cfan-root {
    width: 100%;
    position: relative;
    top: 0;
    max-height: none;
    overflow-y: visible;
    overflow-x: auto;
  }

  .cfan-list {
    flex-direction: row;
    flex-wrap: nowrap;
    gap: 6px;
    padding-bottom: 4px;
  }

  .cfan-item {
    flex-shrink: 0;
    white-space: nowrap;
    border-radius: 20px;
    padding: 5px 12px;
    background: #f0f0f0;
    border: 1px solid #e0e0e0;
  }

  .cfan-item--active {
    background: #e8f0fe;
    border-color: #1a73e8;
    color: #1a73e8;
  }
}
</style>
