<template>
  <div class="iop-card card">

    <!-- Loading skeleton -->
    <div v-if="loading" class="iop-skeleton">
      <div class="iop-skel-title"></div>
      <div class="iop-skel-row"></div>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="iop-error">
      <span class="iop-error-icon">⚠</span>
      <span>{{ error }}</span>
    </div>

    <!-- Empty / no data yet -->
    <div v-else-if="!industryName" class="iop-empty">
      {{ t('ind_ov_select') }}
    </div>

    <!-- Content -->
    <div v-else class="iop-content">

      <div class="iop-identity">
        <div class="iop-name">{{ industryName }}</div>
        <div class="iop-meta-row">
          <span class="iop-badge iop-badge--market">{{ market }}</span>
          <span v-if="industryCode" class="iop-badge iop-badge--code">{{ industryCode }}</span>
          <span v-if="tradeDate" class="iop-meta-item">{{ t('ind_ov_trade_day') }}{{ tradeDate }}</span>
          <span v-if="scoreVersion" class="iop-meta-item">v{{ scoreVersion }}</span>
          <span v-if="itemCount != null" class="iop-meta-item">{{ itemCount }}{{ t('ind_heat_stocks') }}</span>
        </div>
        <div v-if="qualityMessage" class="iop-quality-warn">
          <span class="iop-warn-icon">⚠</span>
          {{ qualityMessage }}
        </div>
      </div>

      <div class="iop-notice">
        {{ t('ind_ov_notice') }}
      </div>

    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  industry:  { type: Object,  default: null },
  hotData:   { type: Object,  default: null },
  loading:   { type: Boolean, default: false },
  error:     { type: String,  default: '' },
  market:    { type: String,  default: 'CN' },
})

const industryName = computed(() =>
  props.hotData?.industry_name || props.industry?.industry_name || ''
)

const industryCode = computed(() =>
  props.industry?.industry_code || props.hotData?.industry_code || ''
)

const tradeDate = computed(() => props.hotData?.trade_date ?? '')

const scoreVersion = computed(() => props.hotData?.score_version ?? '')

const itemCount = computed(() => {
  const items = props.hotData?.items
  return Array.isArray(items) ? items.length : null
})

const qualityMessage = computed(() => props.hotData?.data_quality?.message ?? '')
</script>

<style scoped>
.iop-card {
  padding: 14px 20px;
}

/* ── Skeleton ── */
.iop-skeleton {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.iop-skel-title,
.iop-skel-row {
  border-radius: 6px;
  background: var(--surface2);
  animation: iop-pulse 1.2s ease-in-out infinite;
}

.iop-skel-title { height: 18px; width: 40%; }
.iop-skel-row   { height: 12px; width: 60%; }

@keyframes iop-pulse {
  0%, 100% { opacity: 0.5; }
  50%       { opacity: 1; }
}

/* ── Error ── */
.iop-error {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--warn);
}

.iop-error-icon { font-size: 14px; }

/* ── Empty ── */
.iop-empty {
  font-size: 13px;
  color: var(--muted);
}

/* ── Content ── */
.iop-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.iop-identity {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.iop-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
}

.iop-meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.iop-badge {
  font-size: 10px;
  font-weight: 700;
  border-radius: 4px;
  padding: 1px 6px;
}

.iop-badge--market {
  background: var(--status-info-bg);
  color: var(--accent);
}

.iop-badge--code {
  background: var(--surface2);
  color: var(--muted);
  border: 1px solid var(--border);
}

.iop-meta-item {
  font-size: 12px;
  color: var(--muted);
}

.iop-quality-warn {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--warn);
}

.iop-warn-icon { font-size: 12px; }

/* ── Notice ── */
.iop-notice {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.5;
  padding: 8px 10px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
}

/* ── Mobile ── */
@media (max-width: 375px) {
  .iop-card { padding: 12px 14px; }
  .iop-name { font-size: 14px; }
}
</style>
