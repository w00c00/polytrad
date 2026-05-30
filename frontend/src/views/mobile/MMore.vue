<template>
  <div class="m-more">
    <div class="m-card">
      <div class="card-title">更多功能</div>
      <div class="menu-list">
        <div class="menu-item" @click="$router.push('/m/hot')">
          <span class="menu-icon"> </span>
          <span class="menu-label">热门尾盘</span>
          <span class="menu-arrow">›</span>
        </div>
        <div class="menu-item" @click="$router.push('/m/political')">
          <span class="menu-icon"> </span>
          <span class="menu-label">政治打新</span>
          <span class="menu-arrow">›</span>
        </div>
        <div class="menu-item" @click="$router.push('/m/arbitrage')">
          <span class="menu-icon">⚖️</span>
          <span class="menu-label">事件套利</span>
          <span class="menu-arrow">›</span>
        </div>
        <div class="menu-item" @click="$router.push('/m/settings')">
          <span class="menu-icon">⚙️</span>
          <span class="menu-label">设置</span>
          <span class="menu-arrow">›</span>
        </div>
      </div>
    </div>

    <div class="m-card">
      <div class="menu-list">
        <div class="menu-item" @click="openDesktop">
          <span class="menu-icon"> </span>
          <span class="menu-label">桌面版</span>
          <span class="menu-arrow">›</span>
        </div>
        <div class="menu-item danger" @click="handleLogout">
          <span class="menu-icon"> </span>
          <span class="menu-label">退出登录</span>
          <span class="menu-arrow">›</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'

const router = useRouter()
const auth = useAuthStore()

function openDesktop() {
  window.location.href = '/'
}

function handleLogout() {
  auth.logout()
  router.push('/m/login')
}
</script>

<style scoped>
.m-more { padding: 12px; display: flex; flex-direction: column; gap: 12px; }

.m-card {
  background: #fff;
  border-radius: 12px;
  padding: 4px 0;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.card-title { font-size: 15px; font-weight: bold; color: #303133; padding: 14px 16px 10px; }

.menu-list { display: flex; flex-direction: column; }

.menu-item {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  border-bottom: 1px solid #f5f5f5;
}

.menu-item:last-child { border-bottom: none; }
.menu-item:active { background: #f5f7fa; }
.menu-item.danger .menu-label { color: #f56c6c; }

.menu-icon { font-size: 20px; margin-right: 12px; width: 28px; text-align: center; }
.menu-label { flex: 1; font-size: 15px; color: #303133; }
.menu-arrow { font-size: 18px; color: #c0c4cc; }
</style>
