<template>
  <div v-if="citations.length" class="cv2-citations" data-testid="report-citations">
    <button
      v-for="citation in citations"
      :key="`${citation.chunk_id}-${citation.page}`"
      class="cv2-citation"
      type="button"
      @click="selected = selected === citation ? null : citation"
    >
      第 {{ citation.page }} 页
    </button>
    <div v-if="selected" class="cv2-citation-detail" data-testid="report-citation-detail">
      <div class="cv2-citation-page">第 {{ selected.page }} 页</div>
      <p>{{ selected.excerpt }}</p>
      <a v-if="selected.source_url" :href="selected.source_url" target="_blank" rel="noopener noreferrer">CNINFO PDF</a>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  citations: { type: Array, default: () => [] },
})

const selected = ref(null)
</script>

<style scoped>
.cv2-citations { display: flex; flex-wrap: wrap; gap: 6px; }
.cv2-citation {
  min-height: 26px;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
}
.cv2-citation-detail {
  flex-basis: 100%;
  border: 1px solid #e5e7eb;
  background: #fff;
  border-radius: 6px;
  padding: 10px;
  font-size: 12px;
  color: #374151;
}
.cv2-citation-detail p { margin: 4px 0 6px; line-height: 1.6; }
.cv2-citation-detail a { color: #2563eb; text-decoration: none; }
.cv2-citation-page { font-weight: 600; color: #111827; }
</style>
