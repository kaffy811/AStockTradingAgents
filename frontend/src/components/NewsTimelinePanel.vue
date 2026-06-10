<template>
  <div class="news-panel">

    <!-- ── 标题行 ─────────────────────────────────────────────────────────── -->
    <div class="panel-header">
      <span class="card-title">近 {{ hours }} 小时相关新闻</span>
      <span v-if="!loading && !error && newsItems.length > 0" class="news-count">
        共 {{ newsItems.length }} 条
      </span>
    </div>

    <!-- ── 加载中 ──────────────────────────────────────────────────────────── -->
    <div v-if="loading" class="state-row">
      <span class="spinner"></span>
      <span class="state-text">加载新闻…</span>
    </div>

    <!-- ── 加载失败 ────────────────────────────────────────────────────────── -->
    <EmptyState
      v-else-if="error"
      icon="⚠️"
      title="新闻加载失败"
      :message="error"
      action-text="重试"
      :compact="true"
      @action="emit('retry')"
    />

    <!-- ── 无新闻 ──────────────────────────────────────────────────────────── -->
    <EmptyState
      v-else-if="newsItems.length === 0"
      icon="📰"
      title="暂无相关新闻"
      message="近 72 小时内暂无该股票的相关新闻数据。"
      :compact="true"
    />

    <template v-else>

      <!-- ── 影响摘要 ─────────────────────────────────────────────────────── -->
      <div :class="['impact-bar', impactSummary.riskCount > 0 ? 'impact-bar--risk' : 'impact-bar--normal']">
        <span class="impact-icon">{{ impactSummary.riskCount > 0 ? '⚠' : '📋' }}</span>
        <span class="impact-text">{{ impactSummary.summary }}</span>
      </div>

      <!-- ── 分类筛选 chips ──────────────────────────────────────────────── -->
      <div class="filter-chips">
        <button
          v-for="chip in FILTER_CHIPS"
          :key="chip.type"
          :class="[
            'chip',
            activeFilter === chip.type ? 'chip--active' : '',
            chip.type === 'risk' ? 'chip--risk-style' : '',
          ]"
          @click="setFilter(chip.type)"
        >{{ chip.label }}</button>
      </div>

      <!-- ── 筛选后条数提示 ────────────────────────────────────────────────── -->
      <div v-if="activeFilter !== 'all'" class="filter-count">
        当前筛选：{{ filteredItems.length }} 条
      </div>

      <!-- ── 无筛选结果 ─────────────────────────────────────────────────────── -->
      <EmptyState
        v-if="filteredItems.length === 0"
        icon="🔍"
        title="该分类暂无新闻"
        message="当前筛选条件下无匹配新闻，切换【全部】可查看所有新闻。"
        :compact="true"
      />

      <!-- ── 新闻时间线 ─────────────────────────────────────────────────────── -->
      <div v-else class="news-timeline">
        <div
          v-for="(item, idx) in filteredItems"
          :key="idx"
          class="news-item"
        >
          <!-- 时间线左侧装饰线 + 圆点 -->
          <div class="tl-gutter">
            <span :class="['tl-dot', `dot--${item._cls.type}`]"></span>
            <span v-if="idx < filteredItems.length - 1" class="tl-line"></span>
          </div>

          <!-- 新闻内容 -->
          <div class="news-body">
            <div class="news-item-meta">
              <span :class="['type-badge', `badge--${item._cls.type}`]">
                {{ item._cls.label }}
              </span>
              <span class="news-source">{{ item.source || '来源未知' }}</span>
              <span class="news-time">{{ formatNewsTime(item.publish_time) }}</span>
            </div>
            <p class="news-title">{{ item.title }}</p>
            <p v-if="item.summary" class="news-snippet">{{ item.summary }}</p>
            <div v-if="item.url" class="news-link-row">
              <a
                :href="item.url"
                target="_blank"
                rel="noopener noreferrer"
                class="news-link"
              >查看原文 →</a>
            </div>
          </div>
        </div>
      </div>

    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import EmptyState from './EmptyState.vue'
import { classifyNewsItem, buildNewsImpactSummary, formatNewsTime } from '../utils/newsInsights.js'

// ── Props / emits ─────────────────────────────────────────────────────────────
const props = defineProps({
  newsItems: { type: Array,   default: () => [] },
  loading:   { type: Boolean, default: false },
  error:     { type: String,  default: '' },
  hours:     { type: Number,  default: 72 },
  compact:   { type: Boolean, default: false },
})

const emit = defineEmits(['retry'])

// ── Filter chips config ───────────────────────────────────────────────────────
const FILTER_CHIPS = [
  { type: 'all',      label: '全部'   },
  { type: 'risk',     label: '风险关注' },
  { type: 'earnings', label: '业绩相关' },
  { type: 'policy',   label: '政策监管' },
  { type: 'market',   label: '市场动态' },
  { type: 'product',  label: '业务动态' },
  { type: 'neutral',  label: '其他'   },
]

// ── Active filter ─────────────────────────────────────────────────────────────
const activeFilter = ref('all')

function setFilter(type) {
  activeFilter.value = type
}

// 股票切换时重置筛选
watch(() => props.newsItems, () => {
  activeFilter.value = 'all'
})

// ── Classified + sorted items ─────────────────────────────────────────────────
const classifiedItems = computed(() => {
  const items = props.newsItems || []
  return items
    .map(item => ({ ...item, _cls: classifyNewsItem(item) }))
    .sort((a, b) => {
      const ta = a.publish_time ? new Date(a.publish_time).getTime() : 0
      const tb = b.publish_time ? new Date(b.publish_time).getTime() : 0
      return tb - ta
    })
})

const filteredItems = computed(() => {
  if (activeFilter.value === 'all') return classifiedItems.value
  return classifiedItems.value.filter(item => item._cls.type === activeFilter.value)
})

// ── Impact summary ────────────────────────────────────────────────────────────
const impactSummary = computed(() => buildNewsImpactSummary(props.newsItems || []))
</script>

<style scoped>
/* ── Header ── */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.news-count {
  font-size: 12px;
  color: var(--muted);
}

/* ── State row ── */
.state-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0;
  color: var(--muted);
  font-size: 13px;
}

.state-text { color: var(--muted); font-size: 13px; }

/* ── Impact bar ── */
.impact-bar {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface2);
  margin-bottom: 12px;
  font-size: 12px;
  line-height: 1.55;
}

.impact-bar--risk {
  border-color: var(--status-warn-ring);
  background:   var(--status-warn-bg);
}

.impact-bar--normal {
  border-color: var(--status-info-ring);
  background:   var(--surface-hover);
}

.impact-icon {
  flex-shrink: 0;
  font-size: 14px;
  line-height: 1.4;
}

.impact-text {
  color: var(--text);
}

/* ── Filter chips ── */
.filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.chip {
  padding: 3px 10px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 20px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--muted);
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.12s, background 0.12s, border-color 0.12s;
}

.chip:hover {
  color: var(--accent);
  background: var(--status-info-bg);
  border-color: var(--status-info-ring);
}

.chip--active {
  color: var(--accent);
  background: var(--status-info-bg);
  border-color: var(--border-glow);
  font-weight: 600;
}

.chip--risk-style.chip--active {
  color: var(--warn);
  background: var(--status-warn-bg);
  border-color: var(--status-warn-ring);
}

/* ── Filter count ── */
.filter-count {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 10px;
  padding-left: 2px;
}

/* ── Timeline layout ── */
.news-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.news-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

/* ── Gutter (dot + line) ── */
.tl-gutter {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 14px;
  padding-top: 4px;
}

.tl-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  border: 2px solid currentColor;
}

.dot--risk     { color: var(--warn);    background: var(--status-warn-ring); }
.dot--earnings { color: var(--accent);  background: var(--status-info-ring);  }
.dot--policy   { color: var(--muted);   background: rgba(122, 133, 156, 0.2); }
.dot--market   { color: var(--success); background: var(--status-down-ring);  }
.dot--product  { color: var(--accent-secondary);        background: var(--accent-glow); }
.dot--neutral  { color: var(--border);  background: var(--surface2);          }

.tl-line {
  width: 1px;
  flex: 1;
  min-height: 20px;
  background: var(--border);
  margin-top: 4px;
}

/* ── News body ── */
.news-body {
  flex: 1;
  min-width: 0;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 0;
}

.news-item:last-child .news-body {
  border-bottom: none;
  padding-bottom: 4px;
}

.news-item-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 6px;
}

/* ── Type badge ── */
.type-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
  white-space: nowrap;
  flex-shrink: 0;
}

.badge--risk     { background: var(--status-warn-bg); color: var(--warn);    border: 1px solid var(--status-warn-ring);  }
.badge--earnings { background: var(--status-info-bg); color: var(--accent);  border: 1px solid var(--status-info-ring);  }
.badge--policy   { background: var(--surface-muted); color: var(--muted);   border: 1px solid var(--border);             }
.badge--market   { background: var(--status-down-bg); color: var(--success); border: 1px solid var(--status-down-ring);  }
.badge--product  { background: var(--accent-glow); color: var(--accent-secondary);        border: 1px solid var(--border-glow); }
.badge--neutral  { background: var(--surface2);            color: var(--muted);   border: 1px solid var(--border);             }

/* ── Meta text ── */
.news-source {
  font-size: 11px;
  color: var(--accent);
  font-weight: 500;
  white-space: nowrap;
}

.news-time {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
  margin-left: auto;
}

/* ── Content ── */
.news-title {
  font-size: 13px;
  color: var(--text);
  line-height: 1.5;
  margin: 0 0 6px;
  word-break: break-word;
}

.news-snippet {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.55;
  margin: 0 0 6px;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.news-link-row {
  margin-top: 4px;
}

.news-link {
  font-size: 11px;
  color: var(--accent);
  text-decoration: none;
  font-weight: 500;
  opacity: 0.85;
  transition: opacity 0.12s;
}

.news-link:hover {
  opacity: 1;
  text-decoration: underline;
}

/* ── Mobile ── */
@media (max-width: 540px) {
  .filter-chips { gap: 5px; }
  .chip         { font-size: 10px; padding: 2px 8px; }

  .news-item-meta {
    gap: 4px;
  }

  .news-time {
    margin-left: 0;
    width: 100%;
    order: 3;
  }

  .tl-gutter { display: none; }
  .news-item  { gap: 0; }

  .news-body {
    padding-bottom: 14px;
  }
}
</style>
