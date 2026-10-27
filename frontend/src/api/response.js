/** Parse API JSON without exposing proxy HTML, plaintext errors, or tracebacks. */
export async function readJsonResponse(res) {
  try {
    return await res.json()
  } catch {
    const err = new Error(res.ok
      ? '服务返回了无法识别的数据，请稍后重试'
      : `服务暂时不可用（HTTP ${res.status}），请稍后重试`)
    err.status = res.status
    err.errorCode = 'INVALID_RESPONSE'
    throw err
  }
}
