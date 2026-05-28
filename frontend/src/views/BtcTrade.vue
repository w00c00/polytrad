<template>
  <div>
    <el-row :gutter="20">
      <el-col :span="16">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>BTC 短周期市场</span>
              <div>
                <el-tooltip content="slug 来自 Polymarket URL，例如 polymarket.com/event/btc-above-100k 中的 btc-above-100k" placement="top">
                  <el-input v-model="searchSlug" placeholder="输入市场 slug（从 Polymarket URL 获取）" size="small" style="width:300px;margin-right:8px" @keyup.enter="loadMarket" />
                </el-tooltip>
                <el-button size="small" type="primary" @click="loadMarket">加载</el-button>
                <el-button size="small" @click="loadBTCMarkets" :loading="loadingMarkets">刷新市场</el-button>
              </div>
            </div>
          </template>

          <!-- BTC 短周期列表 -->
          <el-tabs v-model="activeTab" @tab-change="onTabChange">
            <el-tab-pane label="15分钟" name="15m" />
            <el-tab-pane label="1小时" name="1h" />
            <el-tab-pane label="4小时" name="4h" />
            <el-tab-pane label="1天" name="1d" />
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
          <div style="margin-bottom:12px">
            <div style="font-size:12px;color:#999">USDC 可用余额</div>
            <div style="font-size:20px;font-weight:bold;color:#409eff">${{ usdcBalance }}</div>
          </div>
          <el-divider style="margin:8px 0" />
          <div v-if="positions.length > 0" style="font-size:12px;color:#666">
            <div style="font-size:12px;color:#999;margin-bottom:4px">持仓 ({{ positions.length }}) · 总值 ${{ totalPositionValue }}</div>
            <div v-for="p in positions.slice(0, 5)" :key="p.asset" style="display:flex;align-items:center;justify-content:space-between;padding:3px 0;gap:6px">
              <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0">{{ p.title_zh || p.title }}</span>
              <span :style="{ color: parseFloat(p.cashPnl || 0) >= 0 ? '#67c23a' : '#f56c6c', whiteSpace:'nowrap' }">${{ parseFloat(p.currentValue || 0).toFixed(2) }}</span>
              <el-button size="small" type="danger" link @click="quickSell(p)" :loading="sellingAsset === p.asset">卖</el-button>
            </div>
            <div v-if="positions.length > 5" style="color:#999;margin-top:4px">还有 {{ positions.length - 5 }} 个持仓</div>
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
            <el-form-item label="金额 (USDC)">
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
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>BTC 短周期预测</span>
              <span v-if="signalData" style="font-size:12px;color:#999">{{ signalData.fetched_at }}</span>
            </div>
          </template>
          <el-select v-model="aiConfigId" placeholder="选择AI模型" size="small" style="width:100%;margin-bottom:8px">
            <el-option v-for="p in aiProviders" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
          <el-button size="small" type="primary" @click="runPredict" :loading="predicting" :disabled="!aiConfigId" style="width:100%">
            {{ selectedSlug ? 'AI 概率预测' : '本地技术分析' }}
          </el-button>

          <!-- 本地信号 -->
          <div v-if="signalData" style="margin-top:12px">
            <div style="font-weight:bold;margin-bottom:6px">本地技术分析</div>
            <div style="display:flex;gap:16px;margin-bottom:6px">
              <div>UP: <span style="color:#67c23a;font-weight:bold">{{ (signalData.prob_up * 100).toFixed(1) }}%</span></div>
              <div>DOWN: <span style="color:#f56c6c;font-weight:bold">{{ (signalData.prob_down * 100).toFixed(1) }}%</span></div>
              <div>置信: {{ signalData.confidence }}</div>
            </div>
            <div style="font-size:12px;color:#666">
              RSI {{ signalData.rsi }} | 波动率 {{ (signalData.vol * 100).toFixed(3) }}%
            </div>
            <div v-if="localAction" style="margin-top:6px;padding:6px 10px;border-radius:4px;font-weight:bold"
              :style="{ background: localAction === '不交易' ? '#fdf6ec' : '#ecf5ff', color: localAction === '不交易' ? '#e6a23c' : '#409eff' }">
              本地建议: {{ localAction }} {{ localEdge }}
            </div>
          </div>

          <!-- AI 分析 -->
          <div v-if="aiPrediction" style="margin-top:12px;border-top:1px solid #eee;padding-top:10px">
            <div style="font-weight:bold;margin-bottom:6px">AI 综合分析</div>
            <div style="white-space:pre-wrap;font-size:13px;line-height:1.6">{{ aiPrediction }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
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
const signalData = ref<any>(null)
const localAction = ref('')
const localEdge = ref('')
const aiPrediction = ref('')
const portfolioValue = ref<string | null>(null)
const usdcBalance = ref('--')
const positions = ref<any[]>([])
const loadingPortfolio = ref(false)
const sellingAsset = ref('')

const totalPositionValue = computed(() => {
  return positions.value.reduce((sum, p) => sum + parseFloat(p.currentValue || 0), 0).toFixed(2)
})

const orderForm = reactive({
  side: 'BUY',
  type: 'market',
  price: 0.50,
  amount: 10,
})

const tabLabelMap: Record<string, string> = {
  '5m': '5分钟', '15m': '15分钟', '1h': '1小时', '4h': '4小时', '1d': '1天'
}
const filteredShortMarkets = computed(() => {
  const label = tabLabelMap[activeTab.value]
  if (!label) return []
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
  currentMarket.value = { question: row.title_zh || row.title, volume: 0 }
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

function explainOrderError(msg: string): string {
  const m = msg.toLowerCase()
  if (m.includes('balance') || m.includes('allowance') || m.includes('insufficient'))
    return 'USDC 余额不足，请先充值'
  if (m.includes('fill') || m.includes('fok'))
    return '市场流动性不足，无法成交'
  if (m.includes('tick_size') || m.includes('tick size'))
    return '价格不符合最小变动单位要求'
  if (m.includes('neg_risk'))
    return '该市场为负风险市场，下单参数有误'
  if (m.includes('min') && m.includes('size'))
    return '下单数量低于最低要求'
  if (m.includes('cancel'))
    return '订单已被取消'
  if (m.includes('not found') || m.includes('404'))
    return '市场或代币不存在'
  if (m.includes('unauthorized') || m.includes('401'))
    return '钱包未配置或已过期，请重新配置'
  if (m.includes('timeout') || m.includes('network'))
    return '网络超时，请稍后重试'
  // 截取冒号后面的具体信息
  const colon = msg.indexOf(':')
  if (colon > 0) return msg.slice(colon + 1).trim()
  return msg
}

async function placeOrder() {
  if (!selectedTokenId.value) {
    ElMessage.warning('请先选择市场')
    return
  }
  ordering.value = true
  try {
    if (orderForm.type === 'market') {
      // 市价单：用盘口价下 GTC 限价单（避免 FOK 流动性不足失败）
      const bookPrice = orderForm.side === 'BUY'
        ? (asks.value.length > 0 ? Math.min(...asks.value.map((a: any) => parseFloat(a.price))) : yesPrice.value)
        : (bids.value.length > 0 ? Math.max(...bids.value.map((b: any) => parseFloat(b.price))) : noPrice.value)
      const price = Math.round(bookPrice * 100) / 100
      if (price <= 0) { ElMessage.warning('无法获取盘口价格'); return }
      const size = Math.floor(orderForm.amount / price)
      if (size <= 0) { ElMessage.warning('金额太小，无法转换为有效数量'); return }
      await btcApi.order({
        token_id: selectedTokenId.value,
        price,
        size,
        side: orderForm.side,
        order_type: 'GTC',
        tick_size: selectedTickSize.value,
      })
    } else {
      // 限价单：amount 是 USDC 金额，转换为 shares
      const price = Math.round(orderForm.price * 100) / 100
      if (price <= 0) { ElMessage.warning('价格必须大于 0'); return }
      const size = Math.floor(orderForm.amount / price)
      if (size <= 0) { ElMessage.warning('数量必须大于 0'); return }
      await btcApi.order({
        token_id: selectedTokenId.value,
        price,
        size,
        side: orderForm.side,
        order_type: 'GTC',
        tick_size: selectedTickSize.value,
      })
    }
    ElMessage.success('下单成功')
    loadOrders()
  } catch (err: any) {
    const raw = err?.response?.data?.detail || err?.message || '未知错误'
    ElMessage.error({ message: `下单失败: ${explainOrderError(String(raw))}`, duration: 5000 })
  } finally {
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
  } catch (err: any) {
    const raw = err?.response?.data?.detail || err?.message || '未知错误'
    ElMessage.error(`撤单失败: ${explainOrderError(String(raw))}`)
  }
}

async function cancelAllOrders() {
  try {
    await btcApi.cancelAll()
    ElMessage.success('全部撤单成功')
    loadOrders()
  } catch (err: any) {
    const raw = err?.response?.data?.detail || err?.message || '未知错误'
    ElMessage.error(`撤单失败: ${explainOrderError(String(raw))}`)
  }
}

async function quickSell(p: any) {
  const tokenId = p.asset
  if (!tokenId) { ElMessage.warning('无法获取持仓 token'); return }
  const size = Math.floor(parseFloat(p.size || 0))
  if (size <= 0) { ElMessage.warning('持仓数量为 0'); return }
  sellingAsset.value = tokenId
  try {
    // 用盘口价卖出（取 bid 价）
    const price = yesPrice.value > 0 ? Math.round(yesPrice.value * 100) / 100 : 0.01
    await btcApi.order({
      token_id: tokenId,
      price,
      size,
      side: 'SELL',
      order_type: 'GTC',
      tick_size: '0.01',
    })
    ElMessage.success(`挂卖单成功: ${size} 份 @ $${price.toFixed(2)}`)
    loadOrders()
  } catch (err: any) {
    const raw = err?.response?.data?.detail || err?.message || '未知错误'
    ElMessage.error({ message: `卖出失败: ${explainOrderError(String(raw))}`, duration: 5000 })
  } finally {
    sellingAsset.value = ''
  }
}

async function runPredict() {
  if (!aiConfigId.value) return
  predicting.value = true
  signalData.value = null
  localAction.value = ''
  localEdge.value = ''
  aiPrediction.value = ''

  // 从选中的短周期市场提取信息
  const horizon = activeTab.value === '5m' ? 5 : 15
  const question = currentMarket.value?.question || ''
  const upPrice = yesPrice.value
  const downPrice = noPrice.value

  try {
    const { data } = await btcApi.predict({
      ai_config_id: aiConfigId.value,
      horizon_minutes: horizon,
      market_question: question,
      up_price: upPrice,
      down_price: downPrice,
    })
    signalData.value = data.signal
    localAction.value = data.local.action
    localEdge.value = data.local.edge ? `(${data.local.edge})` : ''
    aiPrediction.value = data.ai
  } catch {} finally { predicting.value = false }
}

async function loadPortfolio() {
  loadingPortfolio.value = true
  try {
    const { data } = await btcApi.positions()
    positions.value = data.positions || []
    const bal = data.balance
    if (bal && typeof bal === 'object') {
      const raw = bal.balance ?? bal.available ?? bal.available_balance ?? null
      usdcBalance.value = raw !== null ? Number(raw).toFixed(2) : '--'
    } else {
      usdcBalance.value = '--'
    }
  } catch {} finally { loadingPortfolio.value = false }
}

watch(aiProviders, (list) => {
  if (list.length === 1 && !aiConfigId.value) aiConfigId.value = list[0].id
})

onMounted(() => {
  loadOrders()
  loadBTCMarkets()
  loadPortfolio()
  aiApi.providers().then(({ data }) => { aiProviders.value = data }).catch(() => {})
})
</script>
