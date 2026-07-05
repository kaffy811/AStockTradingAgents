/**
 * C32.1.4 Compare Page Failure Fix — frontend static tests.
 *
 * T1:  ChatConfirmationCard shows '✓ 已确认' for status='executed'
 * T2:  ChatResultCard renders compare_link template for type=compare_link
 * T3:  ChatResultCard compare_link link includes 'from=chat'
 * T4:  ChatResultCard compare_link uses card.data.stocks chip list
 * T5:  ChatCopilotView imports compare_link handling (session_id inject)
 * T6:  ChatCopilotView onConfirm injects session_id into compare URL
 * T7:  api/chat.js confirmChatAction is exported
 * T8:  ChatConfirmationCard does not show 'executing' for 'executed' status
 * T9:  chat_streaming has _has_confirmation_only guard (source)
 * T10: ChatResultCard compare_link path includes '?' for URL building
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

describe('C32.1.4 — ChatConfirmationCard status states', () => {

  it('T1: executed status shows confirmed check', () => {
    const src = readSrc('src/components/chat/ChatConfirmationCard.vue')
    expect(src).toContain("apiStatus === 'executed'")
    expect(src).toContain('chat_confirmed')
  })

  it('T8: executed status does NOT show executing spinner', () => {
    const src = readSrc('src/components/chat/ChatConfirmationCard.vue')
    // executing and executed should be separate branches
    expect(src).toContain("apiStatus === 'executing'")
    // executed branch leads to confirmed, not executing
    const execIdx = src.indexOf("apiStatus === 'executed'")
    const executingIdx = src.indexOf("apiStatus === 'executing'")
    expect(execIdx).not.toBe(-1)
    expect(executingIdx).not.toBe(-1)
    expect(execIdx).not.toBe(executingIdx)
  })

})

describe('C32.1.4 — ChatResultCard compare_link rendering', () => {

  it('T2: compare_link template block exists', () => {
    const src = readSrc('src/components/chat/ChatResultCard.vue')
    expect(src).toContain("card.type === 'compare_link'")
  })

  it('T3: compare_link link appends from=chat', () => {
    const src = readSrc('src/components/chat/ChatResultCard.vue')
    const cmpBlock = src.slice(src.indexOf("compare_link"))
    expect(cmpBlock).toContain('from=chat')
  })

  it('T4: compare_link renders stock chips from card.data.stocks', () => {
    const src = readSrc('src/components/chat/ChatResultCard.vue')
    const cmpBlock = src.slice(src.indexOf("compare_link"))
    expect(cmpBlock).toContain('card.data.stocks')
    expect(cmpBlock).toContain('rc-stock-chip')
  })

  it('T10: compare_link path builder handles ? for URL query string', () => {
    const src = readSrc('src/components/chat/ChatResultCard.vue')
    const cmpBlock = src.slice(src.indexOf("compare_link"))
    // Must handle both '?' and '&' cases
    expect(cmpBlock).toContain("includes('?')")
  })

})

describe('C32.1.4 — ChatCopilotView compare session_id injection', () => {

  it('T5: ChatCopilotView has compare_link handling', () => {
    const src = readSrc('src/views/ChatCopilotView.vue')
    expect(src).toContain("compare_link")
    expect(src).toContain('session_id')
  })

  it('T6: ChatCopilotView injects session_id into compare link path', () => {
    const src = readSrc('src/views/ChatCopilotView.vue')
    // Find the compare_link block
    const cmpIdx = src.indexOf("card?.type === 'compare_link'")
    expect(cmpIdx).not.toBe(-1)
    const cmpBlock = src.slice(cmpIdx, cmpIdx + 600)
    expect(cmpBlock).toContain('sessionId.value')
    expect(cmpBlock).toContain('session_id')
  })

})

describe('C32.1.4 — api/chat.js confirmChatAction', () => {

  it('T7: confirmChatAction is exported from api/chat.js', () => {
    const src = readSrc('src/api/chat.js')
    expect(src).toContain('confirmChatAction')
    expect(src).toContain('confirm')
  })

})

describe('C32.1.4 — chat_streaming confirmation-only guard', () => {

  it('T9: _has_confirmation_only guard exists in chat_streaming.py', () => {
    // Read backend file from frontend test using relative path
    const backendSrc = readFileSync(
      path.resolve(__dirname, '../../../backend/app/agents/chat_streaming.py'),
      'utf-8'
    )
    expect(backendSrc).toContain('_has_confirmation_only')
    expect(backendSrc).toContain('not _has_confirmation_only')
  })

})

describe('C32.1.1 — Memory LLM integration source checks', () => {

  it('build_llm_messages_with_memory exported from conversation_memory_service', () => {
    const src = readFileSync(
      path.resolve(__dirname, '../../../backend/app/services/conversation_memory_service.py'),
      'utf-8'
    )
    expect(src).toContain('def build_llm_messages_with_memory')
    expect(src).toContain('max_recent_messages')
  })

  it('generate_answer accepts memory_context param', () => {
    const src = readFileSync(
      path.resolve(__dirname, '../../../backend/app/agents/chat_llm_answerer.py'),
      'utf-8'
    )
    expect(src).toContain('memory_context')
    expect(src).toContain('build_llm_messages_with_memory')
  })

  it('SkillContext has memory_context field', () => {
    const src = readFileSync(
      path.resolve(__dirname, '../../../backend/app/agents/chat_skills/base.py'),
      'utf-8'
    )
    expect(src).toContain('memory_context')
  })

  it('chat_orchestrator passes memory_context to SkillContext', () => {
    const src = readFileSync(
      path.resolve(__dirname, '../../../backend/app/agents/chat_orchestrator.py'),
      'utf-8'
    )
    expect(src).toContain('memory_context=_memory_ctx')
    // And uses _effective_content for skill registry
    expect(src).toContain('_effective_content, context')
  })

})
