<template>
  <div>
    <el-card>
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>热门尾盘扫描</span>
          <div>
            <el-input-number v-model="hours" :min="1" :max="168" size="small" style="width:100px" />
            <span style="margin:0 8px">小时内到期</span>
            <el-button type="primary" size="small" @click="scan" :loading="loading">扫描</el-button>
          </div>
        </div>
      </template>

      <el-table :data="results" size="small" v-loading="loading">
        <el-table-column prop="title" label="市场" show-overflow-tooltip />
        <el-table-column label="24h成交量" width="120">
          <template #default="{ row }">${{ (row.volume_24h || 0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="end_date" label="到期时间" width="180" />
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

    <el-dialog v-model="showDetail" title="市场详情" width="600">
      <el-table :data="detailMarkets" size="small">
        <el-table-column prop="question" label="结果" show-overflow-tooltip />
        <el-table-column label="YES" width="80">
          <template #default="{ row }">${{ row.yes_price.toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="NO" width="80">
          <template #default="{ row }">${{ row.no_price.toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button size="small" type="success" @click="quickBuy(row)">买YES</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { hotApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const hours = ref(24)
const results = ref<any[]>([])
const showDetail = ref(false)
const detailMarkets = ref<any[]>([])

async function scan() {
  loading.value = true
  try {
    const { data } = await hotApi.scan(hours.value)
    results.value = data || []
    if (results.value.length === 0) ElMessage.info('未发现符合条件的市场')
  } catch {} finally { loading.value = false }
}

function expandMarket(row: any) {
  detailMarkets.value = row.markets || []
  showDetail.value = true
}

async function quickBuy(row: any) {
  if (!row.token_ids?.length) return
  try {
    await hotApi.order({
      token_id: row.token_ids[0],
      price: row.yes_price,
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
