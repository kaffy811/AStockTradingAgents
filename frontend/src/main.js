import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index.js'
import { applyTheme, getStoredTheme } from './utils/theme.js'
import { setLocale, getStoredLocale } from './utils/i18n.js'

import './styles/variables.css'
import './styles/base.css'
import './styles/markdown.css'
import './styles/print.css'

// Apply stored theme and locale before first paint
applyTheme(getStoredTheme())
setLocale(getStoredLocale())

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
