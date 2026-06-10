/**
 * theme.js — 主题切换工具
 *
 * 三套主题：
 *   light-holo   流光幻岛（浅色默认）
 *   dark-dive    极夜深潜（暗色专业）
 *   paper-lilac  晨暮丁香（护眼阅读）
 *
 * 用法：
 *   applyTheme('light-holo')  — 写入 html[data-theme] 并立即生效
 *   getStoredTheme()          — 从 settings localStorage 读取已保存主题
 */

const SETTINGS_KEY = 'tradingagents:settings:v1'

export const THEMES = [
  { value: 'light-holo',  label: '流光幻岛' },
  { value: 'dark-dive',   label: '极夜深潜' },
  { value: 'paper-lilac', label: '晨暮丁香' },
]

/**
 * Apply a theme by setting html[data-theme].
 * Falls back to 'light-holo' if the value is unknown.
 * @param {string} theme
 */
export function applyTheme(theme = 'light-holo') {
  const valid = THEMES.some(t => t.value === theme)
  document.documentElement.dataset.theme = valid ? theme : 'light-holo'
}

/**
 * Read the stored theme from settings localStorage without importing settings.js
 * (avoids circular dependency when called from main.js before app mounts).
 * @returns {string}
 */
export function getStoredTheme() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    const stored = raw ? JSON.parse(raw) : {}
    const t = stored.theme
    return THEMES.some(x => x.value === t) ? t : 'light-holo'
  } catch {
    return 'light-holo'
  }
}
