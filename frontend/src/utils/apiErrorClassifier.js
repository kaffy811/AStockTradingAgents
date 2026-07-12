/**
 * src/utils/apiErrorClassifier.js — 统一 API 错误分类（Phase 6N-8A）
 *
 * 核心原则：HTTP 401/403 是认证问题，永远不能被归因为
 * "BaoStock/AkShare 数据源未返回数据"（provider 失败）。
 *
 * 分类：
 *   auth_required        — HTTP 401（或后端 error_code=AUTH_REQUIRED）
 *   forbidden            — HTTP 403
 *   rate_limited         — HTTP 429
 *   server_error         — HTTP 5xx
 *   provider_unavailable — provider 网络错误（error_code=DATA_SOURCE_UNAVAILABLE / fetch 网络失败）
 *   provider_empty       — provider 返回空（error_code=DATA_SOURCE_EMPTY / envelope 空原因）
 *   partial_data         — envelope partial=true / partial_errors 非空
 *   unknown_error        — 无法分类
 */

export const AUTH_REQUIRED_MESSAGE = '登录已过期，请重新登录后查看数据。'
export const AUTH_REQUIRED_PAGE_MESSAGE = '登录已过期，请重新登录后查看行情、新闻和财报数据。'
export const PROVIDER_EMPTY_MESSAGE = '免费数据源暂未返回该模块'
export const PARTIAL_DATA_MESSAGE = '部分模块数据不完整，请以已披露财报为准'

const CATEGORY_MESSAGES = {
  auth_required:        AUTH_REQUIRED_MESSAGE,
  forbidden:            '没有权限访问该数据。',
  rate_limited:         '请求过于频繁，请稍后再试。',
  server_error:         '服务暂时不可用，请稍后再试。',
  provider_unavailable: '数据源网络暂不可用，请稍后重试。',
  provider_empty:       PROVIDER_EMPTY_MESSAGE,
  partial_data:         PARTIAL_DATA_MESSAGE,
  unknown_error:        '加载失败，请稍后重试。',
}

/** 判断错误是否为认证类错误（401/AUTH_REQUIRED/normalize 后的 type=auth）。 */
export function isAuthError(err) {
  if (!err) return false
  const status = err.status ?? err.statusCode ?? null
  if (status === 401) return true
  if (err.errorCode === 'AUTH_REQUIRED' || err.error_code === 'AUTH_REQUIRED') return true
  if (err.type === 'auth') return true
  const msg = String(err.message || err.detail || '')
  return /登录已过期|请重新登录|AUTH_REQUIRED/.test(msg)
}

/**
 * 分类任意 API 错误 / 失败 envelope。
 * @param {unknown} err — baseFetch 抛出的 Error（带 status/errorCode）、
 *                        normalizeFundamentalError 的结果，或失败 DataEnvelope
 * @returns {{ category: string, message: string, status: number|null }}
 */
export function classifyApiError(err) {
  if (!err) return _result('unknown_error', null)

  const status = err.status ?? err.statusCode ?? null
  const code   = err.errorCode ?? err.error_code ?? null

  // ── 认证类优先：绝不落入 provider 分类 ──
  if (isAuthError(err))  return _result('auth_required', status ?? 401)
  if (status === 403)    return _result('forbidden', 403)
  if (status === 429)    return _result('rate_limited', 429)
  if (status >= 500)     return _result('server_error', status)

  // ── 后端稳定错误码 ──
  if (code === 'DATA_SOURCE_UNAVAILABLE') return _result('provider_unavailable', status)
  if (code === 'DATA_SOURCE_EMPTY' || code === 'FREE_SOURCE_LIMITED') {
    return _result('provider_empty', status)
  }

  // ── 失败 envelope（ok=false + reason）──
  if (err.ok === false || err.reason) {
    const reason = String(err.reason || '')
    if (/timeout|超时|network|网络|connection|proxy/i.test(reason)) {
      return _result('provider_unavailable', status)
    }
    return _result('provider_empty', status)
  }

  // ── partial data ──
  if (err.partial === true || (Array.isArray(err.partial_errors) && err.partial_errors.length)) {
    return _result('partial_data', status)
  }

  // ── fetch 完全失败（网络层）──
  if (err instanceof TypeError && /fetch/i.test(err.message || '')) {
    return _result('provider_unavailable', null)
  }
  if (err.type === 'network' || err.type === 'unavailable') {
    return _result('provider_unavailable', status)
  }

  return _result('unknown_error', status)
}

function _result(category, status) {
  return { category, message: CATEGORY_MESSAGES[category], status: status ?? null }
}
