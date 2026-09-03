import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import {
  normalizeResearchMetadata,
  researchFulfillmentView,
  researchReasonMessage,
} from '../utils/researchFulfillment.js'

describe('research fulfillment contract', () => {
  it.each([
    ['fulfilled', '已完成研究', true, false],
    ['partial', '部分完成', false, true],
    ['unavailable', '当前缺少所需数据', false, false],
    ['failed', '研究执行失败', false, true],
  ])('maps %s without a false completion state', (status, title, completed, retryable) => {
    expect(researchFulfillmentView(status)).toMatchObject({ title, completed, retryable })
  })

  it.each([
    'NO_APPROVED_NEWS_SOURCE',
    'NO_APPROVED_INDUSTRY_NEWS_SOURCE',
    'PROVIDER_NETWORK_TIMEOUT',
    'PROVIDER_PERMISSION_DENIED',
    'DATA_NOT_AVAILABLE',
  ])('provides readable copy for %s', (reason) => {
    expect(researchReasonMessage(reason)).toMatch(/[一-鿿]/)
    expect(researchReasonMessage(reason)).not.toContain(reason)
  })
})

describe('five acceptance response shapes', () => {
  it('renders a fulfilled CNINFO official-event response with public provenance', () => {
    const result = normalizeResearchMetadata({
      fulfillment: 'fulfilled',
      as_of: '2026-09-02T12:00:00Z',
      coverage: { kind: 'persisted_cninfo_events', event_count: 2 },
      events: [{
        source: 'CNINFO',
        source_url: 'https://www.cninfo.com.cn/new/disclosure/detail?stockCode=600519',
        raw_chunk_id: 'must-not-leak',
      }],
      internal_table: 'report_chunks',
    })
    expect(result).toMatchObject({ status: 'fulfilled', completed: true, retryable: false })
    expect(result.sources).toEqual([{
      name: '巨潮资讯（CNINFO）',
      url: 'https://www.cninfo.com.cn/new/disclosure/detail?stockCode=600519',
    }])
    expect(JSON.stringify(result)).not.toMatch(/must-not-leak|report_chunks|raw_chunk_id/)
  })

  it('renders authorized EOD research as partial without a completion check', () => {
    const result = normalizeResearchMetadata({
      fulfillment: 'partial',
      as_of: '2026-09-01',
      coverage: 'eod',
      sources: [{ source_name: 'Tushare EOD', source_url: 'https://example.test/eod' }],
    })
    expect(result).toMatchObject({ status: 'partial', completed: false, retryable: true })
    expect(result.sources[0].name).toBe('已授权行情数据')
    expect(result.limitations).toHaveLength(1)
  })

  it('fails closed for unavailable industry news without a retry or source', () => {
    const result = normalizeResearchMetadata({
      fulfillment: 'unavailable',
      reason_code: 'NO_APPROVED_INDUSTRY_NEWS_SOURCE',
      provider: 'eastmoney',
      stack_trace: 'must-not-leak',
    })
    expect(result).toMatchObject({ status: 'unavailable', completed: false, retryable: false })
    expect(result.sources).toEqual([])
    expect(result.reason).toContain('行业新闻来源')
    expect(JSON.stringify(result)).not.toMatch(/eastmoney|stack_trace|must-not-leak/i)
  })

  it('offers retry for an execution timeout but does not claim completion', () => {
    const result = normalizeResearchMetadata({
      fulfillment: 'failed',
      reason_code: 'PROVIDER_NETWORK_TIMEOUT',
    })
    expect(result).toMatchObject({ status: 'failed', completed: false, retryable: true })
    expect(result.sources).toEqual([])
  })

  it('renders an incomplete market overview as partial', () => {
    const result = normalizeResearchMetadata({
      fulfillment: 'partial',
      coverage: 'market_overview',
      limitations: ['成交额字段暂缺'],
      sources: [{ source_name: 'approved', source_url: 'https://example.test/market' }],
    })
    expect(result).toMatchObject({ status: 'partial', completed: false })
    expect(result.coverage).toBe('市场概览')
    expect(result.limitations).toEqual(['成交额字段暂缺'])
  })
})

describe('component wiring', () => {
  const read = (relative) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8')

  it('shows only the verified-source empty state when provenance is absent', () => {
    const source = read('../components/chat/ChatResearchStatusCard.vue')
    expect(source).toContain('v-if="research.sources.length"')
    expect(source).toContain('未获得可验证来源')
    expect(source).toContain("v-if=\"research.retryable\"")
  })

  it('passes fulfillment to the thinking panel and gates the legacy retry action', () => {
    const source = read('../components/chat/ChatMessageList.vue')
    expect(source).toContain(':fulfillment="msg.research?.status ?? \'\'"')
    expect(source).toContain('(!msg.research || msg.research.retryable)')
    expect(source).toContain('<ChatResearchStatusCard')
  })
})
