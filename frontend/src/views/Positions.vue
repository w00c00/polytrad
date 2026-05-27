<template>
  <div>
    <el-card>
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>持仓总览</span>
          <el-button size="small" @click="load" :loading="loading">刷新</el-button>
        </div>
      </template>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="USDC 余额">${{ usdcBalance }}</el-descriptions-item>
        <el-descriptions-item label="持仓数量">{{ positions.length }}</el-descriptions-item>
        <el-descriptions-item label="持仓总值">${{ totalValue }}</el-descriptions-item>
      </el-descriptions>
      <el-table :data="positions" size="small" v-loading="loading" style="margin-top:16px">
        <el-table-column prop="title" label="市场" show-overflow-tooltip />
        <el-table-column label="到期 (北京)" width="120">
          <template #default="{ row }">{{ row.endDate_bj || row.endDateIso_bj || '-' }}</template>
        </el-table-column>
        <el-table-column prop="size" label="数量" width="100" />
        <el-table-column label="当前价值" width="120">
          <template #default="{ row }">${{ parseFloat(row.currentValue || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="买入均价" width="100">
          <template #default="{ row }">${{ parseFloat(row.avgPrice || 0).toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="盈亏" width="100">
          <template #default="{ row }">
            <span :style="{ color: parseFloat(row.cashPnl || 0) >= 0 ? '#67c23a' : '#f56c6c' }">
              ${{ parseFloat(row.cashPnl || 0).toFixed(2) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="盈亏%" width="80">
          <template #default="{ row }">
            <span :style="{ color: parseFloat(row.percentPnl || 0) >= 0 ? '#67c23a' : '#f56c6c' }">
              {{ parseFloat(row.percentPnl || 0).toFixed(1) }}%
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { btcApi } from '../api'

const loading = ref(false)
const positions = ref<any[]>([])
const balance = ref<any>(null)

const usdcBalance = computed(() => {
  if (!balance.value) return '--'
  const raw = balance.value.balance ?? balance.value.available ?? balance.value.available_balance ?? null
  return raw !== null ? Number(raw).toFixed(2) : '--'
})

const totalValue = computed(() => {
  return positions.value.reduce((sum, p) => sum + parseFloat(p.currentValue || 0), 0).toFixed(2)
})

async function load() {
  loading.value = true
  try {
    const { data } = await btcApi.positions()
    positions.value = data.positions || []
    balance.value = data.balance
  } catch {} finally { loading.value = false }
}

onMounted(load)
</script>
