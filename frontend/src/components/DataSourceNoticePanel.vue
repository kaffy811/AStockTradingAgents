<template>
  <div class="dsnp-card card">
    <div class="dsnp-header" @click="open = !open">
      <span class="dsnp-title">数据源与风险说明</span>
      <span class="dsnp-toggle-icon">{{ open ? '▲' : '▼' }}</span>
    </div>

    <div v-if="open" class="dsnp-body">

      <!-- 数据源 -->
      <div class="dsnp-section">
        <div class="dsnp-section-title">数据来源</div>
        <ul class="dsnp-list">
          <li>
            <strong>行情：</strong>多源聚合（Sina / Tencent / Eastmoney / yfinance），A 股与港股均适用，
            行情可能存在 15 分钟以上延迟，非实时交易数据。
          </li>
          <li>
            <strong>财务（基本面）：</strong>AkShare / Tushare / yfinance，
            覆盖 A 股主流上市公司；港股财务字段可能不完整。
          </li>
          <li>
            <strong>新闻：</strong>东方财富、新浪财经、Bing 等聚合，
            默认覆盖最近 72 小时（可在偏好设置中调整）；不同股票的新闻覆盖密度存在差异。
          </li>
          <li>
            <strong>行业分类：</strong>申万一级行业，仅覆盖 A 股（CN）；
            港股（HK）暂未接入行业分类体系。
          </li>
          <li>
            <strong>技术指标：</strong>MA / MACD / RSI 由前端基于 K 线数据实时计算，
            结果与第三方平台可能存在细微差异。
          </li>
        </ul>
      </div>

      <!-- 数据边界 -->
      <div class="dsnp-section">
        <div class="dsnp-section-title">数据边界</div>
        <ul class="dsnp-list">
          <li>行情数据存在延迟，不适合用于实时交易决策</li>
          <li>港股数据覆盖范围有限，部分字段可能缺失或不可用</li>
          <li>新闻来源可用性随时间变化，部分时间窗口内可能无新闻数据</li>
          <li>财务字段（市盈率、市值等）可能因数据源更新频率不同而有所滞后</li>
          <li>AI 报告基于多个 Agent 生成，各 Agent 独立运行，个别维度可能因数据缺失而降级</li>
        </ul>
      </div>

      <!-- 风险声明 -->
      <div class="dsnp-section dsnp-section--risk">
        <div class="dsnp-section-title dsnp-section-title--risk">风险声明</div>
        <ul class="dsnp-list">
          <li>本平台所有内容仅供个人研究和学习参考，不构成任何形式的投资建议或推荐。</li>
          <li>股票市场存在风险，投资者需自行判断并承担投资风险。</li>
          <li>分析报告不保证信息完整性或准确性，使用前请自行核实关键数据。</li>
          <li>本平台不对任何投资决策的损益结果负责。</li>
        </ul>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const open = ref(false)
</script>

<style scoped>
.dsnp-card {
  padding: 14px 20px;
}

.dsnp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}

.dsnp-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}

.dsnp-toggle-icon {
  font-size: 11px;
  color: var(--muted);
}

/* ── Body ── */
.dsnp-body {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.dsnp-section {}

.dsnp-section-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.dsnp-section-title--risk { color: var(--warn); }

.dsnp-section--risk .dsnp-list li {
  color: var(--muted);
}

.dsnp-list {
  margin: 0;
  padding-left: 16px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.6;
}

.dsnp-list strong {
  color: var(--text);
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .dsnp-card { padding: 12px 16px; }
}
</style>
