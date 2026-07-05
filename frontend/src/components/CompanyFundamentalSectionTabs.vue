<template>
  <div class="cfst-root">
    <div class="cfst-tabs">
      <button
        v-for="s in sections"
        :key="s.key"
        :class="['cfst-btn', active === s.key && 'active']"
        @click="$emit('change', s.key)"
      >{{ s.label }}</button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  sections: { type: Array, default: () => [] },
  active: { type: String, default: '' },
})
defineEmits(['change'])
</script>

<style scoped>
.cfst-root {
  background: white;
  border-radius: 10px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
  overflow: hidden;
}
.cfst-tabs {
  display: flex;
  overflow-x: auto;
  scrollbar-width: none;
  border-bottom: 2px solid var(--border, #e8eaed);
}
.cfst-tabs::-webkit-scrollbar { display: none; }
.cfst-btn {
  flex-shrink: 0;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  padding: 10px 18px;
  font-size: 13px;
  font-weight: 500;
  color: var(--muted);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}
.cfst-btn:hover { color: var(--text); }
.cfst-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  font-weight: 600;
}
</style>
