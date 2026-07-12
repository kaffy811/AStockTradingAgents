<template>
  <div class="cv2-profile-card">
    <div class="cv2-profile-header">
      <div class="cv2-profile-name">
        <h2>{{ companyName || symbol }}</h2>
        <span class="cv2-profile-code">{{ symbol }}</span>
        <span class="cv2-profile-exchange">{{ exchange }}</span>
      </div>
      <div v-if="listDateStatus !== 'unknown'" class="cv2-profile-meta">
        <span class="cv2-profile-label">上市日期</span>
        <span :class="['cv2-profile-value', listDateStatus === 'seed' && 'cv2-seed']">
          {{ listDate || '—' }}
          <span v-if="listDateStatus === 'seed'" class="cv2-seed-badge">seed</span>
        </span>
      </div>
    </div>

    <div v-if="hasDetails" class="cv2-profile-body">
      <div v-if="industry" class="cv2-profile-item">
        <span class="cv2-profile-label">行业</span>
        <span class="cv2-profile-value">{{ industry }}</span>
      </div>
      <div v-if="area" class="cv2-profile-item">
        <span class="cv2-profile-label">地区</span>
        <span class="cv2-profile-value">{{ area }}</span>
      </div>
      <div v-if="mainBusiness" class="cv2-profile-item cv2-full-width">
        <span class="cv2-profile-label">主营业务</span>
        <span class="cv2-profile-value cv2-truncate">{{ mainBusiness }}</span>
      </div>
      <div v-if="website" class="cv2-profile-item">
        <span class="cv2-profile-label">官网</span>
        <a :href="website" target="_blank" rel="noopener noreferrer" class="cv2-profile-link">
          {{ websiteDisplay }}
        </a>
      </div>
      <div v-if="chairman" class="cv2-profile-item">
        <span class="cv2-profile-label">法人代表</span>
        <span class="cv2-profile-value">{{ chairman }}</span>
      </div>
    </div>

    <div class="cv2-profile-footer">
      <span class="cv2-source-badge">
        数据来源：{{ sourceLabel }}
      </span>
      <span v-if="updatedAt" class="cv2-update-time">{{ updatedAt }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  stockBasic: { type: Object, default: () => ({}) },
  symbol: { type: String, default: '' },
  market: { type: String, default: 'CN' },
})

const companyName = computed(() => props.stockBasic?.company_name || '')
const exchange = computed(() => props.stockBasic?.exchange || '')
const listDate = computed(() => props.stockBasic?.list_date || '')
const listDateStatus = computed(() => props.stockBasic?.list_date_status || 'unknown')
const industry = computed(() => props.stockBasic?.industry || '')
const area = computed(() => props.stockBasic?.area || '')
const mainBusiness = computed(() => props.stockBasic?.main_business || '')
const website = computed(() => props.stockBasic?.website || '')
const chairman = computed(() => props.stockBasic?.chairman || '')
const updatedAt = computed(() => props.stockBasic?.updated_at || '')

const hasDetails = computed(() => !!(industry.value || area.value || mainBusiness.value))

const websiteDisplay = computed(() => {
  try {
    const url = new URL(website.value)
    return url.hostname
  } catch {
    return website.value
  }
})

const sourceLabel = computed(() => {
  const s = props.stockBasic?.source || ''
  const map = { baostock: 'BaoStock', akshare_profile: 'AkShare', seed: '内置数据', default: '默认' }
  return map[s] || s || '公开数据源'
})
</script>

<style scoped>
.cv2-profile-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 16px;
}
.cv2-profile-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.cv2-profile-name {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}
.cv2-profile-name h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}
.cv2-profile-code {
  font-size: 13px;
  font-weight: 500;
  color: #4b5563;
  background: #f3f4f6;
  padding: 2px 8px;
  border-radius: 4px;
}
.cv2-profile-exchange {
  font-size: 12px;
  color: #6b7280;
  background: #f0fdf4;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid #d1fae5;
}
.cv2-profile-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}
.cv2-profile-body {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  margin-bottom: 12px;
}
.cv2-profile-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 140px;
}
.cv2-full-width { width: 100%; }
.cv2-profile-label {
  font-size: 11px;
  color: #9ca3af;
  white-space: nowrap;
}
.cv2-profile-value {
  font-size: 13px;
  color: #374151;
  font-weight: 500;
}
.cv2-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
}
.cv2-profile-link {
  font-size: 13px;
  color: #3b82f6;
  text-decoration: none;
}
.cv2-profile-link:hover { text-decoration: underline; }
.cv2-seed-badge {
  font-size: 10px;
  color: #f59e0b;
  background: #fef3c7;
  padding: 1px 4px;
  border-radius: 3px;
  margin-left: 4px;
}
.cv2-seed { opacity: 0.85; }
.cv2-profile-footer {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-top: 10px;
  border-top: 1px solid #f3f4f6;
}
.cv2-source-badge {
  font-size: 10px;
  color: #9ca3af;
}
.cv2-update-time {
  font-size: 10px;
  color: #d1d5db;
}
</style>
