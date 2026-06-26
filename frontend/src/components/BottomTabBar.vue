<template>
  <nav v-if="shouldShow" class="bottom-tab-bar" role="navigation" aria-label="底部导航">
    <RouterLink
      v-for="tab in TABS"
      :key="tab.path"
      :to="tab.path"
      :class="['tab-item', { 'tab-item--active': isActive(tab) }]"
      :aria-label="tab.label"
    >
      <span class="tab-icon">{{ tab.icon }}</span>
      <span class="tab-label">{{ tab.label }}</span>
    </RouterLink>
  </nav>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from '../utils/i18n.js'

const route = useRoute()
const { t } = useI18n()

const TABS = computed(() => [
  { path: '/',           icon: '🔬', label: t('tab_analysis'),   exact: true },
  { path: '/watchlist',  icon: '⭐', label: t('tab_watchlist') },
  { path: '/industries', icon: '🏢', label: t('tab_industries') },
  { path: '/history',    icon: '📋', label: t('tab_history') },
  { path: '/chat',       icon: '💬', label: t('tab_chat') },
  { path: '/me',         icon: '👤', label: t('tab_me') },
])

// Paths that should not show the BottomTabBar (e.g. print / immersive views)
const HIDE_PREFIXES = ['/print']

const shouldShow = computed(() =>
  !HIDE_PREFIXES.some(p => route.path.startsWith(p))
)

function isActive(tab) {
  if (tab.exact) return route.path === tab.path
  return route.path.startsWith(tab.path)
}
</script>

<style scoped>
.bottom-tab-bar {
  /* Only shown on mobile */
  display: none;
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 56px;
  z-index: 200;
  background: var(--surface);
  border-top: 1px solid var(--border);
  /* iOS safe-area */
  padding-bottom: env(safe-area-inset-bottom);
  /* 5 equal columns */
  display: none;
  grid-template-columns: repeat(6, 1fr);
  align-items: stretch;
}

.tab-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  text-decoration: none;
  color: var(--muted);
  padding: 6px 0;
  transition: color 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.tab-item:hover,
.tab-item:focus-visible { color: var(--text); }

.tab-item--active {
  color: var(--accent);
}

.tab-icon {
  font-size: 18px;
  line-height: 1;
}

.tab-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

/* ── Show only on mobile ── */
@media (max-width: 640px) {
  .bottom-tab-bar {
    display: grid;
  }
}
</style>
