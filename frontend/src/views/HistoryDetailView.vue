<template>
  <div class="app-shell">
    <AppHeader />

    <!-- C29.2.4: "返回聊天" banner when navigated from chat copilot -->
    <div v-if="fromChat" class="back-to-chat-bar">
      <button class="btn-back-chat" @click="router.push('/chat')">← 返回聊天</button>
    </div>

    <!-- ── Report header ────────────────────────────────────────────────────── -->
    <ReportDetailHeader
      :report="result"
      :loading="loading"
      @back="handleBack"
      @go-stock="goStock"
      @reanalyze="goReanalyze"
      @delete="openConfirm"
    />

    <!-- ── Meta summary ─────────────────────────────────────────────────────── -->
    <ReportMetaSummary v-if="result" :report="result" />

    <!-- Error -->
    <ErrorBox :message="errorMsg" />

    <!-- Detail -->
    <template v-if="result">
      <AnalysisResultLayout :result="result">
        <template #actions>
          <DownloadMenu :result="result" />

          <button
            class="btn btn-sm btn-danger"
            :disabled="deleting"
            @click="openConfirm"
          >
            <span v-if="deleting" class="spinner"></span>
            删除报告
          </button>
        </template>
      </AnalysisResultLayout>
    </template>
  </div>

  <ConfirmDialog
    v-model="confirmOpen"
    title="删除报告"
    message="确认删除此报告？此操作不可恢复。"
    confirm-text="删除"
    cancel-text="取消"
    :danger="true"
    :loading="deleting"
    @confirm="doDelete"
  />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getReport, deleteReport } from '../api/reports.js'
import AppHeader            from '../components/AppHeader.vue'
import ErrorBox             from '../components/ErrorBox.vue'
import ConfirmDialog        from '../components/ConfirmDialog.vue'
import DownloadMenu         from '../components/DownloadMenu.vue'
import AnalysisResultLayout from '../components/AnalysisResultLayout.vue'
import ReportDetailHeader   from '../components/ReportDetailHeader.vue'
import ReportMetaSummary    from '../components/ReportMetaSummary.vue'

const route  = useRoute()
const router = useRouter()

// C29.2.4: detect navigation from chat copilot
const fromChat = computed(() => route.query.from === 'chat')
function handleBack() {
  router.push(fromChat.value ? '/chat' : '/history')
}

const loading     = ref(false)
const errorMsg    = ref('')
const result      = ref(null)
const deleting    = ref(false)
const confirmOpen = ref(false)

async function loadDetail() {
  loading.value  = true
  errorMsg.value = ''
  try {
    result.value = await getReport(route.params.id)
  } catch (e) {
    errorMsg.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openConfirm() {
  confirmOpen.value = true
}

async function doDelete() {
  deleting.value = true
  try {
    await deleteReport(route.params.id)
    confirmOpen.value = false
    router.push('/history')
  } catch (e) {
    errorMsg.value = e.message || '删除失败'
    confirmOpen.value = false
    deleting.value = false
  }
}

function goStock() {
  if (!result.value?.market || !result.value?.symbol) return
  router.push(`/stocks/${result.value.market}/${result.value.symbol}`)
}

function goReanalyze() {
  if (!result.value?.market || !result.value?.symbol) return
  const q = {
    market: result.value.market,
    symbol: result.value.symbol,
  }
  if (result.value.analysis_scope) q.scope = result.value.analysis_scope
  router.push({ path: '/', query: q })
}

onMounted(loadDetail)
</script>

<style scoped>
/* C29.2.4: back-to-chat banner */
.back-to-chat-bar {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  background: var(--status-info-bg);
  border-bottom: 1px solid var(--border-soft);
}
.btn-back-chat {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  padding: 4px 0;
}
.btn-back-chat:hover { text-decoration: underline; }

.btn-danger {
  background: var(--status-up-bg);
  color: var(--danger);
  border: 1px solid var(--status-up-ring);
}

.btn-danger:hover:not(:disabled) {
  background: var(--status-up-ring);
}
</style>
