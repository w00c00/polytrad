<template>
  <div>
    <el-card>
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>持仓总览</span>
          <el-button size="small" @click="load" :loading="loading">刷新</el-button>
        </div>
      </template>
      <el-descriptions :column="3" border size="small" v-if="portfolio">
        <el-descriptions-item label="总价值">${{ parseFloat(portfolio.value || 0).toFixed(2) }}</el-descriptions-item>
      </el-descriptions>
      <el-table :data="positions" size="small" v-loading="loading" style="margin-top:16px">
        <el-table-column prop="title" label="市场" show-overflow-tooltip />
        <el-table-column prop="size" label="数量" width="100" />
        <el-table-column label="当前价值" width="120">
          <template #default="{ row }">${{ parseFloat(row.currentValue || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="买入均价" width="100">
          <template #default="{ row }">${{ parseFloat(row.avgPrice || 0).toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="盈亏" width="100">
          <template #default="{ row }">
            <span :style="{ color: parseFloat(row.pnl || 0) >= 0 ? '#67c23a' : '#f56c6c' }">
              ${{ parseFloat(row.pnl || 0).toFixed(2) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { btcApi } from '../api'

const loading = ref(false)
const positions = ref<any[]>([])
const portfolio = ref<any>(null)

async function load() {
  loading.value = true
  try {
    const { data } = await btcApi.positions()
    positions.value = data.positions || []
    portfolio.value = data.portfolio_value
  } catch {} finally { loading.value = false }
}

onMounted(load)
</script>
