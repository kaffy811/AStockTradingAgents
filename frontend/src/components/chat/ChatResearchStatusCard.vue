<template>
  <section class="research-status" :class="`research-status--${research.tone}`" aria-live="polite">
    <header class="research-status__header">
      <span class="research-status__mark" aria-hidden="true">{{ research.completed ? '✓' : statusMark }}</span>
      <div>
        <h3>{{ research.title }}</h3>
        <p>{{ research.description }}</p>
      </div>
    </header>

    <p v-if="research.reason" class="research-status__reason">{{ research.reason }}</p>

    <div v-if="research.sources.length" class="research-status__provenance">
      <div class="research-status__row">
        <dt>来源</dt>
        <dd>
          <template v-for="(source, index) in research.sources" :key="`${source.name}-${source.url}`">
            <span v-if="index"> · </span>
            <a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.name }}</a>
            <span v-else>{{ source.name }}</span>
          </template>
        </dd>
      </div>
      <div class="research-status__row"><dt>数据截至时间</dt><dd>{{ research.asOf || '未提供' }}</dd></div>
      <div class="research-status__row"><dt>数据覆盖范围</dt><dd>{{ research.coverage || '未提供' }}</dd></div>
      <div class="research-status__row">
        <dt>数据限制</dt>
        <dd>{{ research.limitations.length ? research.limitations.join('；') : '未发现已知限制' }}</dd>
      </div>
    </div>
    <p v-else class="research-status__empty-source">未获得可验证来源</p>

    <button v-if="research.retryable" class="research-status__retry" type="button" @click="$emit('retry')">重试研究</button>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  research: { type: Object, required: true },
})

defineEmits(['retry'])

const statusMark = computed(() => ({
  partial: '–',
  unavailable: '–',
  failed: '!',
}[props.research.status] ?? '–'))
</script>

<style scoped>
.research-status { margin-top: 14px; padding: 14px 16px; border: 1px solid var(--border-soft); border-radius: 12px; background: var(--surface2, #f7f7f8); color: var(--text-primary); }
.research-status__header { display: flex; gap: 10px; align-items: flex-start; }
.research-status__mark { display: grid; place-items: center; flex: 0 0 22px; height: 22px; border-radius: 50%; background: #e7e7e9; color: #595961; font-weight: 700; }
.research-status--success .research-status__mark { background: #e7f4eb; color: #267a43; }
.research-status--warning .research-status__mark { background: #f8efd9; color: #8a641b; }
.research-status--danger .research-status__mark { background: #f8e5e5; color: #a03c3c; }
h3 { margin: 1px 0 4px; font-size: 14px; line-height: 1.4; }
p { margin: 0; color: var(--text-secondary); font-size: 13px; line-height: 1.55; }
.research-status__reason, .research-status__empty-source { margin-top: 12px; }
.research-status__provenance { display: grid; gap: 8px; margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border-soft); }
.research-status__row { display: grid; grid-template-columns: 108px 1fr; gap: 10px; font-size: 12px; line-height: 1.55; }
dt { color: var(--text-tertiary, #777); }
dd { margin: 0; color: var(--text-secondary); overflow-wrap: anywhere; }
a { color: var(--accent, #3168c6); text-decoration: none; }
a:hover { text-decoration: underline; }
.research-status__retry { margin-top: 12px; border: 1px solid var(--border-soft); border-radius: 8px; padding: 6px 10px; background: var(--surface, #fff); color: var(--text-primary); cursor: pointer; }
@media (max-width: 520px) { .research-status__row { grid-template-columns: 1fr; gap: 2px; } }
</style>
