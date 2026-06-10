<template>
  <div class="hero-wrap">
    <div class="hero-body">
      <h1 class="hero-title">{{ t('hero_title') }}</h1>
      <p class="hero-sub">{{ t('hero_subtitle') }}</p>
      <div class="hero-chips">
        <span class="hero-chip">{{ t('hero_chip_multi_agent') }}</span>
        <span class="hero-chip">{{ t('hero_chip_a_shares') }}</span>
        <span class="hero-chip">{{ t('hero_chip_hk') }}</span>
        <span class="hero-chip">{{ t('hero_chip_charts') }}</span>
        <span class="hero-chip">{{ t('hero_chip_reports') }}</span>
        <span class="hero-chip">{{ t('hero_chip_watchlist') }}</span>
      </div>
      <p class="hero-risk">{{ t('hero_disclaimer') }}</p>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from '../utils/i18n.js'
const { t } = useI18n()
</script>

<style scoped>
.hero-wrap {
  margin-bottom: 20px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: linear-gradient(135deg, var(--surface-hover) 0%, var(--surface-hover) 100%);
  overflow: hidden;
}

.hero-body {
  padding: 24px 24px 20px;
}

.hero-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 8px;
  line-height: 1.3;
}

.hero-sub {
  font-size: 13px;
  color: var(--muted);
  margin: 0 0 14px;
  line-height: 1.6;
  max-width: 560px;
}

.hero-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 14px;
}

.hero-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  background: var(--status-info-bg);
  border: 1px solid var(--status-info-ring);
  border-radius: 20px;
  color: var(--accent);
  white-space: nowrap;
}

.hero-risk {
  font-size: 11px;
  color: var(--muted);
  margin: 0;
  line-height: 1.5;
  opacity: 0.75;
}

/* ── Mobile ── */
@media (max-width: 540px) {
  .hero-body {
    padding: 18px 16px 16px;
  }

  .hero-title {
    font-size: 17px;
  }

  .hero-sub {
    font-size: 12px;
  }

  .hero-chips {
    gap: 5px;
  }

  .hero-chip {
    font-size: 10px;
    padding: 2px 8px;
  }
}
</style>
