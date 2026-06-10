/**
 * userSettings.js — 用户偏好设置工具函数。
 *
 * Re-exports everything from settings.js for backwards compatibility,
 * and adds DEFAULT_SETTINGS alias, updateSettings, and syncDevMode helpers.
 *
 * Existing callers of settings.js are unaffected.
 */
export {
  getSettings,
  saveSettings,
  resetSettings,
  SETTINGS_DEFAULTS as DEFAULT_SETTINGS,
  SETTINGS_EVENT,
} from './settings.js'

import { getSettings, saveSettings } from './settings.js'

/**
 * Merge a partial patch into current settings and persist.
 * Alias for saveSettings — provided for API symmetry with the spec.
 * @param {Record<string, unknown>} patch
 * @returns {object} updated settings
 */
export function updateSettings(patch) {
  return saveSettings(patch)
}

/**
 * Synchronise the standalone tradingagents:dev_mode key
 * that ComprehensiveAnalysisView reads directly from localStorage.
 * Call this after any settings write that may include dev_mode.
 * (saveSettings already does this internally; this is exposed for
 *  external callers that only have the full settings object.)
 * @param {{ dev_mode?: boolean }} settings
 */
export function syncDevMode(settings) {
  if (settings.dev_mode) {
    localStorage.setItem('tradingagents:dev_mode', 'true')
  } else {
    localStorage.removeItem('tradingagents:dev_mode')
  }
}
