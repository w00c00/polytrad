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
          <el-table :data="events" size="small" @row-click="selectEvent" highlight-current-row>
            <el-table-column label="赛事" show-overflow-tooltip>
              <template #default="{ row }">{{ row.title_zh || row.title }}</template>
            </el-table-column>
            <el-table-column label="截止时间 (北京)" width="140">
              <template #default="{ row }">{{ row.end_date_bj || '-' }}</template>
            </el-table-column>
            <el-table-column label="24h成交量" width="120">
              <template #default="{ row }">${{ (row.volume_24h || 0).toLocaleString() }}</template>
            </el-table-column>
            <el-table-column label="市场数" width="80">
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
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button size="small" type="success" @click="quickBuy(row)">买YES</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card>
          <template #header>快速下单</template>
          <el-form label-position="top" size="small">
            <el-form-item label="方向">
              <el-radio-group v-model="form.side">
                <el-radio-button value="BUY">YES</el-radio-button>
                <el-radio-button value="SELL">NO</el-radio-button>
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
import { ref, reactive, watch, onMounted } from 'vue'
import { sportsApi, aiApi } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const ordering = ref(false)
const predicting = ref(false)
const events = ref<any[]>([])
const selectedEvent = ref<any>(null)
const aiProviders = ref<any[]>([])
const aiConfigId = ref<number | null>(null)
const prediction = ref('')
const form = reactive({ side: 'BUY', amount: 10, tokenId: '', price: 0.5 })

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

function quickBuy(row: any) {
  if (row.token_ids?.length > 0) {
    form.tokenId = row.token_ids[0]
    form.side = 'BUY'
    form.price = row.yes_price || 0.5
    ElMessage.success(`已选择: ${row.question_zh || row.question}`)
  }
}

async function placeOrder() {
  if (!form.tokenId) { ElMessage.warning('请先点击买YES选择市场'); return }
  ordering.value = true
  try {
    // amount 是 USDC 金额，转换为 shares: shares = amount / price
    const price = form.price || 0.5
    const size = Math.floor(form.amount / price)
    await sportsApi.order({ token_id: form.tokenId, price, size, side: form.side, order_type: 'FOK' })
    ElMessage.success(`下单成功: ${size} shares @ $${price.toFixed(3)}`)
  } catch {} finally { ordering.value = false }
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
