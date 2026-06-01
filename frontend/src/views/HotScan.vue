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

      <el-table :data="results" size="small" v-loading="loading" @row-click="selectRow" highlight-current-row>
        <el-table-column label="市场" show-overflow-tooltip>
          <template #default="{ row }">{{ row.title_zh || row.title }}</template>
        </el-table-column>
        <el-table-column label="24h成交量" width="120">
          <template #default="{ row }">${{ (row.volume_24h || 0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="到期时间 (北京)" width="140">
          <template #default="{ row }">{{ row.end_date_bj || row.end_date || '-' }}</template>
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

    <el-dialog v-model="showDetail" title="市场详情" width="600">
      <el-form inline size="small" style="margin-bottom:12px">
        <el-form-item label="下单金额 ($)">
          <el-input-number v-model="orderAmount" :min="1" :step="1" style="width:120px" />
        </el-form-item>
      </el-form>
      <el-table :data="detailMarkets" size="small">
        <el-table-column label="结果" show-overflow-tooltip>
          <template #default="{ row }">{{ row.question_zh || row.question }}</template>
        </el-table-column>
        <el-table-column label="YES" width="80">
          <template #default="{ row }">${{ row.yes_price.toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="NO" width="80">
          <template #default="{ row }">${{ row.no_price.toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="到期" width="120">
          <template #default="{ row }">{{ row.end_date_bj || selectedEvent?.end_date_bj || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button size="small" type="success" @click="quickBuy(row, 'YES')">买YES</el-button>
            <el-button size="small" type="danger" @click="quickBuy(row, 'NO')">买NO</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { hotApi, aiApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const hours = ref(24)
const results = ref<any[]>([])
const showDetail = ref(false)
const detailMarkets = ref<any[]>([])
const selectedEvent = ref<any>(null)
const aiProviders = ref<any[]>([])
const aiConfigId = ref<number | null>(null)
const predicting = ref(false)
const prediction = ref('')
const orderAmount = ref(10)

async function scan() {
  loading.value = true
  try {
    const { data } = await hotApi.scan(hours.value)
    results.value = data || []
    if (results.value.length === 0) ElMessage.info('未发现符合条件的市场')
  } catch {} finally { loading.value = false }
}

function selectRow(row: any) {
  selectedEvent.value = row
  prediction.value = ''
}

function expandMarket(row: any) {
  detailMarkets.value = row.markets || []
  showDetail.value = true
  selectedEvent.value = row
  prediction.value = ''
}

async function quickBuy(row: any, direction: string = 'YES') {
  if (!row.token_ids?.length) return
  const tokenId = direction === 'NO' ? row.token_ids[1] : row.token_ids[0]
  if (!tokenId) { ElMessage.warning('缺少对应方向的 token'); return }
  try {
    const resp = await hotApi.order({
      token_id: tokenId,
      side: 'BUY',
      order_type: 'GTC',
      tick_size: row.tick_size || '0.01',
      neg_risk: row.neg_risk || false,
      market_slug: row.slug || '',
      condition_id: row.condition_id || '',
      usdc_amount: orderAmount.value,
    })
    const d = resp.data
    ElMessage.success(`买入 ${direction} 成功: $${orderAmount.value} → ${d.size} 份 @ $${d.price}`)
  } catch (err: any) {
    const raw = err?.response?.data?.detail || err?.message || '未知错误'
    ElMessage.error({ message: `下单失败: ${raw}`, duration: 5000 })
  }
}

async function runPredict() {
  if (!selectedEvent.value || !aiConfigId.value) return
  predicting.value = true
  prediction.value = ''
  try {
    const { data } = await aiApi.analyzeMarket({ ai_config_id: aiConfigId.value, market_slug: selectedEvent.value.event_slug, question: '分析这个即将到期的热门市场，各结果的胜率如何，当前价格是否合理，给出交易建议。' })
    prediction.value = data.analysis
  } catch {} finally { predicting.value = false }
}

watch(aiProviders, (list) => {
  if (list.length === 1 && !aiConfigId.value) aiConfigId.value = list[0].id
})

onMounted(() => {
  aiApi.providers().then(({ data }) => { aiProviders.value = data }).catch(() => {})
})
</script>
