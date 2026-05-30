<template>
  <div class="mobile-shell">
    <!-- Top header -->
    <div class="m-header">
      <span class="m-logo">PolyTrad</span>
      <span class="m-user">{{ auth.user?.username }}</span>
    </div>

    <!-- Page content -->
    <div class="m-content">
      <router-view />
    </div>

    <!-- Bottom tab bar -->
    <div class="m-tabbar">
      <div v-for="tab in tabs" :key="tab.path" class="m-tab" :class="{ active: isActive(tab.path) }" @click="$router.push(tab.path)">
        <span class="m-tab-icon">{{ tab.icon }}</span>
        <span class="m-tab-label">{{ tab.label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../../stores/auth'

const route = useRoute()
const auth = useAuthStore()

const tabs = [
  { path: '/m', icon: ' ', label: '首页' },
  { path: '/m/btc', icon: '₿', label: 'BTC' },
  { path: '/m/sports', icon: ' ', label: '体育' },
  { path: '/m/positions', icon: ' ', label: '持仓' },
  { path: '/m/more', icon: '⋯', label: '更多' },
]

function isActive(path: string) {
  if (path === '/m') return route.path === '/m'
  return route.path.startsWith(path)
}

onMounted(() => {
  if (!auth.user) auth.fetchUser()
})
</script>

<style scoped>
.mobile-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  background: #f5f7fa;
  overflow: hidden;
}

.m-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 16px;
  background: #304156;
  color: #fff;
  flex-shrink: 0;
}

.m-logo {
  font-size: 18px;
  font-weight: bold;
  letter-spacing: 1px;
}

.m-user {
  font-size: 13px;
  color: #bfcbd9;
}

.m-content {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding-bottom: 8px;
}

.m-tabbar {
  display: flex;
  height: 56px;
  background: #fff;
  border-top: 1px solid #e6e6e6;
  flex-shrink: 0;
  padding-bottom: env(safe-area-inset-bottom, 0);
}

.m-tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
  -webkit-tap-highlight-color: transparent;
}

.m-tab.active {
  color: #409eff;
}

.m-tab-icon {
  font-size: 20px;
  line-height: 1;
}

.m-tab-label {
  font-size: 11px;
  line-height: 1;
}
</style>
