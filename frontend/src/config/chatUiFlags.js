/**
 * C29.1 — Chat UI display mode flags.
 *
 * CHAT_UI_DEBUG is true only in the Vite dev server AND when
 * localStorage.CHAT_UI_DEBUG is set to "1".
 *
 * Enable:  localStorage.setItem('CHAT_UI_DEBUG', '1'); location.reload()
 * Disable: localStorage.removeItem('CHAT_UI_DEBUG'); location.reload()
 *
 * In production builds, import.meta.env.DEV is false → all debug flags false.
 */
export const CHAT_UI_DEBUG =
  import.meta.env.DEV && localStorage.getItem('CHAT_UI_DEBUG') === '1'

/**
 * C29.1.1 — Minimal thinking panel (always visible).
 * Shows high-level progress like "正在检索数据 / 正在生成回答".
 * Hidden only when the full debug panel is active.
 */
export const SHOW_THINKING_MINI   = !CHAT_UI_DEBUG

/** Show DataQualityCard beneath AI messages — debug only */
export const SHOW_DATA_QUALITY    = CHAT_UI_DEBUG

/** Show ChatSourceList (资料来源) beneath AI messages — debug only */
export const SHOW_SOURCES         = CHAT_UI_DEBUG

/** Show full ChatReasoningPanel (thinking steps / tool trace) — debug only */
export const SHOW_REASONING_PANEL = CHAT_UI_DEBUG

/** Show stream-debug diagnostic panel (event counts, timing) — debug only */
export const SHOW_STREAM_DEBUG    = CHAT_UI_DEBUG
