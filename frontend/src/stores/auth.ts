import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '../api'

interface User {
  id: number
  username: string
  role: string
  status: string
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('polytrad_token') || '')
  const user = ref<User | null>(null)

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function login(username: string, password: string) {
    const { data } = await authApi.login({ username, password })
    token.value = data.access_token
    localStorage.setItem('polytrad_token', data.access_token)
    await fetchUser()
  }

  async function fetchUser() {
    try {
      const { data } = await authApi.me()
      user.value = data
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('polytrad_token')
  }

  return { token, user, isLoggedIn, isAdmin, login, fetchUser, logout }
})
