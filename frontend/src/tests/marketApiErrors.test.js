import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { readJsonResponse } from '../api/response.js'

const auth = vi.hoisted(() => ({ token: 'test', logout: vi.fn() }))
vi.mock('../stores/auth.js', () => ({ useAuthStore: () => auth }))
import { baseFetch } from '../api/http.js'
import { googleConfigApi, googleLoginApi } from '../api/auth.js'
import { getCompanyV2FullDebug } from '../api/companyV2.js'

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks() })

function response(status, body, type = 'text/plain') {
  return new Response(body, { status, headers: { 'Content-Type': type } })
}

for (const [name, call] of [
  ['stocks', () => baseFetch('/stocks/CN/600519/quote')],
  ['company v2', () => getCompanyV2FullDebug('CN', '600519')],
  ['Google config', () => googleConfigApi()],
  ['Google login', () => googleLoginApi('fake-credential')],
]) {
  describe(name, () => {
    it.each([500, 502, 503])('handles non-JSON HTTP %s without parsing errors or body disclosure', async (status) => {
      fetch.mockResolvedValue(response(status, 'Traceback secret password /private/server.py'))
      const error = await call().catch(e => e)
      expect(error).toBeInstanceOf(Error)
      expect(error).not.toBeInstanceOf(SyntaxError)
      expect(error.status).toBe(status)
      expect(error.message).toContain('服务暂时不可用')
      expect(error.message).not.toMatch(/Traceback|secret|password|server\.py|Unexpected token/)
    })
  })
}

it('handles malformed JSON despite a JSON header', async () => {
  await expect(readJsonResponse(response(500, 'Traceback secret', 'application/json')))
    .rejects.toMatchObject({ errorCode: 'INVALID_RESPONSE', status: 500 })
})
it('rejects non-JSON success response (proxy login page)', async () => {
  await expect(readJsonResponse(response(200, '<html>private</html>', 'text/html')))
    .rejects.toThrow('无法识别的数据')
})
it('keeps valid payload and unavailable reason', async () => {
  fetch.mockResolvedValue(response(503, JSON.stringify({ message: '行情源不可用', error_code: 'DATA_SOURCE_UNAVAILABLE' }), 'application/json'))
  await expect(baseFetch('/stocks/CN/600519/quote')).rejects.toMatchObject({ status: 503, message: '行情源不可用', errorCode: 'DATA_SOURCE_UNAVAILABLE' })
})
it('keeps 401 session handling and 204 contract', async () => {
  fetch.mockResolvedValueOnce(response(401, 'Traceback secret'))
  await expect(baseFetch('/watchlist')).rejects.toMatchObject({ status: 401, errorCode: 'AUTH_REQUIRED' })
  expect(auth.logout).toHaveBeenCalledWith({ expired: true })
  fetch.mockResolvedValueOnce(new Response(null, { status: 204 }))
  expect(await baseFetch('/watchlist', { method: 'DELETE' })).toBeNull()
})
it('returns valid JSON unmodified', async () => {
  const payload = { provider: 'sina', stale: true, data: { price: 10 } }
  fetch.mockResolvedValue(response(200, JSON.stringify(payload), 'application/json'))
  expect(await baseFetch('/stocks/CN/600519/quote')).toEqual(payload)
})
