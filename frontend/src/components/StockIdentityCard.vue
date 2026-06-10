<template>
  <div class="card sic-card">
    <!-- Loading skeleton -->
    <div v-if="loading" class="sic-loading">
      <span class="spinner"></span>
      <span class="sic-loading-text">{{ props.market }}/{{ props.symbol }}</span>
    </div>

    <!-- Loaded -->
    <div v-else class="sic-content">
      <div class="sic-top">
        <span class="sic-pre">即将分析</span>

        <div class="sic-title-area">
          <!-- Found in stock_master -->
          <template v-if="identity">
            <span class="sic-name">{{ identity.name }}</span>
            <span class="sic-ms">（{{ props.market }}/{{ identity.symbol || props.symbol }}）</span>
          </template>
          <!-- Fallback: not found -->
          <template v-else>
            <span class="sic-name sic-name--fallback">{{ props.market }}/{{ props.symbol }}</span>
          </template>
        </div>
      </div>

      <!-- Industry (CN only, null for HK is expected) -->
      <div v-if="identity?.industry_name" class="sic-industry">
        申万一级行业：<strong>{{ identity.industry_name }}</strong>
      </div>

      <!-- Not-found warning -->
      <div v-if="!identity" class="sic-warn">
        暂未匹配到股票名称，请确认代码是否正确
      </div>

      <!-- Data coverage -->
      <div class="sic-coverage">
        <span class="sic-cov-label">本次分析将综合使用：</span>
        <div class="sic-badges">
          <span class="sic-badge">技术图表</span>
          <span class="sic-badge">基本面</span>
          <span class="sic-badge">{{ props.market === 'HK' ? '港股同行对比' : '同行对比' }}</span>
          <span class="sic-badge">新闻信息</span>
        </div>
      </div>

      <!-- HK note -->
      <p v-if="props.market === 'HK'" class="sic-hk-note">
        港股行业分类暂不使用申万行业体系，部分行业热股信息可能不可用。
      </p>

      <p class="sic-hint">请确认股票无误后生成综合分析报告。</p>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue'
import { searchStocks } from '../api/stocks.js'

const props = defineProps({
  market: { type: String, required: true },
  symbol: { type: String, required: true },
})

const emit = defineEmits(['identity'])

const loading  = ref(false)
const identity = ref(null)   // { name, symbol, industry_name } | null

let debounceTimer = null
let fetchGen = 0   // incremented each fetch; stale responses are ignored

function scheduleIdentityFetch() {
  clearTimeout(debounceTimer)
  const sym = props.symbol.trim()
  if (!sym) {
    fetchGen++           // invalidate any in-flight fetch
    identity.value = null
    loading.value  = false
    emit('identity', '')
    return
  }
  loading.value = true
  debounceTimer = setTimeout(doFetch, 400)
}

async function doFetch() {
  const gen = ++fetchGen
  const sym = props.symbol.trim()
  const mkt = props.market
  if (!sym) { if (gen === fetchGen) loading.value = false; return }
  try {
    const data  = await searchStocks(mkt, sym, 3)
    if (gen !== fetchGen) return   // stale — a newer fetch is pending/done
    const items = data.items || []
    let match = null
    if (mkt === 'HK') {
      match = items.find(i => i.symbol.replace(/^0+/, '') === sym.replace(/^0+/, ''))
    } else {
      match = items.find(i => i.symbol === sym)
    }
    identity.value = match || null
    emit('identity', match?.name || '')
  } catch {
    if (gen !== fetchGen) return
    identity.value = null
    emit('identity', '')
  } finally {
    if (gen === fetchGen) loading.value = false
  }
}

watch(
  () => [props.market, props.symbol],
  scheduleIdentityFetch,
  { immediate: true },
)

onUnmounted(() => clearTimeout(debounceTimer))
</script>

<style scoped>
.sic-card {
  margin-bottom: 20px;
  border-left: 3px solid var(--accent);
  padding: 14px 16px;
}

/* ── Loading ── */
.sic-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--muted);
  min-height: 28px;
}

.sic-loading-text {
  font-family: monospace;
  color: var(--muted);
}

/* ── Content ── */
.sic-content { }

.sic-top {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 6px;
}

.sic-pre {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
  opacity: 0.8;
  white-space: nowrap;
  flex-shrink: 0;
}

.sic-title-area {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 2px;
}

.sic-name {
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.3;
}

.sic-name--fallback {
  font-family: monospace;
  font-size: 15px;
  font-weight: 700;
  color: var(--muted);
}

.sic-ms {
  font-size: 13px;
  font-weight: 500;
  color: var(--muted);
  font-family: monospace;
}

/* ── Industry ── */
.sic-industry {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 8px;
}

.sic-industry strong {
  color: var(--text);
  font-weight: 600;
}

/* ── Not-found warning ── */
.sic-warn {
  font-size: 12px;
  color: var(--warn, #f5a623);
  margin-bottom: 8px;
}

/* ── Data coverage ── */
.sic-coverage {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.sic-cov-label {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

.sic-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sic-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  background: var(--status-info-bg);
  border: 1px solid var(--status-info-ring);
  border-radius: 4px;
  color: var(--accent);
  white-space: nowrap;
}

/* ── HK note ── */
.sic-hk-note {
  font-size: 12px;
  color: var(--muted);
  margin: 0 0 6px;
  line-height: 1.5;
}

/* ── Hint ── */
.sic-hint {
  font-size: 12px;
  color: var(--muted);
  margin: 0;
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .sic-card { padding: 12px 14px; }

  .sic-top { gap: 6px; }

  .sic-name { font-size: 15px; }

  .sic-coverage {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .sic-cov-label { white-space: normal; }
}
</style>
