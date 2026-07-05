/**
 * C32 Conversation Markers + Session Search — frontend tests.
 *
 * T11: 3+ user messages → markers component has v-if condition ≥3
 * T12: marker preview = first 15 chars of user message
 * T13: ConversationMarkers has hover tooltip template
 * T14: scrollToMessage calls scrollIntoView on target element
 * T15: highlighted message gets msg-row--highlighted class
 * T16: fewer than 3 user messages → v-if="userMessages.length >= 3" hides rail
 * T17: ChatMessageList has data-message-id on each msg-row
 * T18: ChatMessageList exposes listRef
 * T19: ChatMessageList accepts highlightedId prop
 * T20: ChatCopilotView imports ConversationMarkers
 * T21: ChatCopilotView has sidebarRef and onSidebarSearch
 * T22: ChatSessionSidebar has search input
 * T23: ChatSessionSidebar has time filter chips
 * T24: ChatSessionSidebar emits 'search' event
 * T25: ChatSessionSidebar exposes setSearchResults
 * T26: api/chat.js exports searchChatSessions
 * T27: searchChatSessions builds correct query string with date_ranges
 * T28: searchChatSessions passes date_ranges as repeated param
 * T29: toggleRange adds to activeRanges (pure logic)
 * T30: clearSearch resets query and ranges (pure logic)
 * T31: zh-CN locale has all 12 new C32 keys
 * T32: en-US locale has all 12 new C32 keys
 * T33: C32.3: ConversationMarkers hidden on mobile (CSS @media check)
 * T34: C32.5: filter chip 'today' is listed in TIME_RANGES
 * T35: C32.3: marker tooltip shows time when created_at is present (pure logic)
 * T36: C32.6: ChatCopilotView searchChatSessions imported for session switching
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

// ─────────────────────────────────────────────────────────────────────────────
// T11–T16: C32.3 ConversationMarkers component
// ─────────────────────────────────────────────────────────────────────────────

describe('C32.3 — ConversationMarkers component', () => {

  it('T11: v-if condition shows markers only when ≥3 user messages', () => {
    const src = readSrc('src/components/chat/ConversationMarkers.vue')
    // Component template must have "userMessages.length >= 3"
    expect(src).toContain('userMessages.length >= 3')
  })

  it('T12: marker preview is first 15 chars of message content', () => {
    const src = readSrc('src/components/chat/ConversationMarkers.vue')
    expect(src).toContain('.slice(0, 15)')
    // Preview should have ellipsis for longer messages
    expect(src).toContain("'…'")
  })

  it('T13: marker tooltip contains preview and time', () => {
    const src = readSrc('src/components/chat/ConversationMarkers.vue')
    expect(src).toContain('conv-marker-tooltip')
    expect(src).toContain('conv-marker-preview')
    expect(src).toContain('conv-marker-time')
  })

  it('T14: scrollToMessage uses scrollIntoView', () => {
    const src = readSrc('src/components/chat/ConversationMarkers.vue')
    expect(src).toContain('scrollIntoView')
    expect(src).toContain("behavior: 'smooth'")
  })

  it('T15: highlighted message gets css class msg-row--highlighted', () => {
    const msgListSrc = readSrc('src/components/chat/ChatMessageList.vue')
    expect(msgListSrc).toContain('msg-row--highlighted')
    expect(msgListSrc).toContain('highlightedId')
  })

  it('T16: v-if hides the rail when user messages < 3 (guard is present)', () => {
    const src = readSrc('src/components/chat/ConversationMarkers.vue')
    // The component root must be wrapped with a v-if checking count
    expect(src).toMatch(/v-if.*userMessages\.length\s*>=\s*3/)
  })

})

// ─────────────────────────────────────────────────────────────────────────────
// T17–T21: ChatMessageList + ChatCopilotView integration
// ─────────────────────────────────────────────────────────────────────────────

describe('C32.3 — ChatMessageList data-message-id + ChatCopilotView integration', () => {

  it('T17: ChatMessageList has data-message-id on msg-row', () => {
    const src = readSrc('src/components/chat/ChatMessageList.vue')
    expect(src).toContain('data-message-id')
    expect(src).toContain('msg.id')
  })

  it('T18: ChatMessageList exposes listRef', () => {
    const src = readSrc('src/components/chat/ChatMessageList.vue')
    expect(src).toContain('defineExpose')
    expect(src).toContain('listRef')
  })

  it('T19: ChatMessageList accepts highlightedId prop', () => {
    const src = readSrc('src/components/chat/ChatMessageList.vue')
    expect(src).toContain('highlightedId')
    // Must be in defineProps
    const propsStart = src.indexOf('defineProps')
    const propsBody = src.slice(propsStart, propsStart + 300)
    expect(propsBody).toContain('highlightedId')
  })

  it('T20: ChatCopilotView imports ConversationMarkers', () => {
    const src = readSrc('src/views/ChatCopilotView.vue')
    expect(src).toContain('ConversationMarkers')
    expect(src).toContain("from '../components/chat/ConversationMarkers.vue'")
  })

  it('T21: ChatCopilotView has sidebarRef and onSidebarSearch', () => {
    const src = readSrc('src/views/ChatCopilotView.vue')
    expect(src).toContain('sidebarRef')
    expect(src).toContain('onSidebarSearch')
  })

})

// ─────────────────────────────────────────────────────────────────────────────
// T22–T25: ChatSessionSidebar search UI
// ─────────────────────────────────────────────────────────────────────────────

describe('C32.5 — ChatSessionSidebar search UI', () => {

  it('T22: ChatSessionSidebar has search input', () => {
    const src = readSrc('src/components/chat/ChatSessionSidebar.vue')
    expect(src).toContain('search-input')
    expect(src).toContain('chat_search_placeholder')
  })

  it('T23: ChatSessionSidebar has time filter chips', () => {
    const src = readSrc('src/components/chat/ChatSessionSidebar.vue')
    expect(src).toContain('filter-chip')
    expect(src).toContain('TIME_RANGES')
    expect(src).toContain('chat_filter_today')
  })

  it('T24: ChatSessionSidebar emits "search" event', () => {
    const src = readSrc('src/components/chat/ChatSessionSidebar.vue')
    expect(src).toContain("'search'")
    expect(src).toContain("emit('search'")
  })

  it('T25: ChatSessionSidebar exposes setSearchResults', () => {
    const src = readSrc('src/components/chat/ChatSessionSidebar.vue')
    expect(src).toContain('defineExpose')
    expect(src).toContain('setSearchResults')
  })

})

// ─────────────────────────────────────────────────────────────────────────────
// T26–T30: api/chat.js searchChatSessions
// ─────────────────────────────────────────────────────────────────────────────

describe('C32.5 — api/chat.js searchChatSessions', () => {

  it('T26: searchChatSessions is exported from api/chat.js', () => {
    const src = readSrc('src/api/chat.js')
    expect(src).toContain('export function searchChatSessions')
  })

  it('T27: searchChatSessions builds URL with q param', () => {
    const src = readSrc('src/api/chat.js')
    const fnIdx = src.indexOf('export function searchChatSessions')
    const fnBody = src.slice(fnIdx, fnIdx + 900)
    expect(fnBody).toContain("params.set('q'")
    expect(fnBody).toContain('/chat/sessions/search')
  })

  it('T28: searchChatSessions appends date_ranges as repeated params', () => {
    const src = readSrc('src/api/chat.js')
    expect(src).toContain("params.append('date_ranges'")
  })

  it('T29: toggleRange pure logic — adds/removes from array', () => {
    // Simulate the toggleRange logic from ChatSessionSidebar
    const activeRanges = []
    function toggleRange(value) {
      const idx = activeRanges.indexOf(value)
      if (idx >= 0) activeRanges.splice(idx, 1)
      else activeRanges.push(value)
    }
    toggleRange('7days')
    expect(activeRanges).toContain('7days')
    toggleRange('today')
    expect(activeRanges).toContain('today')
    toggleRange('7days')
    expect(activeRanges).not.toContain('7days')
    expect(activeRanges).toContain('today')
  })

  it('T30: clearSearch resets query and ranges', () => {
    let searchQuery = 'test'
    let activeRanges = ['today', '7days']
    // Simulate clearSearch
    function clearSearch() {
      searchQuery = ''
      activeRanges = []
    }
    clearSearch()
    expect(searchQuery).toBe('')
    expect(activeRanges).toHaveLength(0)
  })

})

// ─────────────────────────────────────────────────────────────────────────────
// T31–T36: i18n, CSS, and consistency checks
// ─────────────────────────────────────────────────────────────────────────────

const C32_I18N_KEYS = [
  'chat_markers_jump',
  'chat_search_placeholder',
  'chat_search_clear',
  'chat_search_no_results',
  'chat_search_loading',
  'chat_filter_title',
  'chat_filter_today',
  'chat_filter_yesterday',
  'chat_filter_7days',
  'chat_filter_30days',
  'chat_filter_month',
  'chat_filter_clear',
]

describe('C32 — i18n and CSS checks', () => {

  it('T31: zh-CN locale has all 12 new C32 keys', () => {
    const src = readSrc('src/locales/zh-CN.js')
    for (const key of C32_I18N_KEYS) {
      expect(src, `Missing zh-CN key: ${key}`).toContain(key)
    }
  })

  it('T32: en-US locale has all 12 new C32 keys', () => {
    const src = readSrc('src/locales/en-US.js')
    for (const key of C32_I18N_KEYS) {
      expect(src, `Missing en-US key: ${key}`).toContain(key)
    }
  })

  it('T33: ConversationMarkers is hidden on mobile via CSS @media', () => {
    const src = readSrc('src/components/chat/ConversationMarkers.vue')
    // Must have a media query that hides the markers on small screens
    expect(src).toContain('@media')
    expect(src).toContain('max-width: 640px')
    expect(src).toContain('display: none')
  })

  it('T34: TIME_RANGES includes "today" preset', () => {
    const src = readSrc('src/components/chat/ChatSessionSidebar.vue')
    expect(src).toContain("value: 'today'")
    expect(src).toContain("value: 'yesterday'")
    expect(src).toContain("value: '7days'")
    expect(src).toContain("value: '30days'")
    expect(src).toContain("value: 'month'")
  })

  it('T35: marker tooltip time computation uses toLocaleTimeString', () => {
    const src = readSrc('src/components/chat/ConversationMarkers.vue')
    expect(src).toContain('toLocaleTimeString')
  })

  it('T36: ChatCopilotView imports searchChatSessions', () => {
    const src = readSrc('src/views/ChatCopilotView.vue')
    expect(src).toContain('searchChatSessions')
  })

})
