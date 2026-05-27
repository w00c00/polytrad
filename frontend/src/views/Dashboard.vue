<template>
  <div>
    <h2>交易总览</h2>
    <el-row :gutter="20">
      <el-col :span="6" v-for="card in cards" :key="card.title">
        <el-card shadow="hover" class="dash-card" @click="router.push(card.path)">
          <div class="card-icon"><el-icon :size="32"><component :is="card.icon" /></el-icon></div>
          <div class="card-title">{{ card.title }}</div>
          <div class="card-desc">{{ card.desc }}</div>
        </el-card>
      </el-col>
    </el-row>
    <el-row :gutter="20" style="margin-top:20px">
      <el-col :span="12">
        <el-card>
          <template #header>当前挂单</template>
          <div v-if="trades.length === 0" style="text-align:center;color:#999;padding:40px">暂无挂单</div>
          <el-table v-else :data="trades" size="small" max-height="300">
            <el-table-column prop="side" label="方向" width="60">
              <template #default="{ row }">
                <el-tag :type="row.side === 'BUY' ? 'success' : 'danger'" size="small">{{ row.side }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="price" label="价格" width="70" />
            <el-table-column prop="original_size" label="数量" width="70" />
            <el-table-column prop="status" label="状态" width="80" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>持仓概况</template>
          <div v-if="positions.length === 0" style="text-align:center;color:#999;padding:40px">暂无持仓</div>
          <el-table v-else :data="positions" size="small" max-height="300">
            <el-table-column prop="title" label="市场" show-overflow-tooltip />
            <el-table-column prop="size" label="数量" width="80" />
            <el-table-column label="价值" width="100">
              <template #default="{ row }">${{ parseFloat(row.currentValue || 0).toFixed(2) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { btcApi } from '../api'

const router = useRouter()
const trades = ref<any[]>([])
const positions = ref<any[]>([])

const cards = [
  { title: 'BTC短周期', desc: '快速交易BTC预测市场', icon: 'TrendCharts', path: '/btc' },
  { title: '体育赛事', desc: '世界杯等体育赛事交易', icon: 'Football', path: '/sports' },
  { title: '热门尾盘', desc: '扫描即将到期的热门市场', icon: 'Flame', path: '/hot' },
  { title: '事件套利', desc: '多市场定价偏差套利', icon: 'Switch', path: '/arbitrage' },
]

onMounted(async () => {
  try {
    const { data } = await btcApi.positions()
    positions.value = (data.positions || []).slice(0, 10)
  } catch {}
  try {
    const { data } = await btcApi.orders()
    trades.value = (data.orders || []).slice(0, 10)
  } catch {}
})
</script>

<style scoped>
.dash-card { cursor:pointer; text-align:center; }
.card-icon { margin-bottom:8px; color:#409eff; }
.card-title { font-size:16px; font-weight:bold; }
.card-desc { font-size:12px; color:#999; margin-top:4px; }
</style>
