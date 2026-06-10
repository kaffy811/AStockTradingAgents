<template>
  <div :class="['empty-state', compact ? 'empty-state--compact' : '']">
    <span class="es-icon">{{ icon }}</span>
    <div class="es-body">
      <p class="es-title">{{ title }}</p>
      <p v-if="message" class="es-message">{{ message }}</p>
      <button
        v-if="actionText"
        class="btn btn-secondary btn-sm es-action"
        @click="$emit('action')"
      >
        {{ actionText }}
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title:      { type: String,  required: true },
  message:    { type: String,  default: ''    },
  icon:       { type: String,  default: 'ℹ️'  },
  actionText: { type: String,  default: ''    },
  compact:    { type: Boolean, default: false },
})

defineEmits(['action'])
</script>

<style scoped>
.empty-state {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 16px 0;
}

.empty-state--compact {
  padding: 10px 0;
}

.es-icon {
  font-size: 18px;
  flex-shrink: 0;
  line-height: 1.4;
}

.empty-state--compact .es-icon {
  font-size: 15px;
}

.es-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.es-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
  line-height: 1.4;
}

.empty-state--compact .es-title {
  font-size: 12px;
}

.es-message {
  font-size: 12px;
  color: var(--muted);
  margin: 0;
  line-height: 1.6;
  word-break: break-word;
}

.es-action {
  margin-top: 6px;
  align-self: flex-start;
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .empty-state { gap: 8px; }
  .es-icon     { font-size: 16px; }
}
</style>
