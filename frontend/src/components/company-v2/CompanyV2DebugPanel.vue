<template>
  <aside class="cv2-debug">
    <div class="cv2-debug-head">
      <div>
        <strong>Debug Envelope</strong>
        <span>{{ requestId }}</span>
      </div>
      <button @click="$emit('refresh')">刷新</button>
    </div>
    <div class="cv2-debug-grid">
      <span>providers_success {{ summary.providers_success ?? 0 }}</span>
      <span>providers_timeout {{ summary.providers_timeout ?? 0 }}</span>
      <span>modules_renderable {{ summary.modules_renderable ?? okCount }}</span>
      <span>modules_unavailable {{ summary.modules_unavailable ?? unavailableCount }}</span>
      <span>baostock_aggregate_calls {{ summary.baostock_aggregate_calls ?? providerCalls.baostock_aggregate ?? '—' }}</span>
      <span>providers_data_success {{ summary.providers_data_success ?? '—' }}</span>
      <span>overall_coverage {{ agentSummary.overall_coverage_pct ?? '—' }}%</span>
    </div>
    <section v-if="validationSummary.checks_total !== undefined" class="cv2-data-quality">
      <div class="cv2-data-quality-head">
        <strong>Data Quality</strong>
        <span :class="['cv2-validation-status', validationStatusClass]">
          {{ validationSummary.status }} · {{ validationSummary.data_quality_score }}
        </span>
      </div>
      <p>数据质量校验，仅用于字段一致性和口径提示，不构成投资建议。</p>
      <p v-if="hasSemanticWarnings" class="cv2-semantic-warning">
        该指标存在口径差异，可能来自报告期间、累计/单季或供应商定义差异，不代表数据一定错误。
      </p>
      <div class="cv2-debug-grid">
        <span>checks_total {{ validationSummary.checks_total ?? 0 }}</span>
        <span>warnings {{ validationSummary.checks_warning ?? 0 }}</span>
        <span>failed {{ validationSummary.checks_failed ?? 0 }}</span>
        <span>critical {{ validationSummary.critical_failures ?? 0 }}</span>
      </div>
      <details class="cv2-validation-checks">
        <summary>validation_checks {{ validationChecks.length }}</summary>
        <pre>{{ JSON.stringify(topValidationChecks, null, 2) }}</pre>
      </details>
    </section>
    <section class="cv2-production-health">
      <div class="cv2-data-quality-head">
        <strong>Production Health Summary</strong>
        <span :class="['cv2-validation-status', productionHealthClass]">{{ productionHealthLabel }}</span>
      </div>
      <div class="cv2-debug-grid">
        <span>Company Tab Version {{ companyTabVersion }}</span>
        <span>Rollback company_v2=0</span>
        <span>Schema Version {{ schemaVersion }}</span>
        <span>providers_data_success {{ summary.providers_data_success ?? '—' }}</span>
        <span>modules_renderable {{ summary.modules_renderable ?? okCount }}</span>
        <span>coverage_avg {{ agentSummary.overall_coverage_pct ?? '—' }}</span>
        <span>validation_status {{ validationSummary.status ?? '—' }}</span>
        <span>data_quality_score {{ validationSummary.data_quality_score ?? '—' }}</span>
        <span>strong_failed_count {{ validationSummary.strong_failed_count ?? 0 }}</span>
        <span>semantic_warning_count {{ validationSummary.semantic_warning_count ?? 0 }}</span>
        <span>cache_hit_count {{ summary.cache_hit_count ?? 0 }}</span>
        <span>fallback_to_legacy_count {{ summary.fallback_to_legacy_count ?? 0 }}</span>
      </div>
      <p v-if="(validationSummary.semantic_warning_count ?? 0) > 0" class="cv2-semantic-warning">
        口径提示：semantic warnings 用于观察供应商定义、报告期间或公式上下文差异，不等同于数据错误。
      </p>
      <p v-if="(validationSummary.strong_failed_count ?? 0) > 0" class="cv2-strong-failure">
        数据强校验失败：请检查字段映射、期间和计算来源。
      </p>
      <p v-if="(validationSummary.critical_failures ?? 0) > 0" class="cv2-critical-failure">
        Critical validation failure: stop cutover and rollback to legacy.
      </p>
    </section>
    <details class="cv2-provider-summary">
      <summary>provider_summary</summary>
      <pre>{{ JSON.stringify(providerSummary, null, 2) }}</pre>
    </details>
    <p class="cv2-debug-message">{{ dataStatusMessage }}</p>
    <CompanyV2RawJsonDrawer :data="data" />
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import CompanyV2RawJsonDrawer from './CompanyV2RawJsonDrawer.vue'

defineEmits(['refresh'])
const props = defineProps({
  data: { type: Object, default: () => ({}) },
})

const route = useRoute()
const modules = computed(() => Object.values(props.data.modules || {}))
const summary = computed(() => props.data.summary || {})
const providerCalls = computed(() => summary.value.provider_calls_count || {})
const agentSummary = computed(() => props.data.agent_summary || {})
const validationSummary = computed(() => props.data.validation_summary || {})
const validationChecks = computed(() => props.data.validation_checks || [])
const schemaVersion = computed(() => props.data.schema_version || '1.x')
const companyTabVersion = computed(() => {
  if (route.query.company_v2 === '0') return 'legacy-forced'
  if (route.query.company_v2 === '1') return 'v2-forced'
  return import.meta.env.VITE_COMPANY_TAB_VERSION || (import.meta.env.PROD ? 'legacy' : 'v2')
})
const topValidationChecks = computed(() => validationChecks.value.filter(check => ['warning', 'fail'].includes(check.status)).slice(0, 10))
const hasSemanticWarnings = computed(() => validationChecks.value.some(check => (
  check.check_strength === 'weak' || (check.tags || []).some(tag => [
    'DUPONT_PROVIDER_DEFINED',
    'ACCOUNTING_DEFINITION_DIFFERENCE',
    'FORMULA_CONTEXT_MISSING',
  ].includes(tag))
)))
const validationStatusClass = computed(() => {
  if (validationSummary.value.status === 'pass') return 'pass'
  if (validationSummary.value.status === 'fail') return 'fail'
  return 'warning'
})
const productionHealthClass = computed(() => {
  if ((validationSummary.value.critical_failures ?? 0) > 0) return 'fail'
  if ((validationSummary.value.strong_failed_count ?? 0) > 0) return 'fail'
  if ((validationSummary.value.semantic_warning_count ?? 0) > 0) return 'warning'
  if (validationSummary.value.status === 'pass') return 'pass'
  return 'warning'
})
const productionHealthLabel = computed(() => {
  if ((validationSummary.value.critical_failures ?? 0) > 0) return 'critical'
  if ((validationSummary.value.strong_failed_count ?? 0) > 0) return 'strong failure'
  if ((validationSummary.value.semantic_warning_count ?? 0) > 0) return '口径提示'
  return validationSummary.value.status || 'unknown'
})
const requestId = computed(() => props.data.request_id || '—')
const moduleCount = computed(() => modules.value.length)
const okCount = computed(() => modules.value.filter(m => m.ok).length)
const partialCount = computed(() => modules.value.filter(m => m.partial).length)
const unavailableCount = computed(() => moduleCount.value - okCount.value)
const primaryIssues = computed(() => modules.value.map(m => m.diagnosis?.primary_issue).filter(Boolean))
const providerSummary = computed(() => Object.fromEntries(
  Object.entries(props.data.modules || {}).map(([key, module]) => [key, module.provider_summary || {}]),
))
const dataStatusMessage = computed(() => {
  if (primaryIssues.value.includes('CACHE_UNAVAILABLE')) return '缓存服务暂不可用，已直接读取数据源。'
  if (primaryIssues.value.includes('PROVIDER_TIMEOUT') || primaryIssues.value.includes('PROVIDER_TIMEOUT_WITH_STALE_CACHE')) return '部分公开数据源超时，已展示可用数据或缓存快照。'
  if (primaryIssues.value.includes('MAPPING_ERROR')) return '原始数据已返回，但字段映射为空，请检查 normalizer。'
  if (primaryIssues.value.includes('ALL_NULL_ROWS')) return '该模块返回记录，但核心字段均为空，已隐藏。'
  if (primaryIssues.value.includes('PROVIDER_EMPTY')) return '部分字段当前公开数据源未返回，已展示可用字段。'
  return '已展示当前可用的公开数据。'
})
</script>

<style scoped>
.cv2-provider-summary {
  margin-top: 10px;
  color: #4b5563;
  font-size: 12px;
}
.cv2-provider-summary pre,
.cv2-validation-checks pre {
  max-width: 100%;
  overflow-x: auto;
  padding: 10px;
  border-radius: 8px;
  background: #f9fafb;
}
.cv2-data-quality {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
}
.cv2-production-health {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #f8fafc;
}
.cv2-data-quality-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.cv2-data-quality p {
  margin: 8px 0;
  color: #6b7280;
  font-size: 12px;
}
.cv2-semantic-warning {
  color: #92400e;
}
.cv2-strong-failure,
.cv2-critical-failure {
  color: #991b1b;
}
.cv2-validation-status {
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 12px;
}
.cv2-validation-status.pass {
  background: #dcfce7;
  color: #166534;
}
.cv2-validation-status.warning {
  background: #fef3c7;
  color: #92400e;
}
.cv2-validation-status.fail {
  background: #fee2e2;
  color: #991b1b;
}
.cv2-validation-checks {
  margin-top: 8px;
}
</style>
