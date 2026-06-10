<template>
  <div :class="['card', { 'input-panel--guided': showGuide }]" @focusin="onFocusIn">
    <div class="card-title">{{ t('input_title') }}</div>

    <div class="form-row">
      <div class="form-group">
        <label>{{ t('input_market_label') }}</label>
        <select v-model="form.market" :disabled="loading">
          <option value="CN">{{ t('input_market_cn') }}</option>
          <option value="HK">{{ t('input_market_hk') }}</option>
        </select>
      </div>

      <div class="form-group ssb-group">
        <label>{{ t('input_symbol_label') }}</label>
        <StockSearchBox
          v-model:symbol="form.symbol"
          :market="form.market"
          :disabled="loading"
          @select="onSearchSelect"
          @keydown.enter="submit"
        />
      </div>

      <div class="form-group submit-group">
        <button
          class="btn btn-primary"
          @click="submit"
          :disabled="loading || !form.symbol.trim()"
        >
          <span v-if="loading"><span class="spinner"></span>{{ t('input_submit_loading') }}</span>
          <span v-else>{{ t('input_submit_idle') }}</span>
        </button>
      </div>
    </div>

    <p class="news-hint">{{ t('input_news_hint') }}</p>

    <!-- First-time guide hint -->
    <p v-if="showGuide" class="guide-hint">
      {{ t('input_guide_hint') }}
    </p>

    <!-- Quick examples -->
    <div class="examples">
      <span class="examples-hint">{{ t('input_examples_hint') }}</span>
      <span
        v-for="ex in EXAMPLES"
        :key="ex.label"
        class="example-chip"
        @click="fillExample(ex)"
      >{{ ex.label }}</span>
    </div>
  </div>
</template>

<script setup>
import { reactive, watch } from 'vue'
import { EXAMPLES } from '../utils/warningMap.js'
import StockSearchBox from './StockSearchBox.vue'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  loading:       { type: Boolean, default: false },
  initialMarket: { type: String,  default: 'CN' },
  initialSymbol: { type: String,  default: '' },
  showGuide:     { type: Boolean, default: false },
})

const emit = defineEmits(['analyze', 'change', 'focus-input'])

const form = reactive({
  market: props.initialMarket,
  symbol: props.initialSymbol,
})

// Sync form when parent updates initial values (e.g. navigating from Watchlist)
watch(() => props.initialMarket, (v) => { form.market = v })
watch(() => props.initialSymbol, (v) => { form.symbol = v })

// Notify parent whenever market or symbol changes (for StockIdentityCard)
watch([() => form.market, () => form.symbol], ([market, symbol]) => {
  emit('change', { market, symbol })
})

function onSearchSelect(item) {
  form.symbol = item.symbol
  // market is controlled by the market <select> — do not override it here
}

function fillExample(ex) {
  form.market = ex.market
  form.symbol = ex.symbol
}

function submit() {
  const sym = form.symbol.trim()
  if (!sym || props.loading) return
  emit('analyze', { market: form.market, symbol: sym })
}

function onFocusIn() {
  if (props.showGuide) emit('focus-input')
}

// Exposed to parent via template ref: fill form without submitting
function fill(market, symbol) {
  form.market = market
  form.symbol = symbol
}

defineExpose({ fill })
</script>

<style scoped>
.ssb-group {
  min-width: 200px;
  flex: 1;
}

.submit-group {
  justify-content: flex-end;
}

/* ── First-time guide ── */
.input-panel--guided {
  box-shadow: 0 0 0 2px var(--border-glow), 0 0 18px var(--status-info-bg);
  border-color: var(--border-glow);
  transition: box-shadow 0.6s ease, border-color 0.4s ease;
}

.guide-hint {
  margin-top: 10px;
  margin-bottom: 0;
  font-size: 12px;
  color: var(--accent);
  opacity: 0.85;
}

.news-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--muted);
}

.examples {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
  align-items: center;
}

.examples-hint {
  font-size: 11px;
  color: var(--muted);
  opacity: 0.6;
  line-height: 26px;
}

.example-chip {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 3px 10px;
  font-size: 12px;
  color: var(--muted);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}

.example-chip:hover {
  border-color: var(--accent);
  color: var(--accent);
}

@media (max-width: 540px) {
  .ssb-group { width: 100%; }

  /* Button spans full width so it aligns with the inputs above it */
  .submit-group {
    justify-content: stretch;
  }

  .submit-group .btn {
    width: 100%;
  }
}
</style>
