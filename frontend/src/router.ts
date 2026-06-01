import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'

const routes = [
  { path: '/login', name: 'Login', component: () => import('./views/Login.vue') },
  { path: '/register', name: 'Register', component: () => import('./views/Register.vue') },
  {
    path: '/',
    component: () => import('./views/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'Dashboard', component: () => import('./views/Dashboard.vue') },
      { path: 'btc', name: 'BtcTrade', component: () => import('./views/BtcTrade.vue') },
      { path: 'sports', name: 'SportsTrade', component: () => import('./views/SportsTrade.vue') },
      { path: 'hot', name: 'HotScan', component: () => import('./views/HotScan.vue') },
      { path: 'political', name: 'Political', component: () => import('./views/Political.vue') },
      { path: 'arbitrage', name: 'Arbitrage', component: () => import('./views/Arbitrage.vue') },
      { path: 'strategy', name: 'StrategyWatch', component: () => import('./views/StrategyWatch.vue') },
      { path: 'ai', name: 'AIAnalysis', component: () => import('./views/AIAnalysis.vue') },
      { path: 'positions', name: 'Positions', component: () => import('./views/Positions.vue') },
      { path: 'settings', name: 'Settings', component: () => import('./views/Settings.vue') },
      { path: 'admin/users', name: 'AdminUsers', component: () => import('./views/admin/Users.vue'), meta: { admin: true } },
      { path: 'admin/system', name: 'AdminSystem', component: () => import('./views/admin/System.vue'), meta: { admin: true } },
    ],
  },
  // Mobile sub-app at /m
  { path: '/m/login', name: 'MLogin', component: () => import('./views/Login.vue') },
  { path: '/m/register', name: 'MRegister', component: () => import('./views/Register.vue') },
  {
    path: '/m',
    component: () => import('./views/mobile/MobileLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'MHome', component: () => import('./views/mobile/MHome.vue') },
      { path: 'btc', name: 'MBtc', component: () => import('./views/mobile/MBtc.vue') },
      { path: 'sports', name: 'MSports', component: () => import('./views/mobile/MSports.vue') },
      { path: 'positions', name: 'MPositions', component: () => import('./views/mobile/MPositions.vue') },
      { path: 'ai', name: 'MAI', component: () => import('./views/mobile/MAI.vue') },
      { path: 'more', name: 'MMore', component: () => import('./views/mobile/MMore.vue') },
      { path: 'hot', name: 'MHot', component: () => import('./views/mobile/MHot.vue') },
      { path: 'political', name: 'MPolitical', component: () => import('./views/mobile/MPolitical.vue') },
      { path: 'arbitrage', name: 'MArb', component: () => import('./views/mobile/MArb.vue') },
      { path: 'settings', name: 'MSettings', component: () => import('./views/mobile/MSettings.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.token) {
    // Mobile routes redirect to /m/login, desktop to /login
    const isMobile = to.path.startsWith('/m')
    return isMobile ? { name: 'MLogin' } : { name: 'Login' }
  }
  if (to.meta.admin && auth.user?.role !== 'admin') return { name: 'Dashboard' }
})

export default router
