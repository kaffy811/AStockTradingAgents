/**
 * Lightweight i18n — no external dependencies.
 *
 * Architecture:
 *   - `_locale` is a Vue `ref`, so any template that calls `t()` gains a
 *     reactive dependency on the current locale.  When `setLocale()` changes
 *     `_locale.value`, all components that called `t()` in their last render
 *     automatically re-render with the new locale.
 *
 * Supported locales: zh-CN · en-US · zh-TW · ja-JP · ko-KR · es-ES
 * Default: zh-CN
 *
 * Usage in a component:
 *   import { useI18n } from '../utils/i18n.js'
 *   const { t } = useI18n()
 *   // template: {{ t('nav_analysis') }}
 *
 * Param interpolation: t('recent_expand', { count: 12 })
 *   → "展开更多（共 12 条）"
 */

import { ref } from 'vue'
import zhCN from '../locales/zh-CN.js'
import enUS from '../locales/en-US.js'
import zhTW from '../locales/zh-TW.js'
import jaJP from '../locales/ja-JP.js'
import koKR from '../locales/ko-KR.js'
import esES from '../locales/es-ES.js'

const MESSAGES = {
  'zh-CN': zhCN,
  'en-US': enUS,
  'zh-TW': zhTW,
  'ja-JP': jaJP,
  'ko-KR': koKR,
  'es-ES': esES,
}

export const LOCALES = [
  { value: 'zh-CN', label: '中文简体' },
  { value: 'en-US', label: 'English (US)' },
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'ja-JP', label: '日本語' },
  { value: 'ko-KR', label: '한국어' },
  { value: 'es-ES', label: 'Español' },
]

// Singleton reactive locale ref — shared across all components.
const _locale = ref('zh-CN')

/**
 * Get the currently active locale value string.
 */
export function getLocale() {
  return _locale.value
}

/**
 * Set the active locale.  Components that call `t()` in their templates
 * will re-render automatically because `t()` reads `_locale.value`.
 */
export function setLocale(locale) {
  if (MESSAGES[locale]) {
    _locale.value = locale
  }
}

/**
 * Translate a key for the current locale.
 * Falls back to zh-CN, then the raw key if not found.
 *
 * @param {string} key
 * @param {Record<string,string|number>} params  e.g. { count: 5 }
 * @returns {string}
 */
export function t(key, params = {}) {
  // Access _locale.value so Vue tracks this as a reactive dependency.
  const msgs = MESSAGES[_locale.value] || MESSAGES['zh-CN']
  let str = msgs[key]
  if (str === undefined) {
    // Fallback: zh-CN
    str = MESSAGES['zh-CN'][key]
  }
  if (str === undefined) {
    // Last resort: return key itself
    return key
  }
  // Simple {param} interpolation
  return str.replace(/\{(\w+)\}/g, (_, k) =>
    params[k] !== undefined ? String(params[k]) : `{${k}}`
  )
}

/**
 * Read the stored locale from localStorage (same key as settings).
 * Called before Vue mounts to avoid FOUC-equivalent for language.
 */
const _SETTINGS_KEY = 'tradingagents:settings:v1'
export function getStoredLocale() {
  try {
    const raw = localStorage.getItem(_SETTINGS_KEY)
    const stored = raw ? JSON.parse(raw) : {}
    const lang = stored.language
    return LOCALES.some(l => l.value === lang) ? lang : 'zh-CN'
  } catch {
    return 'zh-CN'
  }
}

/**
 * Composition hook — returns the shared i18n API.
 * The returned `t` function is reactive in template context.
 */
export function useI18n() {
  return { t, getLocale, setLocale, LOCALES, locale: _locale }
}
