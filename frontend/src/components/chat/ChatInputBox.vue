<template>
  <div class="chat-input-box" :class="{ 'is-sending': isSending }">
    <textarea
      ref="textareaRef"
      v-model="inputVal"
      class="chat-textarea"
      :placeholder="t('chat_input_placeholder')"
      :disabled="isSending"
      rows="1"
      @keydown.enter.exact.prevent="onEnter"
      @keydown.enter.shift.exact="onShiftEnter"
      @input="autoResize"
    ></textarea>
    <button
      class="chat-send-btn"
      :disabled="!canSend"
      @click="onSend"
      :aria-label="t('chat_send')"
    >
      <span v-if="isSending" class="send-spinner">⋯</span>
      <span v-else class="send-icon">↑</span>
    </button>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { useI18n } from '../../utils/i18n.js'

const props = defineProps({
  modelValue: { type: String, default: '' },
  isSending:  { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'send'])

const { t } = useI18n()

const textareaRef = ref(null)

const inputVal = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const canSend = computed(() => inputVal.value.trim().length > 0 && !props.isSending)

function onEnter() {
  if (canSend.value) onSend()
}

function onShiftEnter() {
  // Allow newline — handled by browser default (textarea)
}

function onSend() {
  if (!canSend.value) return
  emit('send', inputVal.value.trim())
  emit('update:modelValue', '')
  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
    }
  })
}

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 140) + 'px'
}

// Public method: focus input
function focus() {
  textareaRef.value?.focus()
}

defineExpose({ focus })
</script>

<style scoped>
.chat-input-box {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  background: var(--surface-card, var(--surface));
  border: 1.5px solid var(--border-soft);
  border-radius: 18px;
  padding: 8px 8px 8px 16px;
  box-shadow: var(--shadow-card);
  transition: border-color var(--motion-fast), box-shadow var(--motion-fast);
}

.chat-input-box:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}

.chat-textarea {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  resize: none;
  font-size: 14px;
  color: var(--text);
  line-height: 1.5;
  min-height: 24px;
  max-height: 140px;
  overflow-y: auto;
  font-family: inherit;
  caret-color: var(--accent);
}

.chat-textarea::placeholder { color: var(--muted); }
.chat-textarea:disabled      { opacity: 0.6; }

.chat-send-btn {
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  border: none;
  background: var(--accent-gradient, var(--accent));
  color: white;
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.15s, transform 0.1s;
}

.chat-send-btn:disabled {
  background: var(--surface2);
  color: var(--muted);
  cursor: not-allowed;
}

.chat-send-btn:not(:disabled):hover  { opacity: 0.85; }
.chat-send-btn:not(:disabled):active { transform: scale(0.95); }

.send-spinner { animation: spin-dots 1s infinite; }
.send-icon    { font-weight: 700; margin-top: -1px; }

@keyframes spin-dots { 0%,100%{opacity:1} 50%{opacity:0.3} }

@media (max-width: 640px) {
  .chat-send-btn { width: 44px; height: 44px; }
}
</style>
