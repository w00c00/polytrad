<template>
  <div class="m-settings">
    <div class="page-header">
      <button class="back-btn" @click="$router.push('/m/more')">← 返回</button>
      <span class="page-title">设置</span>
    </div>
    <div class="m-card">
      <div class="menu-list">
        <div class="menu-item" @click="goDesktop('/settings')">
          <span class="menu-label">钱包配置</span>
          <span class="menu-arrow">›</span>
        </div>
        <div class="menu-item" @click="goDesktop('/settings')">
          <span class="menu-label">通知设置</span>
          <span class="menu-arrow">›</span>
        </div>
        <div class="menu-item" @click="goDesktop('/settings')">
          <span class="menu-label">修改密码</span>
          <span class="menu-arrow">›</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
function goDesktop(path: string) {
  window.location.href = path
}
</script>

<style scoped>
.m-settings { padding: 12px; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.back-btn { background: none; border: none; font-size: 14px; color: #409eff; cursor: pointer; padding: 8px 0; }
.page-title { font-size: 16px; font-weight: bold; }
.m-card { background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.menu-list { display: flex; flex-direction: column; }
.menu-item { display: flex; align-items: center; padding: 14px 16px; cursor: pointer; border-bottom: 1px solid #f5f5f5; }
.menu-item:last-child { border-bottom: none; }
.menu-item:active { background: #f5f7fa; }
.menu-label { flex: 1; font-size: 15px; color: #303133; }
.menu-arrow { font-size: 18px; color: #c0c4cc; }
</style>
