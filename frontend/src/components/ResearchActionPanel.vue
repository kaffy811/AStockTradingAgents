<template>
  <div class="rap-wrap">
    <div class="rap-row">
      <!-- Save -->
      <button
        :class="['rap-btn', saved ? 'rap-btn--done' : '']"
        :disabled="saved || saving"
        @click="emit('save')"
      >
        <span v-if="saving" class="spinner rap-spinner"></span>
        <span class="rap-btn-icon">{{ saved ? '✓' : '💾' }}</span>
        <span class="rap-btn-label">{{ saving ? '保存中…' : saved ? '已保存' : '保存报告' }}</span>
      </button>

      <!-- Add to watchlist -->
      <button
        :class="['rap-btn', watchlistStatus === 'added' ? 'rap-btn--done' : watchlistStatus === 'exists' ? 'rap-btn--muted' : watchlistStatus === 'error' ? 'rap-btn--err' : '']"
        :disabled="addingWatchlist || watchlistStatus === 'added'"
        @click="handleAddWatchlist"
      >
        <span v-if="addingWatchlist" class="spinner rap-spinner"></span>
        <span class="rap-btn-icon">
          {{ watchlistStatus === 'added' ? '✓' : watchlistStatus === 'exists' ? '★' : '☆' }}
        </span>
        <span class="rap-btn-label">
          {{ watchlistStatus === 'added'  ? '已加入' :
             watchlistStatus === 'exists' ? '已在自选' :
             watchlistStatus === 'error'  ? '加入失败' :
             '加入自选' }}
        </span>
      </button>

      <!-- View history -->
      <button class="rap-btn" @click="goHistory">
        <span class="rap-btn-icon">📋</span>
        <span class="rap-btn-label">查看历史</span>
      </button>

      <!-- Copy summary -->
      <button
        :class="['rap-btn', copied ? 'rap-btn--done' : '']"
        @click="handleCopy"
      >
        <span class="rap-btn-icon">{{ copied ? '✓' : '📄' }}</span>
        <span class="rap-btn-label">{{ copied ? '已复制' : '复制摘要' }}</span>
      </button>

      <!-- Re-analyze -->
      <button class="rap-btn rap-btn--accent" @click="emit('reanalyze')">
        <span class="rap-btn-icon">🔄</span>
        <span class="rap-btn-label">重新分析</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { addWatchlist } from '../api/watchlist.js'
import { extractSummary, buildReportIdentity, copyText } from '../utils/reportText.js'

const props = defineProps({
  result: { type: Object, required: true },
  saved:  { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['save', 'reanalyze'])

const router = useRouter()

// ── Watchlist ─────────────────────────────────────────────────────────────────
const addingWatchlist = ref(false)
const watchlistStatus = ref('idle')   // idle | added | exists | error

async function handleAddWatchlist() {
  if (addingWatchlist.value || watchlistStatus.value === 'added') return
  addingWatchlist.value = true
  watchlistStatus.value = 'idle'
  try {
    await addWatchlist({
      market: props.result.market,
      symbol: props.result.symbol,
      name:   props.result.stock_name || '',
    })
    watchlistStatus.value = 'added'
  } catch (e) {
    if (e.status === 409) {
      watchlistStatus.value = 'exists'
    } else {
      watchlistStatus.value = 'error'
    }
  } finally {
    addingWatchlist.value = false
  }
}

// ── History navigation ────────────────────────────────────────────────────────
function goHistory() {
  router.push({
    path: '/history',
    query: { market: props.result.market, symbol: props.result.symbol },
  })
}

// ── Copy summary ──────────────────────────────────────────────────────────────
const copied = ref(false)
let copyTimer = null

async function handleCopy() {
  const identity = buildReportIdentity(props.result)
  const summary  = extractSummary(props.result?.report ?? '')
  const text     = `${identity} 核心摘要\n\n${summary}`

  const ok = await copyText(text)
  if (ok) {
    copied.value = true
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { copied.value = false }, 2500)
  }
}
</script>

<style scoped>
.rap-wrap {
  margin-bottom: 16px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 14px;
  background: var(--surface2);
}

.rap-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* ── Button base ── */
.rap-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 13px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: background 0.15s, border-color 0.15s, color 0.15s, opacity 0.15s;
}

.rap-btn:hover:not(:disabled) {
  background: var(--status-info-bg);
  border-color: var(--border-glow);
  color: var(--accent);
}

.rap-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

/* States */
.rap-btn--done {
  color: var(--success, #4caf50);
  border-color: var(--status-down-ring);
  background: var(--status-down-bg);
}

.rap-btn--muted {
  color: var(--muted);
}

.rap-btn--err {
  color: var(--danger, #f5554a);
  border-color: var(--status-up-ring);
}

.rap-btn--accent {
  color: var(--accent);
  border-color: var(--border-glow);
  background: var(--status-info-bg);
}

.rap-btn--accent:hover:not(:disabled) {
  background: var(--status-info-bg);
}

.rap-btn-icon {
  font-size: 13px;
  line-height: 1;
}

.rap-btn-label {
  line-height: 1;
}

.rap-spinner {
  width: 12px;
  height: 12px;
  border-width: 1.5px;
}

/* ── Mobile ── */
@media (max-width: 540px) {
  .rap-wrap {
    padding: 10px 12px;
  }

  .rap-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 7px;
  }

  .rap-btn {
    justify-content: center;
    width: 100%;
  }
}
</style>
