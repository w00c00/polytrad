<template>
  <div class="m-arb">
    <div class="page-header">
      <button class="back-btn" @click="$router.push('/m/more')">← 返回</button>
      <span class="page-title">事件套利</span>
    </div>
    <div class="list">
      <div v-if="loading" class="empty-hint">扫描中...</div>
      <div v-else-if="opps.length === 0" class="empty-hint">暂无套利机会</div>
      <div v-for="o in opps" :key="o.event_slug" class="card">
        <div class="card-title">{{ o.title_zh || o.title }}</div>
        <div class="card-info">
          <span>偏差: {{ (o.deviation * 100).toFixed(1) }}%</span>
          <span>方向: {{ o.direction }}</span>
        </div>
        <div class="card-info">
          <span>YES 总和: {{ o.yes_sum }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { arbitrageApi } from '../../api'

const loading = ref(false)
const opps = ref<any[]>([])

async function loadData() {
  loading.value = true
  try {
    const { data } = await arbitrageApi.scan()
    opps.value = data || []
  } catch {} finally { loading.value = false }
}

onMounted(loadData)
</script>

<style scoped>
.m-arb { padding: 12px; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.back-btn { background: none; border: none; font-size: 14px; color: #409eff; cursor: pointer; padding: 8px 0; }
.page-title { font-size: 16px; font-weight: bold; }
.list { display: flex; flex-direction: column; gap: 8px; }
.card { background: #fff; border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.card-title { font-size: 14px; font-weight: bold; color: #303133; margin-bottom: 6px; }
.card-info { font-size: 13px; color: #606266; display: flex; gap: 16px; margin-top: 4px; }
.empty-hint { text-align: center; color: #909399; padding: 40px 0; font-size: 14px; }
</style>
