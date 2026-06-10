<template>
  <div class="dqs-wrap">
    <!-- ── Summary bar ── -->
    <div class="dqs-bar">
      <div class="dqs-overall">
        <span class="dqs-label">数据完整度：</span>
        <span :class="['dqs-grade', gradeClass]">{{ gradeName }}</span>
        <span class="dqs-score">{{ scores.overall }}/100</span>
      </div>

      <div class="dqs-chips">
        <span
          v-for="dim in DIMS"
          :key="dim.key"
          :class="['dqs-chip', scoreChipClass(scores[dim.key])]"
          :title="descriptions[dim.key]"
        >
          {{ dim.label }} {{ scores[dim.key] }}
        </span>
      </div>

      <button class="dqs-toggle" @click="expanded = !expanded">
        {{ expanded ? '收起' : '查看数据边界' }}
        <span class="dqs-caret">{{ expanded ? '▲' : '▼' }}</span>
      </button>
    </div>

    <!-- ── Expanded detail ── -->
    <div v-if="expanded" class="dqs-detail">
      <div
        v-for="dim in DIMS"
        :key="dim.key"
        class="dqs-row"
      >
        <div class="dqs-row-head">
          <span :class="['dqs-dot', scoreChipClass(scores[dim.key])]"></span>
          <span class="dqs-dim-label">{{ dim.label }}</span>
          <span class="dqs-dim-score">{{ scores[dim.key] }}/100</span>
        </div>
        <p class="dqs-desc">{{ descriptions[dim.key] }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  result: { type: Object, required: true },
})

const expanded = ref(false)

const ALL_DIMS = [
  { key: 'technical',       agentKey: 'technical',       label: '技术面'   },
  { key: 'fundamental',     agentKey: 'fundamental',     label: '基本面'   },
  { key: 'peer',            agentKey: 'peer_comparison', label: '同行对比' },
  { key: 'news',            agentKey: 'news',            label: '新闻面'   },
]

// Only show dimensions that were actually run (not skipped)
const DIMS = computed(() =>
  ALL_DIMS.filter(dim => {
    const status = props.result?.metadata?.agents?.[dim.agentKey]?.status
    return status !== 'skipped'
  })
)

// ── Helpers ───────────────────────────────────────────────────────────────────
function textOf(key) {
  return props.result?.sections?.[key] || ''
}
function agentStatus(key) {
  return props.result?.metadata?.agents?.[key]?.status || 'ok'
}
function warnings() {
  return props.result?.metadata?.warnings || []
}
function warnHas(...kws) {
  return warnings().some(w => kws.some(k => w.toLowerCase().includes(k.toLowerCase())))
}
function textHas(text, ...kws) {
  return kws.some(k => text.includes(k))
}
function clamp(v) { return Math.max(0, Math.min(100, v)) }

// ── Score computation ─────────────────────────────────────────────────────────
const scores = computed(() => {
  const market  = props.result?.market || 'CN'
  const report  = props.result?.report || ''
  const secs    = props.result?.sections || {}

  // ── Technical ──────────────────────────────────────────────────────────────
  let tech = 85
  if (!secs.technical || textHas(secs.technical, '[technical 模块暂时不可用')) {
    tech = 0
  } else if (agentStatus('technical') === 'failed' || agentStatus('technical') === 'timeout') {
    tech = 0
  } else {
    tech += 5  // section present and not failed → 90
    if (warnHas('stale', 'cache', 'kline', '行情降级', 'fallback')) tech -= 15
  }

  // ── Fundamental ────────────────────────────────────────────────────────────
  let fund = 70
  const fundText = textOf('fundamental')
  if (!fundText || textHas(fundText, '[fundamental 模块暂时不可用')) {
    fund = 0
  } else if (agentStatus('fundamental') === 'failed' || agentStatus('fundamental') === 'timeout') {
    fund = 0
  } else {
    if (agentStatus('fundamental') === 'warning') fund -= 10
    if (market === 'HK') fund -= 15
    const allText = fundText + ' ' + report
    if (textHas(allText, '字段缺失', '当前数据源未返回', '估值字段缺失', 'valuation fields are missing')) fund -= 20
    if (textHas(allText, 'PE', 'PB', 'PS', '市值', '股息率') &&
        textHas(allText, '缺失', '不可用', '未返回', 'null')) fund -= 10
  }

  // ── Peer comparison ────────────────────────────────────────────────────────
  let peer = 70
  const peerText = textOf('peer_comparison')
  if (!peerText || textHas(peerText, '[peer_comparison 模块暂时不可用')) {
    peer = 0
  } else if (agentStatus('peer_comparison') === 'failed' || agentStatus('peer_comparison') === 'timeout') {
    peer = 0
  } else {
    if (warnHas('peer comparison is unavailable')) {
      peer = 30
    } else {
      if (market === 'HK') peer = Math.max(40, peer - 20)
      if (textHas(peerText, '样本有限', '不代表完整行业覆盖', '手动映射', '手动配置', 'PEER_MAP')) peer -= 15
      if (textHas(peerText, '暂无同行', '未配置同行', 'peers=[]')) peer = Math.min(peer, 30)
    }
  }

  // ── News ───────────────────────────────────────────────────────────────────
  let news = 70
  const newsText = textOf('news')
  if (!newsText || textHas(newsText, '[news 模块暂时不可用')) {
    news = 0
  } else if (agentStatus('news') === 'failed' || agentStatus('news') === 'timeout') {
    news = 20
  } else {
    if (warnHas('news data is unavailable') ||
        textHas(newsText, '暂无相关新闻', '暂无新闻', '0 条', 'items 为空', '近72小时无', '本时间窗口内暂无新闻')) {
      news = 40
    }
    if (warnHas('news relevance may be limited') || textHas(newsText, '关键词搜索', 'keyword search')) {
      news -= 10
    }
  }

  // Overall: average only non-skipped dims
  const activeDimScores = []
  const agents = props.result?.metadata?.agents || {}
  if (agents.technical?.status       !== 'skipped') activeDimScores.push(clamp(tech))
  if (agents.fundamental?.status     !== 'skipped') activeDimScores.push(clamp(fund))
  if (agents.peer_comparison?.status !== 'skipped') activeDimScores.push(clamp(peer))
  if (agents.news?.status            !== 'skipped') activeDimScores.push(clamp(news))
  const overall = activeDimScores.length > 0
    ? Math.round(activeDimScores.reduce((a, b) => a + b, 0) / activeDimScores.length)
    : 0

  return {
    technical:   clamp(tech),
    fundamental: clamp(fund),
    peer:        clamp(peer),
    news:        clamp(news),
    overall:     clamp(overall),
  }
})

// ── Grade ──────────────────────────────────────────────────────────────────────
const gradeName = computed(() => {
  const s = scores.value.overall
  if (s >= 80) return '较完整'
  if (s >= 60) return '中等'
  if (s >= 40) return '有限'
  return '较弱'
})

const gradeClass = computed(() => {
  const s = scores.value.overall
  if (s >= 80) return 'dqs-grade--good'
  if (s >= 60) return 'dqs-grade--medium'
  if (s >= 40) return 'dqs-grade--low'
  return 'dqs-grade--weak'
})

function scoreChipClass(s) {
  if (s >= 80) return 'chip--good'
  if (s >= 60) return 'chip--medium'
  if (s >= 40) return 'chip--low'
  return 'chip--weak'
}

// ── Descriptions ─────────────────────────────────────────────────────────────
const descriptions = computed(() => {
  const market = props.result?.market || 'CN'
  const s = scores.value

  let techDesc = ''
  if (s.technical === 0)    techDesc = 'K 线或技术指标数据不可用。'
  else if (s.technical < 70) techDesc = 'K 线数据为缓存或降级来源，技术指标可能不完整。'
  else                       techDesc = 'K 线数据可用，技术指标完整。'

  let fundDesc = ''
  if (s.fundamental === 0)      fundDesc = '基本面数据不可用。'
  else if (s.fundamental < 50)  fundDesc = `多项估值与盈利字段缺失${market === 'HK' ? '（港股基本面覆盖有限）' : ''}，当前基本面分析覆盖有限。`
  else if (s.fundamental < 70)  fundDesc = `部分字段缺失（如 PE/PB 等估值指标）${market === 'HK' ? '，港股基本面覆盖有限' : ''}，判断时请结合数据局限说明。`
  else                           fundDesc = '基本面字段基本可用，可支撑常规分析。'

  let peerDesc = ''
  if (s.peer === 0)         peerDesc = '同行对比数据不可用。'
  else if (s.peer <= 30)    peerDesc = market === 'HK'
      ? '港股暂不使用申万行业体系，同行与行业热门股数据可能缺失，行业对比覆盖有限。'
      : '暂无同行样本，当前不支持横向行业对比。'
  else if (s.peer < 60)     peerDesc = '同行样本数量有限，来自手动配置，不代表完整行业覆盖。横向对比仅供参考。'
  else                       peerDesc = '同行样本可用，横向对比结果仅供参考（样本基于热门股或手动配置）。'

  let newsDesc = ''
  if (s.news === 0)        newsDesc = '新闻数据不可用。'
  else if (s.news <= 20)   newsDesc = '新闻模块异常，新闻面分析不可用。'
  else if (s.news <= 40)   newsDesc = '近 72 小时暂无相关新闻，无法形成事件驱动判断，不代表该股长期无新闻。'
  else if (s.news < 70)    newsDesc = market === 'HK'
      ? '新闻通过关键词搜索获取，相关性需谨慎判断。'
      : '新闻数据可用，请结合其他维度综合判断。'
  else                      newsDesc = '新闻数据可用，请结合其他维度综合判断。'

  return {
    technical:   techDesc,
    fundamental: fundDesc,
    peer:        peerDesc,
    news:        newsDesc,
  }
})
</script>

<style scoped>
.dqs-wrap {
  margin-bottom: 16px;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}

/* ── Summary bar ── */
.dqs-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 14px;
  background: var(--surface-hover);
}

.dqs-overall {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.dqs-label {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

.dqs-grade {
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
}
.dqs-grade--good   { color: var(--success, #4caf50); }
.dqs-grade--medium { color: var(--warn, #f5a623); }
.dqs-grade--low    { color: var(--warn, #f5a623); opacity: 0.85; }
.dqs-grade--weak   { color: var(--danger, #f5554a); }

.dqs-score {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

/* ── Dimension chips ── */
.dqs-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  flex: 1;
  min-width: 0;
}

.dqs-chip {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
  cursor: default;
  border: 1px solid transparent;
}

.chip--good   { background: var(--status-down-bg);  border-color: var(--status-down-ring);  color: var(--success, #4caf50); }
.chip--medium { background: var(--status-warn-bg);  border-color: var(--status-warn-ring);  color: var(--warn, #f5a623);    }
.chip--low    { background: var(--status-warn-bg); border-color: var(--status-warn-ring); color: var(--warn, #f5a623);    opacity: 0.85; }
.chip--weak   { background: var(--status-up-bg);  border-color: var(--status-up-ring);  color: var(--danger, #f5554a);  }

/* ── Toggle button ── */
.dqs-toggle {
  font-size: 11px;
  color: var(--muted);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
  transition: color 0.15s;
}
.dqs-toggle:hover { color: var(--accent); }
.dqs-caret { font-size: 9px; margin-left: 2px; }

/* ── Detail panel ── */
.dqs-detail {
  padding: 12px 14px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dqs-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dqs-row-head {
  display: flex;
  align-items: center;
  gap: 7px;
}

.dqs-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.chip--good   .dqs-dot, .dqs-dot.chip--good   { background: var(--success, #4caf50); }
.chip--medium .dqs-dot, .dqs-dot.chip--medium { background: var(--warn, #f5a623); }
.chip--low    .dqs-dot, .dqs-dot.chip--low    { background: var(--warn, #f5a623); opacity: 0.75; }
.chip--weak   .dqs-dot, .dqs-dot.chip--weak   { background: var(--danger, #f5554a); }

.dqs-dim-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

.dqs-dim-score {
  font-size: 11px;
  color: var(--muted);
}

.dqs-desc {
  font-size: 12px;
  color: var(--muted);
  margin: 0 0 0 15px;
  line-height: 1.6;
}

/* ── Mobile ── */
@media (max-width: 540px) {
  .dqs-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    padding: 10px 12px;
  }

  .dqs-chips {
    flex-wrap: wrap;
  }

  .dqs-toggle {
    align-self: flex-start;
  }

  .dqs-detail {
    padding: 10px 12px;
  }
}
</style>
