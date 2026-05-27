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
      { path: 'ai', name: 'AIAnalysis', component: () => import('./views/AIAnalysis.vue') },
      { path: 'positions', name: 'Positions', component: () => import('./views/Positions.vue') },
      { path: 'settings', name: 'Settings', component: () => import('./views/Settings.vue') },
      { path: 'admin/users', name: 'AdminUsers', component: () => import('./views/admin/Users.vue'), meta: { admin: true } },
      { path: 'admin/system', name: 'AdminSystem', component: () => import('./views/admin/System.vue'), meta: { admin: true } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.token) return { name: 'Login' }
  if (to.meta.admin && auth.user?.role !== 'admin') return { name: 'Dashboard' }
})

export default router
