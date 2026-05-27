<template>
  <div>
    <el-card>
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>事件套利扫描</span>
          <div>
            <span style="margin-right:8px">偏差阈值:</span>
            <el-input-number v-model="threshold" :min="0.01" :max="0.5" :step="0.01" :precision="2" size="small" style="width:100px;margin-right:8px" />
            <el-button type="primary" size="small" @click="scan" :loading="loading">扫描</el-button>
          </div>
        </div>
      </template>

      <el-table :data="results" size="small" v-loading="loading">
        <el-table-column prop="title" label="事件" show-overflow-tooltip />
        <el-table-column label="YES总和" width="100">
          <template #default="{ row }">{{ row.yes_sum.toFixed(4) }}</template>
        </el-table-column>
        <el-table-column label="偏差" width="100">
          <template #default="{ row }">{{ row.deviation.toFixed(4) }}</template>
        </el-table-column>
        <el-table-column label="方向" width="100">
          <template #default="{ row }">
            <el-tag :type="row.direction === 'SELL_YES' ? 'danger' : 'success'" size="small">{{ row.direction }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="市场数" width="80">
          <template #default="{ row }">{{ row.markets?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" @click="expandDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showDetail" title="套利详情" width="700">
      <el-descriptions :column="2" border size="small" v-if="selected">
        <el-descriptions-item label="事件">{{ selected.title }}</el-descriptions-item>
        <el-descriptions-item label="YES总和">{{ selected.yes_sum.toFixed(4) }}</el-descriptions-item>
        <el-descriptions-item label="偏差">{{ selected.deviation.toFixed(4) }}</el-descriptions-item>
        <el-descriptions-item label="建议方向">
          <el-tag :type="selected.direction === 'SELL_YES' ? 'danger' : 'success'">{{ selected.direction }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <el-table :data="selected?.markets || []" size="small" style="margin-top:16px">
        <el-table-column prop="question" label="市场" show-overflow-tooltip />
        <el-table-column label="YES价格" width="100">
          <template #default="{ row }">${{ row.yes_price.toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="executeArb(row)">执行</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { arbitrageApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const threshold = ref(0.03)
const results = ref<any[]>([])
const showDetail = ref(false)
const selected = ref<any>(null)

async function scan() {
  loading.value = true
  try {
    const { data } = await arbitrageApi.scan(threshold.value)
    results.value = data || []
    if (results.value.length === 0) ElMessage.info('未发现套利机会')
  } catch {} finally { loading.value = false }
}

function expandDetail(row: any) {
  selected.value = row
  showDetail.value = true
}

async function executeArb(row: any) {
  if (!row.token_ids?.length) return
  try {
    await arbitrageApi.execute({
      token_id: row.token_ids[0],
      price: row.yes_price,
      size: 10,
      side: 'BUY',
      neg_risk: true,
      tick_size: row.tick_size || '0.01',
    })
    ElMessage.success('套利下单成功')
  } catch {}
}
</script>
