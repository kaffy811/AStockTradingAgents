<template>
  <!-- keep-alive preserves ComprehensiveAnalysisView state across navigation -->
  <RouterView v-slot="{ Component }">
    <keep-alive :include="['ComprehensiveAnalysisView']">
      <component :is="Component" />
    </keep-alive>
  </RouterView>
  <!-- BottomTabBar: mobile-only, shown only when authenticated -->
  <BottomTabBar v-if="authStore.token" />
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useAuthStore } from './stores/auth.js'
import BottomTabBar from './components/BottomTabBar.vue'
import { applyTheme } from './utils/theme.js'
import { setLocale } from './utils/i18n.js'
import { SETTINGS_EVENT } from './utils/settings.js'

const authStore = useAuthStore()

function onSettingsUpdate(e) {
  if (e.detail?.theme)    applyTheme(e.detail.theme)
  if (e.detail?.language) setLocale(e.detail.language)
}

onMounted(()   => window.addEventListener(SETTINGS_EVENT, onSettingsUpdate))
onUnmounted(() => window.removeEventListener(SETTINGS_EVENT, onSettingsUpdate))
</script>
