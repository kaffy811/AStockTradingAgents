<template>
  <div class="confirm-card" :class="{ 'is-resolved': isResolved }">
    <div class="confirm-icon">
      <span v-if="apiStatus === 'executing'">⏳</span>
      <span v-else-if="apiStatus === 'failed'">✗</span>
      <span v-else-if="apiStatus === 'expired'">⏱</span>
      <span v-else>⚠</span>
    </div>
    <div class="confirm-body">
      <!-- Render simple bold markers from **text** -->
      <p class="confirm-text" v-html="renderText(confirmation.text)"></p>

      <!-- Buttons (only when still pending) -->
      <div v-if="!isResolved" class="confirm-actions">
        <button class="confirm-btn confirm-btn--ok" @click="onConfirm">
          {{ t('chat_confirm') }}
        </button>
        <button class="confirm-btn confirm-btn--cancel" @click="onCancel">
          {{ t('chat_cancel') }}
        </button>
      </div>

      <!-- Executing state -->
      <div v-else-if="apiStatus === 'executing'" class="confirm-resolved">
        <span class="is-executing">⏳ {{ t('chat_executing') }}</span>
      </div>

      <!-- Failed state -->
      <div v-else-if="apiStatus === 'failed'" class="confirm-resolved">
        <span class="is-failed">✗ {{ t('chat_failed') }}</span>
      </div>

      <!-- Expired state -->
      <div v-else-if="apiStatus === 'expired'" class="confirm-resolved">
        <span class="is-expired">⏱ {{ t('chat_expired') }}</span>
      </div>

      <!-- Confirmed / executed state -->
      <div v-else-if="resolvedAction === 'confirmed' || apiStatus === 'executed'" class="confirm-resolved">
        <span class="is-confirmed">✓ {{ t('chat_confirmed') }}</span>
      </div>

      <!-- Cancelled state -->
      <div v-else class="confirm-resolved">
        <span class="is-cancelled">✗ {{ t('chat_cancelled') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from '../../utils/i18n.js'

const props = defineProps({
  confirmation: { type: Object, required: true },
})

const emit = defineEmits(['confirm', 'cancel'])

const { t } = useI18n()

// Local click state — prevents duplicate clicks before API responds
const resolved       = ref(false)
const resolvedAction = ref('')

// Status from the API (written back to confirmation.status by parent)
const apiStatus = computed(() => props.confirmation?.status ?? 'pending')

// Card is resolved if the user already clicked OR if the API updated status
const isResolved = computed(() =>
  resolved.value ||
  ['executing', 'executed', 'confirmed', 'cancelled', 'failed', 'expired'].includes(apiStatus.value)
)

function renderText(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}

function onConfirm() {
  if (isResolved.value) return
  resolved.value       = true
  resolvedAction.value = 'confirmed'
  emit('confirm', props.confirmation)
}

function onCancel() {
  if (isResolved.value) return
  resolved.value       = true
  resolvedAction.value = 'cancelled'
  emit('cancel', props.confirmation)
}
</script>

<style scoped>
.confirm-card {
  margin-top: 10px;
  display: flex;
  gap: 10px;
  background: var(--status-warn-bg);
  border: 1px solid var(--status-warn-ring);
  border-radius: var(--radius-card);
  padding: 12px 14px;
  transition: opacity 0.2s;
}
.confirm-card.is-resolved { opacity: 0.7; }

.confirm-icon {
  font-size: 18px;
  flex-shrink: 0;
  color: var(--warn);
  margin-top: 1px;
}

.confirm-body { flex: 1; }

.confirm-text {
  font-size: 13px;
  color: var(--text);
  line-height: 1.5;
  margin-bottom: 10px;
}

.confirm-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.confirm-btn {
  font-size: 13px;
  font-weight: 600;
  padding: 6px 18px;
  border-radius: var(--radius-control);
  cursor: pointer;
  border: none;
  transition: opacity 0.15s, transform 0.1s;
}
.confirm-btn:active { transform: scale(0.97); }

.confirm-btn--ok {
  background: var(--accent-gradient, var(--accent));
  color: white;
}
.confirm-btn--ok:hover { opacity: 0.88; }

.confirm-btn--cancel {
  background: var(--surface2);
  color: var(--text-secondary);
  border: 1px solid var(--border-soft);
}
.confirm-btn--cancel:hover { background: var(--surface-hover); }

.confirm-resolved {
  font-size: 13px;
  font-weight: 600;
}
.is-confirmed { color: var(--success); }
.is-cancelled { color: var(--muted); }
.is-executing { color: var(--accent); }
.is-failed    { color: var(--danger, #e53e3e); }
.is-expired   { color: var(--muted); }
</style>
