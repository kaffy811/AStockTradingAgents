<template>
  <div class="about-wrap">
    <button class="about-toggle" @click="expanded = !expanded">
      <span class="about-toggle-icon">ℹ️</span>
      <span class="about-toggle-label">了解系统能力</span>
      <span class="about-caret">{{ expanded ? '▲' : '▼' }}</span>
    </button>

    <div v-if="expanded" class="about-body">
      <div class="about-section">
        <h3 class="about-heading">关于 TradingAgents</h3>
        <p class="about-text">
          TradingAgents 是一个 AI 股票研究工作台，支持基于行情、技术指标、基本面、同行对比与新闻信息，
          通过多 Agent 并行分析生成综合研究报告。
        </p>
      </div>

      <div class="about-cols">
        <div class="about-section">
          <h4 class="about-sub-heading">核心能力</h4>
          <ul class="about-list">
            <li>A 股与港股搜索与身份确认</li>
            <li>技术图表与均线指标分析</li>
            <li>行业热门股发现（申万一级）</li>
            <li>基本面、同行对比与新闻信息整合</li>
            <li>数据完整度四维度评分</li>
            <li>报告保存、历史查询与自选股管理</li>
            <li>Markdown 下载、PDF 打印与分享文本导出</li>
          </ul>
        </div>

        <div class="about-section">
          <h4 class="about-sub-heading">数据边界</h4>
          <ul class="about-list">
            <li>A 股行业分类基于申万行业体系</li>
            <li>港股行业与同行覆盖仍在扩展中</li>
            <li>新闻数据受数据源与时间窗口影响</li>
            <li>行情数据有缓存机制，非实时推送</li>
            <li>港股基本面字段覆盖有限</li>
          </ul>
        </div>
      </div>

      <p class="about-disclaimer">
        ⚠️ 本系统报告仅供研究参考，不构成任何投资建议。投资有风险，决策需谨慎。
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
const expanded = ref(false)
</script>

<style scoped>
.about-wrap {
  margin-bottom: 20px;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  background: var(--surface);
}

/* ── Toggle bar ── */
.about-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 14px;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  color: var(--muted);
  font-size: 12px;
  font-weight: 500;
  transition: background 0.15s, color 0.15s;
}

.about-toggle:hover {
  background: var(--surface2);
  color: var(--text);
}

.about-toggle-icon {
  font-size: 13px;
  line-height: 1;
  flex-shrink: 0;
}

.about-toggle-label {
  flex: 1;
  white-space: nowrap;
}

.about-caret {
  font-size: 9px;
  flex-shrink: 0;
}

/* ── Body ── */
.about-body {
  padding: 16px 16px 12px;
  border-top: 1px solid var(--border);
  background: var(--surface-hover);
}

.about-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 12px;
}

.about-section {
  margin-bottom: 12px;
}

.about-heading {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 8px;
}

.about-sub-heading {
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 6px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.about-text {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.6;
  margin: 0;
}

.about-list {
  margin: 0;
  padding: 0 0 0 14px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.8;
}

.about-list li {
  margin: 0;
}

.about-disclaimer {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.5;
  margin: 0;
  padding-top: 10px;
  border-top: 1px solid var(--border);
  opacity: 0.85;
}

/* ── Mobile ── */
@media (max-width: 540px) {
  .about-cols {
    grid-template-columns: 1fr;
    gap: 0;
  }

  .about-body {
    padding: 14px 12px 10px;
  }
}
</style>
