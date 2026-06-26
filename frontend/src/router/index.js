import { createRouter, createWebHistory } from 'vue-router'
import ComprehensiveAnalysisView from '../views/ComprehensiveAnalysisView.vue'

const routes = [
  {
    path: '/',
    name: 'ComprehensiveAnalysis',
    component: ComprehensiveAnalysisView,
  },
  {
    path: '/history',
    name: 'History',
    component: () => import('../views/HistoryView.vue'),
  },
  {
    path: '/history/:id',
    name: 'HistoryDetail',
    component: () => import('../views/HistoryDetailView.vue'),
  },
  {
    path: '/print/report',
    name: 'PrintReport',
    component: () => import('../views/PrintReportView.vue'),
  },
  { path: '/watchlist',  name: 'Watchlist',    component: () => import('../views/WatchlistView.vue') },
  { path: '/industries', name: 'IndustryHot',  component: () => import('../views/IndustryHotView.vue') },
  {
    path: '/stocks/:market/:symbol',
    name: 'StockDetail',
    component: () => import('../views/StockDetailView.vue'),
  },
  {
    path: '/me',
    name: 'Profile',
    component: () => import('../views/ProfileView.vue'),
  },
  {
    path: '/compare',
    name: 'StockCompare',
    component: () => import('../views/StockCompareView.vue'),
  },
  {
    path: '/chat',
    name: 'ChatCopilot',
    component: () => import('../views/ChatCopilotView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('ta_token')
  const protectedPrefixes = ['/history', '/watchlist', '/industries', '/stocks', '/me', '/compare', '/chat']
  if (!token && protectedPrefixes.some(p => to.path.startsWith(p))) {
    return { path: '/' }
  }
})

export default router
