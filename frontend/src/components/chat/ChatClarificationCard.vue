<template>
  <div v-if="candidates.length" class="clarification-card" data-testid="clarification-card">
    <div v-if="clarification.prompt" class="clar-prompt">{{ clarification.prompt }}</div>
    <div class="clar-candidates">
      <button
        v-for="cand in candidates"
        :key="candKey(cand)"
        class="clar-candidate"
        type="button"
        :disabled="disabled"
        @click="$emit('select', cand)"
      >
        <span class="clar-name">{{ cand.display_name }}</span>
        <span v-if="cand.symbol" class="clar-symbol">{{ cand.symbol }}</span>
        <span v-if="showMarket(cand)" class="clar-market">{{ cand.market }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { candidateKey, dedupCandidates } from '../../utils/clarification.js'

const props = defineProps({
  clarification: { type: Object, default: () => ({}) },
  disabled:      { type: Boolean, default: false },
})
defineEmits(['select'])

// Deduplicate defensively even if the backend already deduped.
const candidates = computed(() => dedupCandidates(props.clarification?.candidates))

function candKey(cand) {
  return candidateKey(cand)
}

function showMarket(cand) {
  return cand.market && cand.market !== 'CN'
}
</script>

<style scoped>
.clarification-card {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.clar-prompt {
  font-size: 13px;
  color: var(--text-secondary, #666);
}
.clar-candidates {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.clar-candidate {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border-color, #d9d9d9);
  border-radius: 16px;
  background: var(--bg-card, #fff);
  cursor: pointer;
  font-size: 13px;
  transition: border-color 0.15s ease;
}
.clar-candidate:hover:not(:disabled) {
  border-color: var(--primary-color, #2563eb);
  color: var(--primary-color, #2563eb);
}
.clar-candidate:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.clar-symbol {
  color: var(--text-secondary, #888);
  font-size: 12px;
}
.clar-market {
  color: var(--text-secondary, #aaa);
  font-size: 11px;
}
</style>
