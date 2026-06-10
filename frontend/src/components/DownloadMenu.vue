<template>
  <!-- @click.stop prevents document click listener from immediately closing the menu -->
  <div class="dl-menu" @click.stop>
    <button
      class="btn btn-secondary btn-sm dl-toggle"
      @click="dlOpen = !dlOpen"
    >
      下载 <span class="dl-caret" :class="{ 'dl-caret--open': dlOpen }">▾</span>
    </button>

    <div v-show="dlOpen" class="dl-list">
      <!-- ── File actions ── -->
      <button class="dl-item" @click="onMd">
        Markdown (.md)
      </button>
      <button class="dl-item" @click="onPdf">
        打印 / 导出 PDF
      </button>

      <!-- ── Divider ── -->
      <div class="dl-separator"></div>

      <!-- ── Copy actions ── -->
      <button
        class="dl-item"
        :disabled="!hasReport"
        @click="onCopyFull"
      >
        <span class="dl-item-icon">{{ copyFullStatus === 'copied' ? '✓' : copyFullStatus === 'fail' ? '✗' : '📋' }}</span>
        {{ copyFullStatus === 'copied' ? '已复制' : copyFullStatus === 'fail' ? '复制失败' : '复制完整报告' }}
      </button>

      <button
        class="dl-item"
        :disabled="!hasReport"
        @click="onCopySummary"
      >
        <span class="dl-item-icon">{{ copySummaryStatus === 'copied' ? '✓' : copySummaryStatus === 'fail' ? '✗' : '📄' }}</span>
        {{ copySummaryStatus === 'copied' ? '已复制' : copySummaryStatus === 'fail' ? '复制失败' : '复制核心摘要' }}
      </button>

      <button
        class="dl-item"
        :disabled="!hasReport"
        @click="onCopyShare"
      >
        <span class="dl-item-icon">{{ copyShareStatus === 'copied' ? '✓' : copyShareStatus === 'fail' ? '✗' : '🔗' }}</span>
        {{ copyShareStatus === 'copied' ? '已复制' : copyShareStatus === 'fail' ? '复制失败' : '复制分享文本' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { usePrintStore }    from '../stores/print.js'
import { downloadMarkdown, buildReportMarkdown } from '../utils/exportMarkdown.js'
import { extractSummary, buildReportIdentity, buildShareText, copyText } from '../utils/reportText.js'

const props = defineProps({
  result: { type: Object, required: true },
})

const router     = useRouter()
const printStore = usePrintStore()
const dlOpen     = ref(false)

const hasReport = computed(() => !!(props.result?.report))

// ── Copy state (idle | copied | fail) ────────────────────────────────────────
const copyFullStatus    = ref('idle')
const copySummaryStatus = ref('idle')
const copyShareStatus   = ref('idle')

function resetAfter(stateRef) {
  setTimeout(() => { stateRef.value = 'idle' }, 2000)
}

// ── File actions ──────────────────────────────────────────────────────────────
function onMd() {
  downloadMarkdown(props.result)
  dlOpen.value = false
}

function onPdf() {
  printStore.setResult(props.result)
  router.push('/print/report')
}

// ── Copy actions ──────────────────────────────────────────────────────────────
async function onCopyFull() {
  const text = buildReportMarkdown(props.result)
  const ok   = await copyText(text)
  copyFullStatus.value = ok ? 'copied' : 'fail'
  resetAfter(copyFullStatus)
}

async function onCopySummary() {
  const identity = buildReportIdentity(props.result)
  const summary  = extractSummary(props.result?.report ?? '')
  const text     = `${identity} 核心摘要\n\n${summary}`
  const ok       = await copyText(text)
  copySummaryStatus.value = ok ? 'copied' : 'fail'
  resetAfter(copySummaryStatus)
}

async function onCopyShare() {
  const text = buildShareText(props.result)
  const ok   = await copyText(text)
  copyShareStatus.value = ok ? 'copied' : 'fail'
  resetAfter(copyShareStatus)
}

// Close menu on any outside click
function closeMenu() { dlOpen.value = false }
onMounted(()        => document.addEventListener('click', closeMenu))
onBeforeUnmount(()  => document.removeEventListener('click', closeMenu))
</script>

<style scoped>
.dl-menu {
  position: relative;
  display: inline-block;
}

.dl-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
}

.dl-caret {
  font-size: 10px;
  transition: transform 0.15s;
  display: inline-block;
}

.dl-caret--open {
  transform: rotate(180deg);
}

.dl-list {
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  min-width: 170px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
  z-index: 200;
  overflow: hidden;
}

.dl-separator {
  height: 1px;
  background: var(--border);
  margin: 2px 0;
}

.dl-item {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 9px 14px;
  text-align: left;
  font-size: 13px;
  color: var(--text);
  background: transparent;
  border: none;
  cursor: pointer;
  white-space: nowrap;
}

.dl-item:hover:not(:disabled) {
  background: var(--surface2);
}

.dl-item:disabled {
  opacity: 0.4;
  cursor: default;
}

.dl-item:not(:last-child):not(.dl-separator + .dl-item ~ .dl-item) {
  /* borders handled via separator div instead */
}

.dl-item-icon {
  font-size: 12px;
  width: 16px;
  text-align: center;
  flex-shrink: 0;
}

/* ── Mobile ── */
@media (max-width: 540px) {
  .dl-list {
    right: auto;
    left: 0;
  }
}
</style>
