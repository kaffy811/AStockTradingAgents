<template>
  <span :class="['cv2-rag-status', tone]" data-testid="report-rag-status">
    {{ label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'pending' },
  chunkCount: { type: Number, default: 0 },
})

const label = computed(() => ({
  pending: '未索引',
  indexing: '索引中',
  indexed: `可提问${props.chunkCount ? ` · ${props.chunkCount}` : ''}`,
  partial: `部分可提问${props.chunkCount ? ` · ${props.chunkCount}` : ''}`,
  failed: '索引失败',
  stale: '索引已过期',
})[props.status] || props.status || '未索引')

const tone = computed(() => {
  if (props.status === 'indexed') return 'ok'
  if (props.status === 'partial' || props.status === 'stale') return 'warn'
  if (props.status === 'failed') return 'fail'
  return 'idle'
})
</script>

<style scoped>
.cv2-rag-status {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 16px;
  border: 1px solid #d1d5db;
  background: #fff;
  color: #4b5563;
}
.cv2-rag-status.ok { border-color: #86efac; background: #f0fdf4; color: #166534; }
.cv2-rag-status.warn { border-color: #fde68a; background: #fffbeb; color: #92400e; }
.cv2-rag-status.fail { border-color: #fecaca; background: #fef2f2; color: #b91c1c; }
.cv2-rag-status.idle { border-color: #e5e7eb; background: #f9fafb; color: #6b7280; }
</style>
