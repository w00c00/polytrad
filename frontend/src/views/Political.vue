<template>
  <div>
    <el-card>
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>政治类新盘扫描</span>
          <el-button type="primary" size="small" @click="scan" :loading="loading">扫描新盘</el-button>
        </div>
      </template>
      <el-table :data="results" size="small" v-loading="loading" @row-click="expandMarket" highlight-current-row>
        <el-table-column label="事件" show-overflow-tooltip>
          <template #default="{ row }">{{ row.title_zh || row.title }}</template>
        </el-table-column>
        <el-table-column label="创建时间 (北京)" width="180">
          <template #default="{ row }">{{ row.start_date_bj || row.start_date || '-' }}</template>
        </el-table-column>
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

    <el-card style="margin-top:16px">
      <template #header>AI 预测</template>
      <el-row :gutter="12" align="middle">
        <el-col :span="8">
          <el-select v-model="aiConfigId" placeholder="选择AI模型" size="small" style="width:100%">
            <el-option v-for="p in aiProviders" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-col>
        <el-col :span="8">
          <el-button size="small" type="primary" @click="runPredict" :loading="predicting" :disabled="!selectedEvent || !aiConfigId" style="width:100%">AI 概率预测</el-button>
        </el-col>
      </el-row>
      <div v-if="prediction" style="margin-top:12px;white-space:pre-wrap;font-size:13px">{{ prediction }}</div>
      <div v-if="!selectedEvent" style="margin-top:8px;color:#999;font-size:12px">请先点击表格行选择一个市场</div>
    </el-card>

    <el-dialog v-model="showDetail" title="新盘详情" width="700">
      <el-table :data="detailMarkets" size="small">
        <el-table-column label="结果" show-overflow-tooltip>
          <template #default="{ row }">{{ row.question_zh || row.question }}</template>
        </el-table-column>
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
import { ref, onMounted } from 'vue'
import { politicalApi, aiApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const results = ref<any[]>([])
const showDetail = ref(false)
const detailMarkets = ref<any[]>([])
const selectedEvent = ref<any>(null)
const aiProviders = ref<any[]>([])
const aiConfigId = ref<number | null>(null)
const predicting = ref(false)
const prediction = ref('')

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
  selectedEvent.value = row
  prediction.value = ''
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

async function runPredict() {
  if (!selectedEvent.value || !aiConfigId.value) return
  predicting.value = true
  prediction.value = ''
  try {
    const { data } = await aiApi.analyzeMarket({ ai_config_id: aiConfigId.value, market_slug: selectedEvent.value.event_slug, question: '分析这个政治类市场的各结果概率，当前价格是否合理，给出交易建议。' })
    prediction.value = data.analysis
  } catch {} finally { predicting.value = false }
}

onMounted(() => {
  aiApi.providers().then(({ data }) => { aiProviders.value = data }).catch(() => {})
})
</script>
