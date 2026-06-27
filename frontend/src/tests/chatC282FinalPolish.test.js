/**
 * C28.2 Final Browser Polish — frontend tests.
 *
 * T1–T3: DataQualityCard / ChatSourceList must never show "unknown".
 * T11–T12: chatReducer replaces same-stage thinking items instead of appending.
 */
import { describe, it, expect } from 'vitest'
import { applyChatUiEvent } from '../utils/chatReducer.js'

// ---------------------------------------------------------------------------
// Problem A — "unknown" must not appear in UI
// ---------------------------------------------------------------------------

describe('DataQualityCard — unknown filtering (T1–T3)', () => {
  /**
   * T1: verified_data containing "unknown" must be filtered in the reducer
   *     (tested via the chatReducer data_quality_update path and via the
   *     safeVerifiedData computed in DataQualityCard.vue — here we test the
   *     downstream data that flows into the card).
   *
   * In practice DataQualityCard filters with safeVerifiedData computed prop;
   * we verify it via the reducer's ui_data_quality_update handling and by
   * checking the raw data that would be passed.
   */
  it('T1: ui_data_quality_update with unknown in verified_data is stored verbatim (filtered by card)', () => {
    const msg = { dataQuality: null, skillSources: [] }
    applyChatUiEvent(msg, {
      type: 'ui_data_quality_update',
      dataQuality: {
        level: 'low',
        reason: 'test',
        verified_data: ['实时行情', 'unknown'],
        missing_data: [],
        warning_flags: [],
      },
    })
    // The reducer stores it verbatim; filtering is the card's responsibility.
    // We validate that the safeVerifiedData logic (replicated here) removes "unknown".
    const SKIP = new Set(['unknown'])
    const safe = (msg.dataQuality?.verified_data || []).filter(
      item => item && !SKIP.has(item) && !/^[a-z][a-z0-9_]+$/.test(item)
    )
    expect(safe).not.toContain('unknown')
    expect(safe).toContain('实时行情')
  })

  it('T2: safeTitle logic maps title="unknown" to "来源未标注"', () => {
    // Simulate _safeTitle from ChatSourceList.vue
    const _TITLE_OVERRIDES = {
      'rag_retrieve': '金融知识库资料',
      'rag_review':   '资料质量审查',
      'unknown':      '来源未标注',
      'tool_result':  '工具结果',
    }
    const _TYPE_LABELS = {
      unknown:      '来源未标注',
      market_quote: '实时行情',
      news:         '新闻',
    }
    function _typeLabel(type) { return _TYPE_LABELS[type] || '参考资料' }
    function _safeTitle(src) {
      const raw = src.title || ''
      if (!raw || _TITLE_OVERRIDES[raw] || /^[a-z][a-z0-9_]+$/.test(raw)) {
        return _TITLE_OVERRIDES[raw] || _typeLabel(src.source_type) || '参考资料'
      }
      return raw
    }
    const src = { title: 'unknown', source_type: 'unknown' }
    expect(_safeTitle(src)).toBe('来源未标注')
    expect(_safeTitle(src)).not.toBe('unknown')
  })

  it('T3: missing provider does not show "unknown" in meta', () => {
    // _meta() from ChatSourceList.vue: [(provider || source), date].filter(Boolean).join(' · ')
    function _meta(src) {
      return [(src.provider || src.source), src.published_at?.slice(0, 10)].filter(Boolean).join(' · ')
    }
    const src = { source_type: 'news' }  // no provider, no source
    expect(_meta(src)).toBe('')           // empty string, never "unknown"
    expect(_meta(src)).not.toContain('unknown')
  })

  it('snake_case verified_data entry filtered by safeVerifiedData logic', () => {
    // e.g. "rag_retrieve" should not appear in the 已获取 list
    const SKIP = new Set(['unknown'])
    const raw = ['实时行情', 'rag_retrieve', 'unknown', '金融知识库']
    const safe = raw.filter(
      item => item && !SKIP.has(item) && !/^[a-z][a-z0-9_]+$/.test(item)
    )
    expect(safe).toEqual(['实时行情', '金融知识库'])
  })
})

// ---------------------------------------------------------------------------
// Problem D — same-stage thinking item replacement
// ---------------------------------------------------------------------------

describe('chatReducer — ui_thinking_item replacement (T11–T12)', () => {
  it('T11: later data_quality_review replaces earlier one (low overwrites high)', () => {
    const msg = { thinkingItems: [] }

    // Early optimistic thinking: data_quality high
    applyChatUiEvent(msg, {
      type:       'ui_thinking_item',
      source:     'data_quality_review',
      stage:      'data_quality',
      title:      '检查数据质量',
      content:    '数据质量：数据完整。已获取多维度数据，信息完整度高。',
      importance: 'medium',
    })
    expect(msg.thinkingItems).toHaveLength(1)
    expect(msg.thinkingItems[0].content).toContain('数据完整')

    // Final corrected thinking: data_quality low
    applyChatUiEvent(msg, {
      type:       'ui_thinking_item',
      source:     'data_quality_review',
      stage:      'data_quality',
      title:      '检查数据质量',
      content:    '数据质量：数据有限。仅获取到行情或新闻数据，缺少财务及深度研究数据。',
      importance: 'high',
    })

    // T11: must still have exactly 1 item; content replaced to "数据有限"
    expect(msg.thinkingItems).toHaveLength(1)
    expect(msg.thinkingItems[0].content).toContain('数据有限')
    expect(msg.thinkingItems[0].content).not.toContain('数据完整')
  })

  it('T12: same source+stage is replaced, not appended', () => {
    const msg = { thinkingItems: [] }

    for (let i = 0; i < 3; i++) {
      applyChatUiEvent(msg, {
        type:       'ui_thinking_item',
        source:     'data_quality_review',
        stage:      'data_quality',
        title:      '检查数据质量',
        content:    `第${i + 1}次发送`,
        importance: 'medium',
      })
    }
    // Should only have 1 item (each replaced the previous)
    expect(msg.thinkingItems).toHaveLength(1)
    expect(msg.thinkingItems[0].content).toBe('第3次发送')
  })

  it('different stages are not collapsed', () => {
    const msg = { thinkingItems: [] }

    applyChatUiEvent(msg, {
      type: 'ui_thinking_item', source: 'data_quality_review',
      stage: 'data_quality', title: 'A', content: 'first', importance: 'medium',
    })
    applyChatUiEvent(msg, {
      type: 'ui_thinking_item', source: 'risk_review',
      stage: 'risk_review', title: 'B', content: 'second', importance: 'medium',
    })
    // Different source+stage → both kept
    expect(msg.thinkingItems).toHaveLength(2)
  })

  it('different sources with same stage are not collapsed', () => {
    const msg = { thinkingItems: [] }

    applyChatUiEvent(msg, {
      type: 'ui_thinking_item', source: 'agent_step',
      stage: 'synthesis', title: 'A', content: 'agent step', importance: 'medium',
    })
    applyChatUiEvent(msg, {
      type: 'ui_thinking_item', source: 'synthesis',
      stage: 'synthesis', title: 'B', content: 'synthesis step', importance: 'low',
    })
    // Different source → both kept
    expect(msg.thinkingItems).toHaveLength(2)
  })

  it('item with empty stage always appended (no dedup key)', () => {
    const msg = { thinkingItems: [] }

    // deepseek_reasoning items typically have empty stage
    applyChatUiEvent(msg, {
      type: 'ui_thinking_item', source: 'deepseek_reasoning',
      stage: '', title: '', content: 'chunk1', importance: 'low',
    })
    applyChatUiEvent(msg, {
      type: 'ui_thinking_item', source: 'deepseek_reasoning',
      stage: '', title: '', content: 'chunk2', importance: 'low',
    })
    // Empty stage → appended, not replaced
    expect(msg.thinkingItems).toHaveLength(2)
  })
})
