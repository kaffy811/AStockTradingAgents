<template>
  <div class="app-header">
    <div class="app-title">🤖 TradingAgents</div>

    <nav class="app-nav">
      <RouterLink to="/" class="nav-link" active-class="nav-link--active" exact>
        {{ t('nav_analysis') }}
      </RouterLink>
      <RouterLink to="/history" class="nav-link" active-class="nav-link--active">
        {{ t('nav_history') }}
      </RouterLink>
      <RouterLink to="/watchlist" class="nav-link" active-class="nav-link--active">
        {{ t('nav_watchlist') }}
      </RouterLink>
      <RouterLink to="/industries" class="nav-link" active-class="nav-link--active">
        {{ t('nav_industries') }}
      </RouterLink>
      <RouterLink to="/chat" class="nav-link" active-class="nav-link--active">
        {{ t('nav_chat') }}
      </RouterLink>
      <RouterLink to="/me" class="nav-link" active-class="nav-link--active">
        {{ t('nav_me') }}
      </RouterLink>
    </nav>

    <div class="user-badge">
      <span>{{ displayName }}</span>
      <button class="logout-btn" @click="authStore.logout" style="margin-left:8px">{{ t('nav_logout') }}</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { useI18n } from '../utils/i18n.js'

const authStore = useAuthStore()
const { t } = useI18n()

const displayName = computed(() => {
  const username = authStore.currentUser?.username
  const email    = authStore.currentUser?.email
  if (username && username !== 'string') return username
  if (email    && email    !== 'string') return email
  return t('nav_default_user')
})
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 28px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
  gap: 16px;
}

.app-title {
  font-size: 18px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--accent), var(--accent2));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  white-space: nowrap;
}

.app-nav {
  display: flex;
  gap: 4px;
  flex: 1;
  justify-content: center;
}

.nav-link {
  padding: 5px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--muted);
  text-decoration: none;
  transition: color 0.15s, background 0.15s;
}

.nav-link:hover { color: var(--text); background: var(--surface2); }

.nav-link--active {
  color: var(--accent);
  background: var(--accent-glow);
}

.user-badge {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

.user-badge span {
  color: var(--success);
  font-weight: 600;
}

.logout-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--muted);
  font-size: 12px;
  text-decoration: underline;
}

.logout-btn:hover { color: var(--danger); }

/* ── Mobile ≤640px: BottomTabBar takes over nav, hide .app-nav ── */
@media (max-width: 640px) {
  .app-nav {
    display: none;
  }
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .app-header {
    flex-wrap: wrap;
    gap: 8px 12px;
  }

  .app-title {
    flex-shrink: 0;
  }

  /* Nav moves to second row, scrolls horizontally if needed */
  .app-nav {
    order: 3;
    width: 100%;
    justify-content: flex-start;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    padding-bottom: 2px;
    scrollbar-width: none;
  }
  .app-nav::-webkit-scrollbar { display: none; }

  .user-badge {
    font-size: 11px;
    max-width: 170px;
  }

  /* Truncate long usernames / email addresses */
  .user-badge span {
    display: inline-block;
    max-width: 100px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    vertical-align: bottom;
  }
}
</style>
