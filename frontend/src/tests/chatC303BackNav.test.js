/**
 * C30.3.4 — Compare page back-to-chat navigation tests.
 *
 * T14: compare_link card in ChatResultCard appends ?from=chat to the path
 * T15: back button is rendered when route.query.from === 'chat'
 * T16: back button is NOT rendered when from query param is absent
 * T17: StockCompareView source contains cmp_back_to_chat i18n key
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '../../')

function readSrc(relPath) {
  return readFileSync(path.join(ROOT, relPath), 'utf-8')
}

describe('C30.3.4 — Compare back-to-chat navigation', () => {

  it('T14: ChatResultCard compare_link enriches path with from=chat', () => {
    const src = readSrc('src/components/chat/ChatResultCard.vue')
    // Template must include from=chat appended to compare link
    expect(src).toContain('from=chat')
    // Must be inside the compare_link template block
    const cmpBlock = src.slice(src.indexOf("card.type === 'compare_link'"))
    const endBlock = cmpBlock.indexOf('</template>')
    const cmpSection = cmpBlock.slice(0, endBlock)
    expect(cmpSection).toContain('from=chat')
  })

  it('T15: StockCompareView shows back button when fromChat is true', () => {
    const src = readSrc('src/views/StockCompareView.vue')
    // fromChat computed must be defined
    expect(src).toContain("route.query.from === 'chat'")
    // Back button must be conditionally rendered
    expect(src).toContain('v-if="fromChat"')
    expect(src).toContain('goBackToChat')
  })

  it('T16: StockCompareView back button uses cmp_back_to_chat i18n key', () => {
    const src = readSrc('src/views/StockCompareView.vue')
    expect(src).toContain("t('cmp_back_to_chat')")
  })

  it('T17: zh-CN locale has cmp_back_to_chat key', () => {
    const src = readSrc('src/locales/zh-CN.js')
    expect(src).toContain('cmp_back_to_chat')
  })

  it('T18: en-US locale has cmp_back_to_chat key', () => {
    const src = readSrc('src/locales/en-US.js')
    expect(src).toContain('cmp_back_to_chat')
  })

  it('T19: goBackToChat navigates to /chat', () => {
    const src = readSrc('src/views/StockCompareView.vue')
    // Navigation target must be /chat
    expect(src).toContain("router.push('/chat')")
  })
})
