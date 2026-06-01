<template>
  <div>
    <el-row :gutter="20">
      <el-col :span="16">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>体育赛事</span>
              <el-button size="small" type="primary" @click="loadEvents" :loading="loading">刷新赛事</el-button>
            </div>
          </template>
          <el-tabs v-model="sportsTab">
            <el-tab-pane label="近期比赛" name="games" />
            <el-tab-pane label="赛事冠军" name="champs" />
          </el-tabs>

          <el-table :data="filteredEvents" size="small" @row-click="selectEvent" highlight-current-row max-height="500">
            <el-table-column label="赛事" show-overflow-tooltip>
              <template #default="{ row }">{{ row.title_zh || row.title }}</template>
            </el-table-column>
            <el-table-column label="截止时间 (北京)" width="140">
              <template #default="{ row }">{{ row.end_date_bj || '-' }}</template>
            </el-table-column>
            <el-table-column label="成交量" width="100">
              <template #default="{ row }">${{ (row.volume_24h || 0).toLocaleString() }}</template>
            </el-table-column>
            <el-table-column label="市场" width="60">
              <template #default="{ row }">{{ row.markets?.length || 0 }}</template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card v-if="selectedEvent" style="margin-top:16px">
          <template #header>{{ selectedEvent.title_zh || selectedEvent.title }} - 市场</template>
          <el-table :data="selectedEvent.markets" size="small">
            <el-table-column label="结果" show-overflow-tooltip>
              <template #default="{ row }">{{ row.question_zh || row.question }}</template>
            </el-table-column>
            <el-table-column label="YES价格" width="100">
              <template #default="{ row }">${{ (row.yes_price || 0).toFixed(3) }}</template>
            </el-table-column>
            <el-table-column label="成交量" width="100">
              <template #default="{ row }">${{ (row.volume || 0).toLocaleString() }}</template>
            </el-table-column>
            <el-table-column label="到期" width="120">
              <template #default="{ row }">{{ row.end_date_bj || selectedEvent?.end_date_bj || '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button size="small" type="primary" @click="selectMarket(row)">选择</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card>
          <template #header>快速下单</template>
          <el-form label-position="top" size="small">
            <el-form-item label="已选市场">
              <div style="font-size:12px;color:#666">{{ selectedMarketObj?.question_zh || selectedMarketObj?.question || '未选择' }}</div>
              <div v-if="selectedMarketObj" style="font-size:12px;color:#f56c6c;margin-top:4px">到期: {{ selectedMarketObj.end_date_bj || selectedEvent?.end_date_bj || '-' }}</div>
            </el-form-item>
            <el-form-item label="方向">
              <el-radio-group v-model="form.direction">
                <el-radio-button value="YES">YES</el-radio-button>
                <el-radio-button value="NO">NO</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="金额 ($)">
              <el-input-number v-model="form.amount" :min="1" style="width:100%" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" style="width:100%" :loading="ordering" @click="placeOrder">市价下单</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card style="margin-top:16px">
          <template #header>AI 预测</template>
          <el-select v-model="aiConfigId" placeholder="选择AI模型" size="small" style="width:100%;margin-bottom:8px">
            <el-option v-for="p in aiProviders" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
          <el-button size="small" type="primary" @click="runPredict" :loading="predicting" :disabled="!selectedEvent || !aiConfigId" style="width:100%">
            AI 概率预测
          </el-button>
          <div v-if="prediction" style="margin-top:12px;white-space:pre-wrap;font-size:13px">{{ prediction }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { sportsApi, aiApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const ordering = ref(false)
const predicting = ref(false)
const events = ref<any[]>([])
const selectedEvent = ref<any>(null)
const sportsTab = ref('games')

const filteredEvents = computed(() => {
  if (sportsTab.value === 'games') {
    return events.value.filter(e => e.is_game)
  }
  return events.value.filter(e => !e.is_game)
})
const aiProviders = ref<any[]>([])
const aiConfigId = ref<number | null>(null)
const prediction = ref('')
const form = reactive({ direction: 'YES', amount: 10 })
const selectedMarketObj = ref<any>(null)

async function loadEvents() {
  loading.value = true
  try {
    const { data } = await sportsApi.events()
    events.value = data || []
  } catch {} finally { loading.value = false }
}

function selectEvent(row: any) {
  selectedEvent.value = row
  prediction.value = ''
}

function selectMarket(row: any) {
  if (!row.token_ids?.length) {
    ElMessage.warning('该市场缺少 token 信息')
    return
  }
  selectedMarketObj.value = row
  ElMessage.success(`已选择: ${row.question_zh || row.question}`)
}

function explainOrderError(msg: string): string {
  const m = msg.toLowerCase()
  if (m.includes('balance') || m.includes('allowance') || m.includes('insufficient'))
    return 'USDC 余额不足，请先充值'
  if (m.includes('fill') || m.includes('fok'))
    return '市场流动性不足，无法成交'
  if (m.includes('tick_size') || m.includes('tick size'))
    return '价格不符合最小变动单位要求'
  if (m.includes('timeout') || m.includes('network'))
    return '网络超时，请稍后重试'
  const colon = msg.indexOf(':')
  if (colon > 0) return msg.slice(colon + 1).trim()
  return msg
}

async function placeOrder() {
  // P0 #2: 根据 direction (YES/NO) 正确选择 token_id，side 统一 BUY
  // YES → token_ids[0], NO → token_ids[1]
  const market = selectedMarketObj.value
  if (!market || !market.token_ids?.length) {
    ElMessage.warning('请先点击"选择"按钮选中市场')
    return
  }
  const tokens = market.token_ids
  const tokenId = form.direction === 'NO' ? tokens[1] : tokens[0]
  if (!tokenId) {
    ElMessage.warning('该市场缺少对应方向的 token')
    return
  }
  ordering.value = true
  try {
    const resp = await sportsApi.order({
      token_id: tokenId,
      side: 'BUY',
      order_type: 'GTC',
      tick_size: market.tick_size || '0.01',
      neg_risk: market.neg_risk || false,
      market_slug: market.slug || '',
      condition_id: market.condition_id || '',
      usdc_amount: form.amount,
    })
    const d = resp.data
    ElMessage.success(`买入 ${form.direction} 成功: $${form.amount} → ${d.size} 份 @ $${d.price}`)
  } catch (err: any) {
    const raw = err?.response?.data?.detail || err?.message || '未知错误'
    ElMessage.error({ message: `下单失败: ${explainOrderError(String(raw))}`, duration: 5000 })
  } finally { ordering.value = false }
}

async function runPredict() {
  if (!selectedEvent.value || !aiConfigId.value) return
  predicting.value = true
  try {
    const { data } = await sportsApi.predict(aiConfigId.value, selectedEvent.value.event_slug)
    prediction.value = data.analysis
  } catch {} finally { predicting.value = false }
}

watch(aiProviders, (list) => {
  if (list.length === 1 && !aiConfigId.value) aiConfigId.value = list[0].id
})

onMounted(async () => {
  loadEvents()
  try {
    const { data } = await aiApi.providers()
    aiProviders.value = data
  } catch {}
})
</script>
