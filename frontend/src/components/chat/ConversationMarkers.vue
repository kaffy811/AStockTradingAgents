<template>
  <!-- C32.3: Conversation marker rail — only shown when ≥3 user messages, desktop only -->
  <div
    v-if="userMessages.length >= 3"
    class="conv-markers-rail"
    aria-hidden="true"
  >
    <!-- Track line -->
    <div class="conv-markers-track"></div>

    <!-- One marker per user message -->
    <div
      v-for="marker in markers"
      :key="marker.msgId"
      class="conv-marker"
      :class="{ 'conv-marker--active': marker.isActive }"
      :style="{ top: marker.topPercent + '%' }"
      @mouseenter="hoveredId = marker.msgId"
      @mouseleave="hoveredId = null"
      @click="scrollToMessage(marker.msgId)"
      :title="t('chat_markers_jump')"
    >
      <div class="conv-marker-tick"></div>

      <!-- Hover preview card -->
      <Transition name="marker-tip">
        <div v-if="hoveredId === marker.msgId" class="conv-marker-tooltip">
          <span class="conv-marker-preview">{{ marker.preview }}</span>
          <span class="conv-marker-time">{{ marker.time }}</span>
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useI18n } from '../../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  /** Full messages array (user + assistant) */
  messages: { type: Array, default: () => [] },
  /** The scrollable HTMLElement (the .message-list div) */
  scrollContainer: { type: Object, default: null },
})

// ── State ──────────────────────────────────────────────────────────────────

const hoveredId      = ref(null)
const highlightedId  = ref(null)
const markerPositions = ref({})   // msgId → topPercent (0-100)
const scrollTop      = ref(0)
const scrollHeight   = ref(1)
const clientHeight   = ref(1)

// ── Computed ───────────────────────────────────────────────────────────────

const userMessages = computed(() =>
  props.messages.filter(m => m.role === 'user')
)

const markers = computed(() =>
  userMessages.value.map(msg => {
    const topPercent = markerPositions.value[msg.id] ?? 0
    // Determine if this message is in the current viewport
    const pxFromTop = (topPercent / 100) * scrollHeight.value
    const isActive = pxFromTop >= scrollTop.value &&
                     pxFromTop <= scrollTop.value + clientHeight.value

    const preview = (msg.content || '').slice(0, 15) +
                    (msg.content?.length > 15 ? '…' : '')

    let time = ''
    if (msg.created_at) {
      try {
        const d = new Date(msg.created_at)
        time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
      } catch { /* noop */ }
    }

    return { msgId: msg.id, topPercent, isActive, preview, time }
  })
)

// ── Position calculation ───────────────────────────────────────────────────

function recalcPositions() {
  const container = props.scrollContainer
  if (!container) return

  const sh = container.scrollHeight || 1
  scrollHeight.value = sh
  clientHeight.value = container.clientHeight || 1

  // C32.3: Use getBoundingClientRect for accurate position calculation.
  // el.offsetTop is relative to the nearest positioned ancestor, which may
  // not be the scroll container when .message-list has no position CSS.
  const containerRect = container.getBoundingClientRect()
  const newPositions = {}
  for (const msg of userMessages.value) {
    const el = container.querySelector(`[data-message-id="${msg.id}"]`)
    if (el) {
      const elRect = el.getBoundingClientRect()
      // Position relative to container top + account for current scroll
      const offsetTop = elRect.top - containerRect.top + container.scrollTop
      newPositions[msg.id] = Math.min(99, Math.max(0, (offsetTop / sh) * 100))
    }
  }
  markerPositions.value = newPositions
}

function onScroll() {
  const container = props.scrollContainer
  if (!container) return
  scrollTop.value = container.scrollTop
}

// ── Scroll to message ──────────────────────────────────────────────────────

function scrollToMessage(msgId) {
  const container = props.scrollContainer
  if (!container) return

  const el = container.querySelector(`[data-message-id="${msgId}"]`)
  if (!el) return

  // Smooth scroll
  el.scrollIntoView({ behavior: 'smooth', block: 'start' })

  // Highlight for 1.5s
  highlightedId.value = msgId
  setTimeout(() => {
    if (highlightedId.value === msgId) highlightedId.value = null
  }, 1500)
}

// ── Watch & resize ─────────────────────────────────────────────────────────

let _ro = null
let _scrollListener = null

function _attach() {
  const container = props.scrollContainer
  if (!container) return

  // Scroll listener
  _scrollListener = () => { scrollTop.value = container.scrollTop }
  container.addEventListener('scroll', _scrollListener, { passive: true })

  // ResizeObserver to recalc on size changes
  if (typeof ResizeObserver !== 'undefined') {
    _ro = new ResizeObserver(() => nextTick(recalcPositions))
    _ro.observe(container)
  }

  nextTick(recalcPositions)
}

function _detach() {
  const container = props.scrollContainer
  if (container && _scrollListener) {
    container.removeEventListener('scroll', _scrollListener)
    _scrollListener = null
  }
  _ro?.disconnect()
  _ro = null
}

watch(() => props.scrollContainer, (newVal, oldVal) => {
  if (oldVal) _detach()
  if (newVal) _attach()
}, { immediate: false })

watch(() => props.messages, () => nextTick(recalcPositions), { deep: false, flush: 'post' })

onMounted(() => {
  if (props.scrollContainer) _attach()
})

onBeforeUnmount(() => {
  _detach()
})

// ── Expose highlight state for ChatMessageList ─────────────────────────────
defineExpose({ highlightedId })
</script>

<style scoped>
/* C32.3: Conversation marker rail — fixed overlay on right side */
.conv-markers-rail {
  position: absolute;
  top: 0;
  right: 0;
  width: 16px;
  height: 100%;
  pointer-events: none;
  z-index: 10;
}

.conv-markers-track {
  position: absolute;
  top: 8px;
  bottom: 8px;
  left: 7px;
  width: 2px;
  background: var(--border-soft);
  border-radius: 1px;
}

.conv-marker {
  position: absolute;
  right: 0;
  transform: translateY(-50%);
  width: 16px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  pointer-events: all;
}

.conv-marker-tick {
  width: 8px;
  height: 3px;
  background: var(--muted);
  border-radius: 2px;
  transition: background 0.15s, width 0.15s;
}

.conv-marker:hover .conv-marker-tick,
.conv-marker--active .conv-marker-tick {
  background: var(--accent);
  width: 10px;
}

/* Tooltip card */
.conv-marker-tooltip {
  position: absolute;
  right: 20px;
  top: 50%;
  transform: translateY(-50%);
  background: var(--surface-card, var(--surface));
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  padding: 4px 8px;
  white-space: nowrap;
  box-shadow: var(--shadow-card);
  display: flex;
  flex-direction: column;
  gap: 2px;
  pointer-events: none;
  z-index: 100;
}

.conv-marker-preview {
  font-size: 11px;
  color: var(--text);
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-marker-time {
  font-size: 10px;
  color: var(--muted);
}

/* Tooltip transition */
.marker-tip-enter-active,
.marker-tip-leave-active {
  transition: opacity 0.12s, transform 0.12s;
}
.marker-tip-enter-from,
.marker-tip-leave-to {
  opacity: 0;
  transform: translateY(-50%) translateX(4px);
}

/* Hide on mobile */
@media (max-width: 640px) {
  .conv-markers-rail {
    display: none;
  }
}
</style>
