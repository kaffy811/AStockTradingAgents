/**
 * chatEventNormalizer.js — Phase 2E-3.
 *
 * Maps raw SSE backend event types + payloads to standardized UI events
 * consumed by chatReducer. Pure function — no side effects, no Vue imports.
 *
 * Returns null for unknown / non-visual events (caller should ignore).
 */

// ── Display name tables ────────────────────────────────────────────────────────

export const TOOL_DISPLAY_NAMES = {
  stock_quote:                       '查询实时行情',
  stock_kline:                       '查询 K 线数据',
  financial_news:                    '检索相关新闻',
  financial_rag_search:              '检索金融知识库',
  official_financial_report_search:  '搜索官方财报',
  verify_financial_report:           '审核财报来源',
  financial_document_ingest:         '导入财报知识库',
  // C25: new realtime search tools
  universal_market_search:           '搜索市场热点',
  search_realtime_news:              '搜索实时财经新闻',
  get_industry_news_tool:            '检索行业新闻',
  // FinancialAgent tool name variants
  stock_quote_tool:                  '查询实时行情',
  stock_kline_tool:                  '查询 K 线数据',
  financial_news_tool:               '检索相关新闻',
  // Report skill tools
  get_recent_reports_tool:           '查找历史报告',
  get_report_detail_tool:            '读取报告详情',
  // Watchlist & action tools
  watchlist_add_tool:                '添加自选股',
  watchlist_remove_tool:             '移除自选股',
  watchlist_list_tool:               '查看自选股列表',
  get_watchlist_tool:                '查看自选股',
}

export const AGENT_DISPLAY_NAMES = {
  fundamental_agent: '基本面分析 Agent',
  market_agent:      '行情分析 Agent',
  news_agent:        '新闻事件 Agent',
  risk_review_agent: '风险审核 Agent',
  synthesis_agent:   '综合生成 Agent',
}

// ── Main normalizer ────────────────────────────────────────────────────────────

/**
 * Convert one raw SSE event into a standardized UI event object.
 *
 * @param {string} rawEventType  SSE event type string from backend
 * @param {object} rawPayload    Parsed payload (may be undefined)
 * @returns {object|null}        Normalized UI event, or null to ignore
 */
export function normalizeChatEvent(rawEventType, rawPayload) {
  const p = rawPayload ?? {}

  switch (rawEventType) {

    // ── FinancialAgent tool call events ────────────────────────────────────────
    case 'tool_call_start':
      return {
        type:    'ui_tool_start',
        stepKey: `tool:${p.tool_name}`,
        title:   TOOL_DISPLAY_NAMES[p.tool_name] ?? p.display_name ?? p.tool_name ?? 'tool',
        status:  'running',
        detail:  p.arguments ? JSON.stringify(p.arguments).slice(0, 80) : '',
      }

    case 'tool_call_result':
      return {
        type:    'ui_tool_done',
        stepKey: `tool:${p.tool_name}`,
        title:   TOOL_DISPLAY_NAMES[p.tool_name] ?? p.display_name ?? p.tool_name ?? 'tool',
        status:  p.status === 'success' ? 'success' : 'error',
        summary: p.result_summary ?? (p.status === 'success' ? '完成' : '失败'),
      }

    // ── Legacy planner tool events ─────────────────────────────────────────────
    case 'tool_started':
      return {
        type:    'ui_tool_start',
        stepKey: `tool:${p.tool_name ?? 'planner_tool'}`,
        title:   TOOL_DISPLAY_NAMES[p.tool_name] ?? p.tool_name ?? '工具执行',
        status:  'running',
        detail:  '',
      }

    case 'tool_completed': {
      const tn = p.tool_event?.name ?? p.tool_name ?? 'planner_tool'
      return {
        type:    'ui_tool_done',
        stepKey: `tool:${tn}`,
        title:   TOOL_DISPLAY_NAMES[tn] ?? tn,
        status:  p.tool_event?.status ?? p.status ?? 'success',
        summary: p.tool_event?.summary ?? p.summary ?? '',
      }
    }

    // ── RAG retrieval / review events ──────────────────────────────────────────
    case 'rag_retrieve_started':
      return {
        type:    'ui_tool_start',
        stepKey: 'tool:rag_retrieve',
        title:   '检索金融知识库',
        status:  'running',
        detail:  '',
      }

    case 'rag_retrieve_completed':
      return {
        type:    'ui_tool_done',
        stepKey: 'tool:rag_retrieve',
        title:   '检索金融知识库',
        status:  p.ok ? 'success' : 'error',
        summary: p.ok
          ? `检索到 ${p.documents_count ?? 0} 份资料${p.source_types?.length ? `（${p.source_types.join('/')}）` : ''}`
          : 'RAG 检索失败',
      }

    case 'rag_review_started':
      return {
        type:    'ui_tool_start',
        stepKey: 'tool:rag_review',
        title:   '资料质量审查',
        status:  'running',
        detail:  '',
      }

    case 'rag_review_completed': {
      const conf = p.overall_confidence ?? 'medium'
      return {
        type:    'ui_tool_done',
        stepKey: 'tool:rag_review',
        title:   '资料质量审查',
        status:  'success',
        summary: `资料可信度：${conf === 'high' ? '高' : conf === 'low' ? '较低' : '中等'}`,
      }
    }

    // ── Skill routing events ───────────────────────────────────────────────────
    case 'skill_started':
      return {
        type:    'ui_tool_start',
        stepKey: `tool:skill:${p.skill_name ?? p.skill_spec ?? 'unknown'}`,
        title:   '技能路由',
        status:  'running',
        detail:  p.skill_name ?? p.source ?? '',
      }

    case 'skill_completed':
      return {
        type:    'ui_tool_done',
        stepKey: `tool:skill:${p.skill_name ?? 'unknown'}`,
        title:   '技能路由',
        status:  'success',
        summary: p.skill_name ?? '完成',
      }

    // ── Planner step events ────────────────────────────────────────────────────
    case 'planner_step_started':
      return {
        type:    'ui_tool_start',
        stepKey: `step:${p.name ?? p.step_id ?? 'step'}`,
        title:   p.name ?? `步骤 ${p.step_id ?? ''}`,
        status:  'running',
        detail:  '',
      }

    case 'planner_step_completed': {
      const ok = p.status === 'completed' || p.status === 'success'
      return {
        type:    'ui_tool_done',
        stepKey: `step:${p.name ?? p.step_id ?? 'step'}`,
        title:   p.name ?? `步骤 ${p.step_id ?? ''}`,
        status:  ok ? 'success' : 'error',
        summary: p.status ?? '完成',
      }
    }

    // ── Streaming content ──────────────────────────────────────────────────────
    case 'thinking':
      return {
        type:    'ui_thinking_delta',
        content: p.content ?? '',
      }

    case 'answer_delta':
      return {
        type:    'ui_answer_delta',
        content: p.delta ?? p.content ?? '',
      }

    // ── Multi-Agent Orchestrator events ────────────────────────────────────────
    case 'orchestrator_start':
      return {
        type:    'ui_step_start',
        stepKey: 'orchestrator',
        title:   '多 Agent 研究开始',
        status:  'running',
        summary: p.query ? `分析: ${String(p.query).slice(0, 60)}` : '',
      }

    case 'subagent_start':
      return {
        type:    'ui_step_start',
        stepKey: `agent:${p.agent_name}`,
        title:   AGENT_DISPLAY_NAMES[p.agent_name] ?? p.display_name ?? p.agent_name ?? 'Agent',
        status:  'running',
        summary: '',
      }

    case 'subagent_result':
      return {
        type:         'ui_step_done',
        stepKey:      `agent:${p.agent_name}`,
        title:        AGENT_DISPLAY_NAMES[p.agent_name] ?? p.display_name ?? p.agent_name ?? 'Agent',
        status:       p.status ?? 'success',
        summary:      p.summary ?? '',
        riskFlags:    p.risk_flags ?? [],
        sourcesCount: p.sources_count ?? 0,
      }

    case 'risk_review_start': {
      const stage = p.stage ?? 'pre_synthesis'
      return {
        type:    'ui_step_start',
        stepKey: `risk_review:${stage}`,
        title:   stage === 'post_synthesis' ? '输出合规复核' : '数据与合规审核',
        status:  'running',
        summary: '',
      }
    }

    case 'risk_review_result': {
      const stage = p.stage ?? 'pre_synthesis'
      const blocked = p.blocked
      return {
        type:          'ui_step_done',
        stepKey:       `risk_review:${stage}`,
        title:         stage === 'post_synthesis' ? '输出合规复核' : '数据与合规审核',
        status:        blocked ? 'failed' : 'success',
        summary:       blocked ? '发现合规问题，已自动处理' : '审核通过',
        issues:        p.issues ?? [],
        requiredEdits: p.required_edits ?? [],
      }
    }

    case 'synthesis_start':
      return {
        type:    'ui_step_start',
        stepKey: 'synthesis',
        title:   '综合生成分析结论',
        status:  'running',
        summary: '',
      }

    // ── Final answer ───────────────────────────────────────────────────────────
    case 'final_answer': {
      const fa = (p && typeof p === 'object' && p.final_answer) ? p.final_answer : p
      return {
        type: 'ui_final_answer',
        data: fa,
      }
    }

    // ── C27: data quality update (skill path — no final_answer event) ─────────
    case 'data_quality_update':
      return {
        type:        'ui_data_quality_update',
        dataQuality: p.data_quality ?? null,
        sources:     p.sources ?? [],
      }

    // ── Terminal events ────────────────────────────────────────────────────────
    // C25: treat all done-like variants as ui_done for robustness
    case 'agent_completed':
    case 'done':
    case 'completed':
    case 'stream_done':
      return { type: 'ui_done' }

    case 'agent_error':
      return {
        type:    'ui_error',
        message: p.error ?? p.message ?? p.content ?? '发生错误',
      }

    // ── Agent lifecycle ────────────────────────────────────────────────────────
    // Section III (Method B): agent_started enters the normalizer so side-effects
    // in _handleEvent can break instead of return, letting the step appear in the panel.
    case 'agent_started':
      return {
        type:    'ui_step_start',
        stepKey: 'agent_started',
        title:   'AI 助理开始分析',
        status:  'running',
      }

    // Non-visual / unknown events — caller handles or ignores
    default:
      return null
  }
}
