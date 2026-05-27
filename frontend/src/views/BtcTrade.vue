<template>
  <div>
    <el-row :gutter="20">
      <el-col :span="16">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>BTC 短周期市场</span>
              <div>
                <el-input v-model="searchSlug" placeholder="输入市场 slug" size="small" style="width:300px;margin-right:8px" @keyup.enter="loadMarket" />
                <el-button size="small" type="primary" @click="loadMarket">加载</el-button>
                <el-button size="small" @click="loadBTCMarkets" :loading="loadingMarkets">刷新市场</el-button>
              </div>
            </div>
          </template>

          <!-- BTC 短周期列表 -->
          <el-tabs v-model="activeTab" @tab-change="onTabChange">
            <el-tab-pane label="15分钟" name="15m" />
            <el-tab-pane label="5分钟" name="5m" />
            <el-tab-pane label="其他BTC" name="other" />
          </el-tabs>

          <el-table :data="filteredShortMarkets" size="small" @row-click="selectShortMarket" highlight-current-row max-height="400" v-if="activeTab !== 'other'">
            <el-table-column label="周期 (北京时间)" min-width="180">
              <template #default="{ row }">
                {{ row.start_time_bj }} ~ {{ row.end_time_bj }}
              </template>
            </el-table-column>
            <el-table-column label="UP (YES)" width="100">
              <template #default="{ row }">
                <span style="color:#67c23a">{{ getYesPrice(row) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="DOWN (NO)" width="100">
              <template #default="{ row }">
                <span style="color:#f56c6c">{{ getNoPrice(row) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" type="primary" link @click.stop="selectShortMarket(row)">交易</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-table :data="btcMarkets" size="small" @row-click="selectMarket" v-if="activeTab === 'other'" max-height="400">
            <el-table-column prop="question" label="市场" show-overflow-tooltip />
            <el-table-column label="YES" width="80">
              <template #default="{ row }">{{ getPrice(row, 0) }}</template>
            </el-table-column>
            <el-table-column label="NO" width="80">
              <template #default="{ row }">{{ getPrice(row, 1) }}</template>
            </el-table-column>
            <el-table-column prop="volume" label="成交量" width="100" />
          </el-table>

          <div v-if="currentMarket" style="margin-top:16px">
            <el-descriptions :column="3" border size="small">
              <el-descriptions-item label="YES 价格">${{ yesPrice.toFixed(3) }}</el-descriptions-item>
              <el-descriptions-item label="NO 价格">${{ noPrice.toFixed(3) }}</el-descriptions-item>
              <el-descriptions-item label="成交量">${{ parseFloat(currentMarket.volume || 0).toLocaleString() }}</el-descriptions-item>
            </el-descriptions>

            <el-divider>订单簿</el-divider>
            <el-row :gutter="20">
              <el-col :span="12">
                <h4 style="color:#67c23a">买单 (Bids)</h4>
                <el-table :data="bids" size="small" max-height="200">
                  <el-table-column prop="price" label="价格" />
                  <el-table-column prop="size" label="数量" />
                </el-table>
              </el-col>
              <el-col :span="12">
                <h4 style="color:#f56c6c">卖单 (Asks)</h4>
                <el-table :data="asks" size="small" max-height="200">
                  <el-table-column prop="price" label="价格" />
                  <el-table-column prop="size" label="数量" />
                </el-table>
              </el-col>
            </el-row>
          </div>
          <div v-if="!currentMarket && activeTab === 'other'" style="text-align:center;padding:60px;color:#999">
            输入市场 slug 或选择 BTC 市场开始交易
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>余额 / 持仓</span>
              <el-button size="small" @click="loadPortfolio" :loading="loadingPortfolio">刷新</el-button>
            </div>
          </template>
          <div v-if="portfolioValue !== null" style="font-size:18px;font-weight:bold;margin-bottom:8px">${{ parseFloat(portfolioValue).toFixed(2) }}</div>
          <div v-if="positions.length > 0" style="font-size:12px;color:#666">
            <div v-for="p in positions.slice(0, 5)" :key="p.asset" style="display:flex;justify-content:space-between;padding:2px 0">
              <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:160px">{{ p.title }}</span>
              <span>${{ parseFloat(p.currentValue || 0).toFixed(2) }}</span>
            </div>
            <div v-if="positions.length > 5" style="color:#999;margin-top:4px">共 {{ positions.length }} 个持仓</div>
          </div>
          <div v-else style="color:#999;font-size:12px">暂无持仓</div>
        </el-card>

        <el-card style="margin-top:16px">
          <template #header>快速下单</template>
          <el-form label-position="top" size="small">
            <el-form-item label="方向">
              <el-radio-group v-model="orderForm.side">
                <el-radio-button value="BUY">UP (YES)</el-radio-button>
                <el-radio-button value="SELL">DOWN (NO)</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="下单方式">
              <el-radio-group v-model="orderForm.type">
                <el-radio-button value="market">市价</el-radio-button>
                <el-radio-button value="limit">限价</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="orderForm.type === 'limit'" label="价格">
              <el-input-number v-model="orderForm.price" :min="0.01" :max="0.99" :step="0.01" :precision="2" style="width:100%" />
            </el-form-item>
            <el-form-item :label="orderForm.type === 'market' ? '金额 ($)' : '数量 (shares)'">
              <el-input-number v-model="orderForm.amount" :min="1" style="width:100%" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" style="width:100%" :loading="ordering" @click="placeOrder">
                {{ orderForm.side === 'BUY' ? '买入' : '卖出' }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card style="margin-top:16px">
          <template #header>当前挂单</template>
          <el-button size="small" type="warning" @click="cancelAllOrders" style="margin-bottom:8px">全部撤单</el-button>
          <el-table :data="openOrders" size="small" max-height="200">
            <el-table-column prop="side" label="方向" width="50" />
            <el-table-column prop="price" label="价格" width="60" />
            <el-table-column prop="original_size" label="数量" width="60" />
            <el-table-column label="操作" width="60">
              <template #default="{ row }">
                <el-button size="small" type="danger" link @click="cancelOrder(row.id)">撤</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card style="margin-top:16px">
          <template #header>AI 预测</template>
          <el-select v-model="aiConfigId" placeholder="选择AI模型" size="small" style="width:100%;margin-bottom:8px">
            <el-option v-for="p in aiProviders" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
          <el-button size="small" type="primary" @click="runPredict" :loading="predicting" :disabled="!selectedSlug || !aiConfigId" style="width:100%">
            AI 概率预测
          </el-button>
          <div v-if="prediction" style="margin-top:12px;white-space:pre-wrap;font-size:13px">{{ prediction }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { btcApi, aiApi } from '../api'
import { ElMessage } from 'element-plus'

const searchSlug = ref('')
const currentMarket = ref<any>(null)
const yesPrice = ref(0.5)
const noPrice = ref(0.5)
const bids = ref<any[]>([])
const asks = ref<any[]>([])
const btcMarkets = ref<any[]>([])
const shortMarkets = ref<any[]>([])
const openOrders = ref<any[]>([])
const ordering = ref(false)
const loadingMarkets = ref(false)
const selectedTokenId = ref('')
const selectedTickSize = ref('0.01')
const selectedNegRisk = ref(false)
const activeTab = ref('15m')
const selectedSlug = ref('')
const aiProviders = ref<any[]>([])
const aiConfigId = ref<number | null>(null)
const predicting = ref(false)
const prediction = ref('')
const portfolioValue = ref<string | null>(null)
const positions = ref<any[]>([])
const loadingPortfolio = ref(false)

const orderForm = reactive({
  side: 'BUY',
  type: 'market',
  price: 0.50,
  amount: 10,
})

const filteredShortMarkets = computed(() => {
  const label = activeTab.value === '15m' ? '15分钟' : '5分钟'
  return shortMarkets.value.filter(m => m.series_label === label)
})

function getYesPrice(row: any) {
  const m = row.markets?.[0]
  return m ? `$${m.yes_price.toFixed(3)}` : '-'
}

function getNoPrice(row: any) {
  const m = row.markets?.[0]
  return m ? `$${m.no_price.toFixed(3)}` : '-'
}

function getPrice(row: any, idx: number) {
  const prices = row.outcomePrices
  if (!prices) return '-'
  const p = typeof prices === 'string' ? JSON.parse(prices) : prices
  return p ? `$${parseFloat(p[idx]).toFixed(3)}` : '-'
}

async function loadBTCMarkets() {
  loadingMarkets.value = true
  try {
    const { data } = await btcApi.markets()
    shortMarkets.value = data.short_markets || []
    btcMarkets.value = data.markets || []
  } catch {} finally {
    loadingMarkets.value = false
  }
}

async function loadMarket() {
  if (!searchSlug.value) return
  selectedSlug.value = searchSlug.value
  prediction.value = ''
  try {
    const { data } = await btcApi.market(searchSlug.value)
    currentMarket.value = data.market
    const tokens = typeof data.market.clobTokenIds === 'string' ? JSON.parse(data.market.clobTokenIds) : data.market.clobTokenIds
    if (tokens?.length > 0) selectedTokenId.value = tokens[0]

    selectedTickSize.value = data.market.minimum_tick_size || '0.01'
    selectedNegRisk.value = !!data.market.neg_risk

    const prices = typeof data.market.outcomePrices === 'string' ? JSON.parse(data.market.outcomePrices) : data.market.outcomePrices
    if (prices) {
      yesPrice.value = parseFloat(prices[0])
      noPrice.value = parseFloat(prices[1])
    }

    const yesBook = data.orderbook?.YES
    bids.value = (yesBook?.bids || []).slice(0, 10)
    asks.value = (yesBook?.asks || []).slice(0, 10)
  } catch {}
}

function selectShortMarket(row: any) {
  const market = row.markets?.[0]
  if (!market) return
  selectedTokenId.value = market.token_ids?.[0] || ''
  selectedTickSize.value = market.tick_size || '0.01'
  selectedNegRisk.value = market.neg_risk || false
  yesPrice.value = market.yes_price || 0.5
  noPrice.value = market.no_price || 0.5
  currentMarket.value = { question: row.title, volume: 0 }
  selectedSlug.value = row.event_slug || ''
  prediction.value = ''

  // 加载订单簿
  if (selectedTokenId.value) {
    btcApi.market(row.event_slug).then(({ data }) => {
      const yesBook = data.orderbook?.YES
      bids.value = (yesBook?.bids || []).slice(0, 10)
      asks.value = (yesBook?.asks || []).slice(0, 10)
    }).catch(() => {})
  }
}

function selectMarket(row: any) {
  searchSlug.value = row.slug
  loadMarket()
}

function onTabChange() {
  if (activeTab.value !== 'other') {
    currentMarket.value = null
  }
}

async function placeOrder() {
  if (!selectedTokenId.value) {
    ElMessage.warning('请先选择市场')
    return
  }
  ordering.value = true
  try {
    if (orderForm.type === 'market') {
      await btcApi.marketOrder({
        token_id: selectedTokenId.value,
        amount: orderForm.amount,
        side: orderForm.side,
        order_type: 'FOK',
      })
    } else {
      await btcApi.order({
        token_id: selectedTokenId.value,
        price: orderForm.price,
        size: orderForm.amount,
        side: orderForm.side,
        order_type: 'GTC',
        tick_size: selectedTickSize.value,
        neg_risk: selectedNegRisk.value,
      })
    }
    ElMessage.success('下单成功')
    loadOrders()
  } catch {} finally {
    ordering.value = false
  }
}

async function loadOrders() {
  try {
    const { data } = await btcApi.orders()
    openOrders.value = data.orders || []
  } catch {}
}

async function cancelOrder(id: string) {
  try {
    await btcApi.cancel(id)
    ElMessage.success('撤单成功')
    loadOrders()
  } catch {}
}

async function cancelAllOrders() {
  try {
    await btcApi.cancelAll()
    ElMessage.success('全部撤单成功')
    loadOrders()
  } catch {}
}

async function runPredict() {
  if (!selectedSlug.value || !aiConfigId.value) return
  predicting.value = true
  prediction.value = ''
  try {
    const { data } = await aiApi.analyzeMarket({ ai_config_id: aiConfigId.value, market_slug: selectedSlug.value, question: '分析这个BTC短周期市场，当前价格是否合理，UP和DOWN各有多大概率，给出交易建议。' })
    prediction.value = data.analysis
  } catch {} finally { predicting.value = false }
}

async function loadPortfolio() {
  loadingPortfolio.value = true
  try {
    const { data } = await btcApi.positions()
    positions.value = data.positions || []
    const pv = data.portfolio_value
    portfolioValue.value = Array.isArray(pv) ? (pv[0]?.value ?? null) : (pv?.value ?? null)
  } catch {} finally { loadingPortfolio.value = false }
}

onMounted(() => {
  loadOrders()
  loadBTCMarkets()
  loadPortfolio()
  aiApi.providers().then(({ data }) => { aiProviders.value = data }).catch(() => {})
})
</script>
