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
                <el-button size="small" @click="loadBTCMarkets">搜索BTC市场</el-button>
              </div>
            </div>
          </template>

          <div v-if="currentMarket">
            <h3>{{ currentMarket.question }}</h3>
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
          <div v-else style="text-align:center;padding:60px;color:#999">
            输入市场 slug 或搜索 BTC 市场开始交易
          </div>
        </el-card>

        <el-card style="margin-top:16px" v-if="btcMarkets.length">
          <template #header>BTC 相关市场</template>
          <el-table :data="btcMarkets" size="small" @row-click="selectMarket">
            <el-table-column prop="question" label="市场" show-overflow-tooltip />
            <el-table-column label="YES" width="80">
              <template #default="{ row }">{{ getPrice(row, 0) }}</template>
            </el-table-column>
            <el-table-column label="NO" width="80">
              <template #default="{ row }">{{ getPrice(row, 1) }}</template>
            </el-table-column>
            <el-table-column prop="volume" label="成交量" width="100" />
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card>
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
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { btcApi } from '../api'
import { ElMessage } from 'element-plus'

const searchSlug = ref('')
const currentMarket = ref<any>(null)
const yesPrice = ref(0.5)
const noPrice = ref(0.5)
const bids = ref<any[]>([])
const asks = ref<any[]>([])
const btcMarkets = ref<any[]>([])
const openOrders = ref<any[]>([])
const ordering = ref(false)
const selectedTokenId = ref('')
const selectedTickSize = ref('0.01')
const selectedNegRisk = ref(false)

const orderForm = reactive({
  side: 'BUY',
  type: 'market',
  price: 0.50,
  amount: 10,
})

function getPrice(row: any, idx: number) {
  const prices = row.outcomePrices
  if (!prices) return '-'
  const p = typeof prices === 'string' ? JSON.parse(prices) : prices
  return p ? `$${parseFloat(p[idx]).toFixed(3)}` : '-'
}

async function loadBTCMarkets() {
  try {
    const { data } = await btcApi.markets()
    btcMarkets.value = data.markets || []
  } catch {}
}

async function loadMarket() {
  if (!searchSlug.value) return
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

function selectMarket(row: any) {
  searchSlug.value = row.slug
  loadMarket()
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

onMounted(() => loadOrders())
</script>
