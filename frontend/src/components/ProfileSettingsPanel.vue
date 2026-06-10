<template>
  <div class="psp-card card">
    <div class="psp-title-row">
      <span class="psp-title">{{ t('psp_title') }}</span>
      <button class="psp-reset-btn" @click="emit('reset')">{{ t('psp_reset') }}</button>
    </div>

    <div class="psp-list">

      <!-- 默认市场 -->
      <div class="psp-row">
        <div class="psp-label-col">
          <span class="psp-name">{{ t('psp_market_label') }}</span>
          <span class="psp-desc">{{ t('psp_market_desc') }}</span>
        </div>
        <select
          class="psp-select"
          :value="settings.default_market"
          @change="patch('default_market', $event.target.value)"
        >
          <option value="CN">{{ t('psp_market_cn') }}</option>
          <option value="HK">{{ t('psp_market_hk') }}</option>
        </select>
      </div>

      <!-- 默认分析范围 -->
      <div class="psp-row">
        <div class="psp-label-col">
          <span class="psp-name">{{ t('psp_scope_label') }}</span>
          <span class="psp-desc">{{ t('psp_scope_desc') }}</span>
        </div>
        <select
          class="psp-select"
          :value="settings.default_analysis_scope"
          @change="patch('default_analysis_scope', $event.target.value)"
        >
          <option value="comprehensive">{{ t('psp_scope_comprehensive') }}</option>
          <option value="technical_only">{{ t('psp_scope_technical') }}</option>
          <option value="fundamental_only">{{ t('psp_scope_fundamental') }}</option>
          <option value="peer_only">{{ t('psp_scope_peer') }}</option>
          <option value="news_only">{{ t('psp_scope_news') }}</option>
          <option value="technical_fundamental">{{ t('psp_scope_tech_fund') }}</option>
        </select>
      </div>

      <!-- 自动保存报告 -->
      <div class="psp-row">
        <div class="psp-label-col">
          <span class="psp-name">{{ t('psp_auto_save_label') }}</span>
          <span class="psp-desc">{{ t('psp_auto_save_desc') }}</span>
        </div>
        <label class="psp-toggle">
          <input
            type="checkbox"
            :checked="settings.auto_save_report"
            @change="patch('auto_save_report', $event.target.checked)"
          >
          <span class="psp-track"></span>
        </label>
      </div>

      <!-- 默认新闻窗口 -->
      <div class="psp-row">
        <div class="psp-label-col">
          <span class="psp-name">{{ t('psp_news_window_label') }}</span>
          <span class="psp-desc">{{ t('psp_news_window_desc') }}</span>
        </div>
        <select
          class="psp-select"
          :value="String(settings.default_news_hours)"
          @change="patch('default_news_hours', Number($event.target.value))"
        >
          <option value="24">{{ t('psp_news_24h') }}</option>
          <option value="72">{{ t('psp_news_72h') }}</option>
          <option value="168">{{ t('psp_news_7d') }}</option>
        </select>
      </div>

      <!-- 风险提示 -->
      <div class="psp-row">
        <div class="psp-label-col">
          <span class="psp-name">{{ t('psp_risk_notice_label') }}</span>
          <span class="psp-desc">{{ t('psp_risk_notice_desc') }}</span>
        </div>
        <label class="psp-toggle">
          <input
            type="checkbox"
            :checked="settings.show_risk_notice"
            @change="patch('show_risk_notice', $event.target.checked)"
          >
          <span class="psp-track"></span>
        </label>
      </div>

      <!-- 界面主题 -->
      <div class="psp-row psp-row--theme">
        <div class="psp-label-col">
          <span class="psp-name">{{ t('psp_theme_label') }}</span>
          <span class="psp-desc">{{ t('psp_theme_desc') }}</span>
        </div>
        <div class="psp-theme-seg">
          <button
            v-for="th in THEMES"
            :key="th.value"
            :class="['psp-theme-btn', settings.theme === th.value ? 'psp-theme-btn--active' : '']"
            @click="patch('theme', th.value)"
          >{{ th.label }}</button>
        </div>
      </div>

      <!-- 界面语言 -->
      <div class="psp-row">
        <div class="psp-label-col">
          <span class="psp-name">{{ t('psp_language_label') }}</span>
          <span class="psp-desc">{{ t('psp_language_desc') }}</span>
        </div>
        <select
          class="psp-select"
          :value="settings.language || 'zh-CN'"
          @change="patch('language', $event.target.value)"
        >
          <option v-for="loc in LOCALES" :key="loc.value" :value="loc.value">{{ loc.label }}</option>
        </select>
      </div>

      <!-- 报告输出语言 -->
      <div class="psp-row">
        <div class="psp-label-col">
          <span class="psp-name">{{ t('settings_rpt_lang') }}</span>
          <span class="psp-desc">{{ t('settings_rpt_lang_hint') }}</span>
        </div>
        <select
          class="psp-select"
          :value="settings.report_language || 'zh-CN'"
          @change="patch('report_language', $event.target.value)"
        >
          <option value="zh-CN">{{ t('lang_zh_cn') }}</option>
          <option value="en-US">{{ t('lang_en_us') }}</option>
          <option value="zh-TW">{{ t('lang_zh_tw') }}</option>
          <option value="ja-JP">{{ t('lang_ja_jp') }}</option>
          <option value="ko-KR">{{ t('lang_ko_kr') }}</option>
          <option value="es-ES">{{ t('lang_es_es') }}</option>
        </select>
      </div>

      <!-- 开发者模式 -->
      <div class="psp-row">
        <div class="psp-label-col">
          <span class="psp-name">{{ t('psp_dev_mode_label') }}</span>
          <span class="psp-desc">{{ t('psp_dev_mode_desc') }}</span>
        </div>
        <label class="psp-toggle">
          <input
            type="checkbox"
            :checked="settings.dev_mode"
            @change="patch('dev_mode', $event.target.checked)"
          >
          <span class="psp-track"></span>
        </label>
      </div>

    </div>
  </div>
</template>

<script setup>
import { THEMES } from '../utils/theme.js'
import { useI18n } from '../utils/i18n.js'

const { t, LOCALES } = useI18n()

const props = defineProps({
  settings: { type: Object, required: true },
})

const emit = defineEmits(['update:settings', 'reset'])

function patch(key, value) {
  emit('update:settings', { [key]: value })
}
</script>

<style scoped>
.psp-card {
  padding: 16px 20px;
}

.psp-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.psp-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}

.psp-reset-btn {
  font-size: 12px;
  color: var(--muted);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
}

.psp-reset-btn:hover { color: var(--accent); }

/* ── Settings list ── */
.psp-list {
  display: flex;
  flex-direction: column;
}

.psp-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border);
}

.psp-row:last-child { border-bottom: none; }

.psp-label-col {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.psp-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.psp-desc {
  font-size: 11px;
  color: var(--muted);
}

.psp-select {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 6px 10px;
  font-size: 12px;
  outline: none;
  min-width: 130px;
  flex-shrink: 0;
}

.psp-select:focus { border-color: var(--accent); }

/* ── Toggle ── */
.psp-toggle {
  position: relative;
  display: inline-flex;
  cursor: pointer;
  flex-shrink: 0;
}

.psp-toggle input {
  opacity: 0;
  width: 0;
  height: 0;
  position: absolute;
}

.psp-track {
  display: block;
  width: 40px;
  height: 22px;
  border-radius: 11px;
  background: var(--border);
  transition: background 0.2s;
  position: relative;
}

.psp-track::after {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  top: 3px;
  left: 3px;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.psp-toggle input:checked + .psp-track { background: var(--accent); }
.psp-toggle input:checked + .psp-track::after { transform: translateX(18px); }

/* ── Theme segmented control ── */
.psp-theme-seg {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.psp-theme-btn {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius-control, 6px);
  color: var(--muted);
  font-size: 12px;
  font-weight: 500;
  padding: 5px 10px;
  cursor: pointer;
  transition: background var(--motion-fast, 0.15s), color var(--motion-fast, 0.15s), border-color var(--motion-fast, 0.15s);
  white-space: nowrap;
}

.psp-theme-btn:hover {
  color: var(--text);
  border-color: var(--accent);
}

.psp-theme-btn--active {
  background: var(--accent-glow);
  border-color: var(--accent);
  color: var(--accent);
  font-weight: 600;
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .psp-card { padding: 14px 16px; }

  .psp-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .psp-row--theme .psp-theme-seg {
    width: 100%;
  }

  .psp-theme-btn {
    flex: 1;
    text-align: center;
  }

  .psp-select { width: 100%; min-width: unset; }
}
</style>
