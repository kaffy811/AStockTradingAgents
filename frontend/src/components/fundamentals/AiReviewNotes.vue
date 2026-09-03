<template>
  <div v-if="notes && notes.length" class="arn-root">
    <details class="arn-details">
      <summary class="arn-summary">
        <span v-if="status === 'revised'">⚠️ 内容已通过合规审核并做安全改写</span>
        <span v-else-if="status === 'rejected'">🚫 AI 内容未通过合规审核</span>
        <span v-else>✅ 内容已通过合规审核</span>
      </summary>
      <ul class="arn-list">
        <li v-for="(note, i) in notes" :key="i" class="arn-item">
          <span class="arn-type">{{ note.type }}</span>
          <span class="arn-msg">{{ note.message }}</span>
        </li>
      </ul>
    </details>
  </div>
</template>

<script setup>
defineProps({
  status: { type: String, default: 'approved' },
  notes:  { type: Array,  default: () => [] },
})
</script>

<style scoped>
.arn-root { margin-top: 8px; }
.arn-details { font-size: 11px; }
.arn-summary {
  cursor: pointer; color: var(--muted); padding: 4px 0;
  list-style: none; display: flex; align-items: center; gap: 4px;
}
.arn-summary::-webkit-details-marker { display: none; }
.arn-list { margin: 6px 0 0 12px; padding: 0; list-style: disc; }
.arn-item { margin: 3px 0; display: flex; gap: 6px; }
.arn-type { font-weight: 600; color: #856404; flex-shrink: 0; }
.arn-msg { color: var(--muted); }
</style>
