<template>
  <div>
    <el-card>
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>政治类新盘扫描</span>
          <el-button type="primary" size="small" @click="scan" :loading="loading">扫描新盘</el-button>
        </div>
      </template>
      <el-table :data="results" size="small" v-loading="loading">
        <el-table-column prop="title" label="事件" show-overflow-tooltip />
        <el-table-column prop="start_date" label="创建时间" width="180" />
        <el-table-column label="市场数" width="80">
          <template #default="{ row }">{{ row.markets?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" @click="expandMarket(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showDetail" title="新盘详情" width="700">
      <el-table :data="detailMarkets" size="small">
        <el-table-column prop="question" label="结果" show-overflow-tooltip />
        <el-table-column label="YES价格" width="100">
          <template #default="{ row }">${{ row.yes_price.toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="成交量" width="100">
          <template #default="{ row }">${{ (row.volume || 0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" type="success" @click="quickBuy(row, 'BUY')">买YES</el-button>
            <el-button size="small" type="danger" @click="quickBuy(row, 'SELL')">买NO</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { politicalApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const results = ref<any[]>([])
const showDetail = ref(false)
const detailMarkets = ref<any[]>([])

async function scan() {
  loading.value = true
  try {
    const { data } = await politicalApi.scan()
    results.value = data || []
  } catch {} finally { loading.value = false }
}

function expandMarket(row: any) {
  detailMarkets.value = row.markets || []
  showDetail.value = true
}

async function quickBuy(row: any, side: string) {
  if (!row.token_ids?.length) return
  const tokenId = side === 'BUY' ? row.token_ids[0] : row.token_ids[1]
  try {
    await politicalApi.order({
      token_id: tokenId,
      price: side === 'BUY' ? row.yes_price : (1 - row.yes_price),
      size: 10,
      side: 'BUY',
      order_type: 'GTC',
      tick_size: row.tick_size || '0.01',
      neg_risk: row.neg_risk || false,
    })
    ElMessage.success('下单成功')
  } catch {}
}
</script>
