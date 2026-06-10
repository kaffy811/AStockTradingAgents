/**
 * User settings — localStorage persistence utility.
 *
 * Key:    tradingagents:settings:v1
 * Format: {
 *   default_market:         "CN" | "HK",
 *   default_analysis_scope: string,
 *   auto_save_report:       boolean,
 *   default_news_hours:     number,
 *   show_risk_notice:       boolean,
 *   dev_mode:               boolean,
 * }
 *
 * Compatibility:
 *   - tradingagents:dev_mode           (M4-b.6) kept in sync on write
 *   - tradingagents:analysis_engine    (M4-b.6) not touched here
 *   - tradingagents:recent_searches:v1 (existing) not touched here
 */

const STORAGE_KEY = 'tradingagents:settings:v1'
const EVENT_NAME  = 'tradingagents-settings-updated'

const DEFAULTS = {
  default_market:         'CN',
  default_analysis_scope: 'comprehensive',
  auto_save_report:       true,
  default_news_hours:     72,
  show_risk_notice:       true,
  dev_mode:               false,
  theme:                  'light-holo',
  language:               'zh-CN',
  report_language:        'zh-CN',
}

/**
 * Read current settings, merged with defaults.
 * @returns {typeof DEFAULTS}
 */
export function getSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const stored = raw ? JSON.parse(raw) : {}
    return { ...DEFAULTS, ...stored }
  } catch {
    return { ...DEFAULTS }
  }
}

/**
 * Write a partial update to settings.
 * @param {Partial<typeof DEFAULTS>} patch
 */
export function saveSettings(patch) {
  const current = getSettings()
  const updated = { ...current, ...patch }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
    // Keep M4-b.6 dev_mode key in sync
    if ('dev_mode' in patch) {
      if (patch.dev_mode) {
        localStorage.setItem('tradingagents:dev_mode', 'true')
      } else {
        localStorage.removeItem('tradingagents:dev_mode')
      }
    }
    window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: updated }))
  } catch {
    // localStorage full or unavailable — silently skip
  }
  return updated
}

/**
 * Reset settings to defaults (does NOT clear dev_mode compat key — caller must handle).
 */
export function resetSettings() {
  try {
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem('tradingagents:dev_mode')
    window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: { ...DEFAULTS } }))
  } catch {
    // ignore
  }
}

export { DEFAULTS as SETTINGS_DEFAULTS, EVENT_NAME as SETTINGS_EVENT }
