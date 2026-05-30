<template>
  <div class="m-opps">
    <div class="page-header">
      <button class="back-btn" @click="$router.push('/m/more')">← 返回</button>
      <span class="page-title">机会中心</span>
    </div>

    <div class="seg-tabs">
      <button v-for="t in tabs" :key="t.key" class="seg-tab" :class="{ active: tab === t.key }" @click="switchTab(t.key)">{{ t.label }}</button>
    </div>

    <div v-if="loading" class="empty-hint">扫描中...</div>
    <div v-else-if="items.length === 0" class="empty-hint">暂无机会</div>

    <div v-else class="list">
      <div v-for="(item, idx) in items" :key="item.event_slug || item.slug || item.topic || idx" class="card">
        <template v-if="tab === 'basket'">
          <div class="card-title">{{ item.title_zh || item.title }}</div>
          <div class="card-info">
            <span>偏差 {{ (item.deviation * 100).toFixed(1) }}%</span>
            <span>{{ item.direction }}</span>
            <span>{{ item.executable ? '可执行' : '观察' }}</span>
          </div>
          <div class="card-note">{{ item.execution_note }}</div>
        </template>

        <template v-else-if="tab === 'slippage'">
          <div class="card-title">{{ item.title_zh || item.title }}</div>
          <div class="card-info">
            <span>{{ item.direction }}</span>
            <span>均价 ${{ item.depth.avg_price.toFixed(4) }}</span>
            <span>滑点 {{ item.depth.slippage_pct.toFixed(2) }}%</span>
          </div>
          <div class="card-note">可买 {{ item.depth.shares.toFixed(2) }} 份，24h量 ${{ Math.round(item.volume_24h).toLocaleString() }}</div>
        </template>

        <template v-else-if="tab === 'cross'">
          <div class="card-title">{{ item.topic_zh || item.topic }}</div>
          <div class="card-info">
            <span>价差 {{ (item.spread * 100).toFixed(1) }}%</span>
          </div>
          <div class="card-note">低价: {{ item.buy_candidate?.question_zh }}</div>
          <div class="card-note">高价: {{ item.sell_reference?.question_zh }}</div>
        </template>

        <template v-else-if="tab === 'rewards'">
          <div class="card-title">{{ item.question_zh || item.question }}</div>
          <div class="card-info">
            <span>点差 {{ (item.spread * 100).toFixed(2) }}%</span>
            <span>{{ item.fit ? '达标' : '偏宽' }}</span>
          </div>
          <div class="card-note">奖励要求 {{ item.rewards_min_size }}份 / {{ (item.rewards_max_spread * 100).toFixed(2) }}%</div>
        </template>

        <template v-else-if="tab === 'resolution'">
          <div class="card-title">{{ item.question_zh || item.question }}</div>
          <div class="card-info">
            <span>YES ${{ item.yes_price.toFixed(3) }}</span>
            <span>{{ item.hours_left ?? '-' }}h</span>
            <span>{{ item.uma_status }}</span>
          </div>
          <div class="card-note">结束 {{ item.end_date_bj || '-' }}</div>
        </template>

        <template v-else-if="tab === 'btc'">
          <div class="card-title">{{ item.title_zh || item.title }}</div>
          <div class="card-info">
            <span>{{ item.series_label }}</span>
            <span>{{ item.action }}</span>
            <span>Edge {{ (item.edge * 100).toFixed(1) }}%</span>
          </div>
          <div class="card-note">UP 概率 {{ (item.signal.prob_up * 100).toFixed(1) }}%，截止 {{ item.end_time_bj || '-' }}</div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { arbitrageApi, opportunityApi } from '../../api'

const tab = ref('basket')
const loading = ref(false)
const dataMap = ref<Record<string, any[]>>({})

const tabs = [
  { key: 'basket', label: '篮子' },
  { key: 'slippage', label: '滑点' },
  { key: 'cross', label: '价差' },
  { key: 'rewards', label: '做市' },
  { key: 'resolution', label: '结算' },
  { key: 'btc', label: 'BTC' },
]

const items = computed(() => dataMap.value[tab.value] || [])

async function switchTab(key: string) {
  tab.value = key
  if (!dataMap.value[key]) await loadData()
}

async function loadData() {
  loading.value = true
  try {
    let data: any[] = []
    if (tab.value === 'basket') {
      const resp = await arbitrageApi.scan(0.03)
      data = resp.data || []
    } else if (tab.value === 'slippage') {
      const resp = await opportunityApi.slippage({ amount: 10, max_slippage_pct: 5, min_volume_24h: 1000, max_candidates: 60 })
      data = resp.data || []
    } else if (tab.value === 'cross') {
      const resp = await opportunityApi.crossEvent({ min_spread: 0.05, max_candidates: 120 })
      data = resp.data || []
    } else if (tab.value === 'rewards') {
      const resp = await opportunityApi.rewards({ max_candidates: 120 })
      data = resp.data || []
    } else if (tab.value === 'resolution') {
      const resp = await opportunityApi.resolutionWatch({ hours: 12, min_volume_24h: 1000 })
      data = resp.data || []
    } else if (tab.value === 'btc') {
      const resp = await opportunityApi.btcAlerts({ min_edge: 0.04 })
      data = resp.data || []
    }
    dataMap.value = { ...dataMap.value, [tab.value]: data }
  } catch {
    dataMap.value = { ...dataMap.value, [tab.value]: [] }
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.m-opps { padding: 12px; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.back-btn { background: none; border: none; font-size: 14px; color: #409eff; cursor: pointer; padding: 8px 0; }
.page-title { font-size: 16px; font-weight: bold; }
.seg-tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px; }
.seg-tab { height: 36px; border: 1px solid #dcdfe6; background: #fff; border-radius: 8px; font-size: 13px; color: #606266; }
.seg-tab.active { border-color: #409eff; color: #409eff; background: #ecf5ff; font-weight: bold; }
.list { display: flex; flex-direction: column; gap: 8px; }
.card { background: #fff; border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.card-title { font-size: 14px; font-weight: bold; color: #303133; margin-bottom: 8px; line-height: 1.4; }
.card-info { font-size: 13px; color: #606266; display: flex; flex-wrap: wrap; gap: 8px 14px; margin-top: 4px; }
.card-note { font-size: 12px; color: #909399; margin-top: 6px; line-height: 1.4; }
.empty-hint { text-align: center; color: #909399; padding: 40px 0; font-size: 14px; }
</style>
