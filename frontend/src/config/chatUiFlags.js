/**
 * C29.1 — Chat UI display mode flags.
 *
 * CHAT_UI_DEBUG is true only in the Vite dev server AND when
 * localStorage.CHAT_UI_DEBUG is set to "1".
 *
 * Enable:  localStorage.setItem('CHAT_UI_DEBUG', '1'); location.reload()
 * Disable: localStorage.removeItem('CHAT_UI_DEBUG'); location.reload()
 *
 * All SHOW_* flags are derived from CHAT_UI_DEBUG.
 * In production builds, import.meta.env.DEV is false → all flags false.
 */
export const CHAT_UI_DEBUG =
  import.meta.env.DEV && localStorage.getItem('CHAT_UI_DEBUG') === '1'

/** Show the DataQualityCard beneath AI messages */
export const SHOW_DATA_QUALITY    = CHAT_UI_DEBUG

/** Show ChatSourceList (资料来源) beneath AI messages */
export const SHOW_SOURCES         = CHAT_UI_DEBUG

/** Show ChatReasoningPanel (thinking steps / tool trace) */
export const SHOW_REASONING_PANEL = CHAT_UI_DEBUG

/** Show stream-debug diagnostic panel (event counts, timing) */
export const SHOW_STREAM_DEBUG    = CHAT_UI_DEBUG
