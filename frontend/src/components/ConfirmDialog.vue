<template>
  <Teleport to="body">
    <div v-if="modelValue" class="cd-overlay" @mousedown.self="onOverlayClick">
      <div class="cd-dialog" role="dialog" aria-modal="true">
        <div class="cd-header">
          <span class="cd-title">{{ title }}</span>
        </div>

        <div class="cd-body">
          <p class="cd-message">{{ message }}</p>
        </div>

        <div class="cd-footer">
          <button
            class="btn btn-secondary btn-sm"
            :disabled="loading"
            @click="onCancel"
          >
            {{ cancelText }}
          </button>
          <button
            :class="['btn', 'btn-sm', danger ? 'btn-danger' : 'btn-primary']"
            :disabled="loading"
            @click="onConfirm"
          >
            <span v-if="loading" class="spinner"></span>
            {{ confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
const props = defineProps({
  modelValue:  { type: Boolean, default: false },
  title:       { type: String,  default: '确认操作' },
  message:     { type: String,  default: '' },
  confirmText: { type: String,  default: '确认' },
  cancelText:  { type: String,  default: '取消' },
  danger:      { type: Boolean, default: false },
  loading:     { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'confirm', 'cancel'])

function onConfirm() {
  if (props.loading) return
  emit('confirm')
}

function onCancel() {
  if (props.loading) return
  emit('cancel')
  emit('update:modelValue', false)
}

function onOverlayClick() {
  if (props.loading) return
  emit('cancel')
  emit('update:modelValue', false)
}
</script>

<style scoped>
.cd-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.cd-dialog {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 24px;
  width: 360px;
  max-width: calc(100vw - 40px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.cd-header {
  margin-bottom: 12px;
}

.cd-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.cd-body {
  margin-bottom: 20px;
}

.cd-message {
  font-size: 13px;
  color: var(--muted);
  line-height: 1.6;
  margin: 0;
}

.cd-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.btn-primary {
  background: var(--accent);
  color: #fff;
  border: 1px solid var(--accent);
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.88;
}

.btn-danger {
  background: var(--status-up-bg);
  color: var(--danger);
  border: 1px solid var(--status-up-ring);
}

.btn-danger:hover:not(:disabled) {
  background: var(--status-up-ring);
}
</style>
