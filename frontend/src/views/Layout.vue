<template>
  <el-container style="height:100vh">
    <el-aside width="220px" style="background:#304156">
      <div class="logo">PolyTrad</div>
      <el-menu :default-active="route.path" router background-color="#304156" text-color="#bfcbd9" active-text-color="#409eff">
        <el-menu-item index="/">
          <el-icon><Odometer /></el-icon><span>总览</span>
        </el-menu-item>
        <el-menu-item index="/btc">
          <el-icon><TrendCharts /></el-icon><span>BTC短周期</span>
        </el-menu-item>
        <el-menu-item index="/sports">
          <el-icon><Football /></el-icon><span>体育赛事</span>
        </el-menu-item>
        <el-menu-item index="/hot">
          <el-icon><Flame /></el-icon><span>热门尾盘</span>
        </el-menu-item>
        <el-menu-item index="/political">
          <el-icon><Flag /></el-icon><span>政治打新</span>
        </el-menu-item>
        <el-menu-item index="/arbitrage">
          <el-icon><Switch /></el-icon><span>事件套利</span>
        </el-menu-item>
        <el-menu-item index="/strategy">
          <el-icon><TrendCharts /></el-icon><span>策略观察</span>
        </el-menu-item>
        <el-menu-item index="/ai">
          <el-icon><MagicStick /></el-icon><span>AI分析</span>
        </el-menu-item>
        <el-menu-item index="/positions">
          <el-icon><Wallet /></el-icon><span>持仓</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon><span>设置</span>
        </el-menu-item>
        <template v-if="auth.isAdmin">
          <el-divider style="border-color:#4a5a6a;margin:8px 16px" />
          <el-menu-item index="/admin/users">
            <el-icon><UserFilled /></el-icon><span>用户管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/system">
            <el-icon><Tools /></el-icon><span>系统管理</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header style="display:flex;align-items:center;justify-content:flex-end;background:#fff;border-bottom:1px solid #e6e6e6">
        <span style="margin-right:16px">{{ auth.user?.username }} ({{ auth.user?.role }})</span>
        <el-button type="danger" size="small" @click="handleLogout">退出</el-button>
      </el-header>
      <el-main style="background:#f5f7fa">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

onMounted(() => {
  if (!auth.user) auth.fetchUser()
})

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.logo { height:60px; display:flex; align-items:center; justify-content:center; color:#fff; font-size:20px; font-weight:bold; letter-spacing:2px; }
</style>
