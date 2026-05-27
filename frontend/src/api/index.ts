import axios from 'axios'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

api.interceptors.response.use(
  (resp) => resp,
  (err) => {
    const msg = err.response?.data?.detail || err.message
    ElMessage.error(msg)
    if (err.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
    }
    return Promise.reject(err)
  }
)

export default api

// Auth
export const authApi = {
  register: (data: { username: string; password: string }) => api.post('/auth/register', data),
  login: (data: { username: string; password: string }) => api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
  changePassword: (data: { old_password: string; new_password: string }) => api.post('/auth/change-password', data),
}

// Admin
export const adminApi = {
  getUsers: (status?: string) => api.get('/admin/users', { params: { status } }),
  approve: (id: number) => api.post(`/admin/users/${id}/approve`),
  reject: (id: number) => api.post(`/admin/users/${id}/reject`),
  deleteUser: (id: number) => api.delete(`/admin/users/${id}`),
  changePassword: (id: number, data: { new_password: string }) => api.post(`/admin/users/${id}/change-password`, data),
  restart: () => api.post('/admin/restart'),
  getAIConfigs: () => api.get('/admin/ai-configs'),
  createAIConfig: (data: any) => api.post('/admin/ai-configs', data),
  updateAIConfig: (id: number, data: any) => api.put(`/admin/ai-configs/${id}`, data),
  deleteAIConfig: (id: number) => api.delete(`/admin/ai-configs/${id}`),
}

// Wallet
export const walletApi = {
  setup: (data: { private_key: string; funder_address: string; chain_id?: number }) => api.post('/wallet/setup', data),
  list: () => api.get('/wallet/list'),
  deactivate: (id: number) => api.post(`/wallet/${id}/deactivate`),
  activate: (id: number) => api.post(`/wallet/${id}/activate`),
  delete: (id: number) => api.delete(`/wallet/${id}`),
}

// BTC
export const btcApi = {
  markets: () => api.get('/btc/markets'),
  market: (slug: string) => api.get(`/btc/market/${slug}`),
  order: (data: any) => api.post('/btc/order', data),
  marketOrder: (data: any) => api.post('/btc/market-order', data),
  sell: (data: any) => api.post('/btc/sell', data),
  positions: () => api.get('/btc/positions'),
  orders: () => api.get('/btc/orders'),
  cancel: (id: string) => api.delete(`/btc/order/${id}`),
  cancelAll: () => api.post('/btc/cancel-all'),
}

// Sports
export const sportsApi = {
  events: () => api.get('/sports/events'),
  event: (slug: string) => api.get(`/sports/event/${slug}`),
  predict: (ai_config_id: number, slug: string) => api.post('/sports/predict', null, { params: { ai_config_id, slug } }),
  order: (data: any) => api.post('/sports/order', data),
}

// Hot
export const hotApi = {
  scan: (hours?: number, minVolume?: number) => api.get('/hot/scan', { params: { hours, min_volume: minVolume } }),
  results: () => api.get('/hot/results'),
  sports: () => api.get('/hot/sports'),
  order: (data: any) => api.post('/hot/order', data),
}

// Political
export const politicalApi = {
  scan: () => api.get('/political/scan'),
  results: () => api.get('/political/results'),
  order: (data: any) => api.post('/political/order', data),
}

// Arbitrage
export const arbitrageApi = {
  scan: (threshold?: number) => api.get('/arbitrage/scan', { params: { threshold } }),
  results: () => api.get('/arbitrage/results'),
  execute: (data: any) => api.post('/arbitrage/execute', null, { params: data }),
}

// AI
export const aiApi = {
  providers: () => api.get('/ai/providers'),
  analyze: (data: any) => api.post('/ai/analyze', data),
  analyzeMarket: (data: any) => api.post('/ai/analyze-market', data),
  analyzeArbitrage: (params: any) => api.post('/ai/analyze-arbitrage', null, { params }),
}

// Notify
export const notifyApi = {
  getConfig: () => api.get('/notify/config'),
  saveConfig: (data: any) => api.post('/notify/config', data),
  deleteConfig: (id: number) => api.delete(`/notify/config/${id}`),
  test: (data: any) => api.post('/notify/test', data),
}
