import { createRouter, createWebHistory } from 'vue-router'
import ComprehensiveAnalysisView from '../views/ComprehensiveAnalysisView.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/RegisterView.vue'),
    meta: { public: true },
  },
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
  {
    path: '/admin/invites',
    name: 'AdminInvites',
    component: () => import('../views/AdminInvitesView.vue'),
    meta: { requiresAdmin: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token   = localStorage.getItem('ta_token')
  const isAdmin = localStorage.getItem('ta_is_admin') === 'true'

  // 已登录用户访问登录/注册页面，回首页
  if (token && to.meta.public) {
    return { path: '/' }
  }

  // 未登录用户只能访问 public 页面
  if (!token && !to.meta.public) {
    return { path: '/login' }
  }

  // 管理员路由：非管理员跳回首页
  if (to.meta.requiresAdmin && !isAdmin) {
    return { path: '/' }
  }
})

export default router
