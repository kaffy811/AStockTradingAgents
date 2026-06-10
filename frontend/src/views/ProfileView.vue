<template>
  <div class="app-shell">
    <AppHeader />

    <!-- ── Page title ─────────────────────────────────────────────────────────── -->
    <div class="pv-title-bar">
      <div>
        <h1 class="pv-title">{{ t('profile_title') }}</h1>
        <p class="pv-subtitle">{{ t('profile_subtitle') }}</p>
      </div>
    </div>

    <!-- ── User identity card ─────────────────────────────────────────────────── -->
    <section class="card pv-hero">
      <div class="pv-avatar">{{ avatarChar }}</div>
      <div class="pv-user-info">
        <div class="pv-username">{{ displayName }}</div>
        <div class="pv-status">
          <span class="pv-status-dot"></span>
          <span class="pv-status-text">{{ t('profile_logged_in') }}</span>
        </div>
      </div>
      <button class="btn btn-sm pv-logout-btn" @click="handleLogout">{{ t('profile_logout') }}</button>
    </section>

    <!-- ── Research stats ──────────────────────────────────────────────────────── -->
    <section class="card pv-section">
      <ProfileResearchStats
        :watchlist-count="stats.watchlistCount"
        :report-total="stats.reportTotal"
        :auto-saved-count="stats.autoSavedCount"
        :unique-stocks-count="stats.uniqueStocksAnalyzed"
        :recent-search-count="recentSearches.length"
        :loading="statsLoading"
      />
    </section>

    <!-- ── Activity panel ──────────────────────────────────────────────────────── -->
    <ProfileActivityPanel
      :recent-reports="recentReports"
      :recent-searches="recentSearches"
      :loading="reportsLoading"
      @go-report="item => router.push(`/history/${item.id}`)"
      @pick-search="item => router.push(`/stocks/${item.market}/${item.symbol}`)"
      @clear-searches="handleClearSearches"
    />

    <!-- ── Settings panel ──────────────────────────────────────────────────────── -->
    <ProfileSettingsPanel
      :settings="settings"
      @update:settings="onSettingsPatch"
      @reset="handleResetSettings"
    />

    <!-- ── Data source notice ─────────────────────────────────────────────────── -->
    <DataSourceNoticePanel />

    <!-- ── System actions ─────────────────────────────────────────────────────── -->
    <section class="card pv-actions-section">
      <div class="pv-section-title">{{ t('profile_system_ops') }}</div>
      <div class="pv-actions">
        <button class="btn btn-sm btn-secondary" @click="handleClearSearches">
          {{ t('profile_clear_searches') }}
        </button>
        <button class="btn btn-sm btn-secondary" @click="handleResetSettings">
          {{ t('profile_reset_settings') }}
        </button>
        <button class="btn btn-sm pv-logout-btn" @click="handleLogout">
          {{ t('profile_logout') }}
        </button>
      </div>
    </section>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore }   from '../stores/auth.js'
import { listReports }    from '../api/reports.js'
import { listWatchlist }  from '../api/watchlist.js'
import { getRecentSearches, clearRecentSearches } from '../utils/recentSearches.js'
import { getSettings, saveSettings, resetSettings, SETTINGS_EVENT } from '../utils/settings.js'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()
import AppHeader              from '../components/AppHeader.vue'
import ProfileResearchStats   from '../components/ProfileResearchStats.vue'
import ProfileActivityPanel   from '../components/ProfileActivityPanel.vue'
import ProfileSettingsPanel   from '../components/ProfileSettingsPanel.vue'
import DataSourceNoticePanel  from '../components/DataSourceNoticePanel.vue'

const router    = useRouter()
const authStore = useAuthStore()

// ── Display name ──────────────────────────────────────────────────────────────
const displayName = computed(() => {
  const u = authStore.currentUser
  if (!u) return '已登录用户'
  if (typeof u === 'string' && u && u !== 'string') return u
  if (u?.username && u.username !== 'string') return u.username
  if (u?.email) return u.email
  return '已登录用户'
})

const avatarChar = computed(() => (displayName.value[0] || '我').toUpperCase())

// ── Settings ──────────────────────────────────────────────────────────────────
const settings = ref(getSettings())

function onSettingsPatch(patch) {
  settings.value = saveSettings(patch)
}

function handleResetSettings() {
  resetSettings()
  settings.value = getSettings()
}

function _onSettingsEvent() {
  settings.value = getSettings()
}
onMounted(() => window.addEventListener(SETTINGS_EVENT, _onSettingsEvent))
onUnmounted(() => window.removeEventListener(SETTINGS_EVENT, _onSettingsEvent))

// ── Recent searches ───────────────────────────────────────────────────────────
const recentSearches = ref(getRecentSearches())

function handleClearSearches() {
  clearRecentSearches()
  recentSearches.value = []
}

// ── Stats ─────────────────────────────────────────────────────────────────────
const statsLoading = ref(true)
const stats = ref({
  watchlistCount:       null,
  reportTotal:          null,
  autoSavedCount:       null,
  uniqueStocksAnalyzed: null,
})

async function loadStats() {
  statsLoading.value = true
  try {
    const [watchRes, rptAllRes, rptAutoRes] = await Promise.allSettled([
      listWatchlist(),
      listReports({ limit: 50, offset: 0 }),
      listReports({ auto_saved: true, limit: 50, offset: 0 }),
    ])

    if (watchRes.status === 'fulfilled') {
      stats.value.watchlistCount = watchRes.value.total ?? (watchRes.value.items?.length ?? 0)
    }

    if (rptAllRes.status === 'fulfilled') {
      const d = rptAllRes.value
      stats.value.reportTotal = d.total ?? d.items?.length ?? 0
      const pairs = new Set((d.items || []).map(r => `${r.market}/${r.symbol}`))
      stats.value.uniqueStocksAnalyzed = pairs.size
    }

    if (rptAutoRes.status === 'fulfilled') {
      const d = rptAutoRes.value
      stats.value.autoSavedCount = d.total ?? d.items?.length ?? 0
    }
  } finally {
    statsLoading.value = false
  }
}

// ── Recent reports ────────────────────────────────────────────────────────────
const reportsLoading = ref(true)
const recentReports  = ref([])

async function loadRecentReports() {
  reportsLoading.value = true
  try {
    const d = await listReports({ limit: 5, offset: 0 })
    recentReports.value = d.items || []
  } catch {
    recentReports.value = []
  } finally {
    reportsLoading.value = false
  }
}

// ── Auth ──────────────────────────────────────────────────────────────────────
function handleLogout() {
  authStore.logout()
  router.push('/')
}

onMounted(async () => {
  await Promise.all([loadStats(), loadRecentReports()])
})
</script>

<style scoped>
/* ── Title bar ── */
.pv-title-bar { margin-bottom: 16px; }

.pv-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 4px;
}

.pv-subtitle {
  font-size: 13px;
  color: var(--muted);
  margin: 0;
}

/* ── Hero ── */
.pv-hero {
  display: flex;
  align-items: center;
  gap: 16px;
}

.pv-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent), var(--accent2, #7c5cfc));
  color: #fff;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.pv-user-info { flex: 1; }

.pv-username {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 4px;
}

.pv-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
}

.pv-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--success);
}

.pv-status-text { font-size: 12px; }

.pv-logout-btn {
  background: var(--status-up-bg);
  color: var(--danger);
  border: 1px solid var(--status-up-ring);
  flex-shrink: 0;
}

.pv-logout-btn:hover { background: var(--status-up-ring); }

/* ── Section wrapper ── */
.pv-section { padding: 16px 20px; }

/* ── System actions ── */
.pv-actions-section { padding: 16px 20px; }

.pv-section-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 12px;
}

.pv-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .pv-title { font-size: 18px; }
  .pv-subtitle { font-size: 12px; }
  .pv-hero { flex-wrap: wrap; }
  .pv-actions { flex-direction: column; }
  .pv-actions .btn { width: 100%; }
}
</style>
