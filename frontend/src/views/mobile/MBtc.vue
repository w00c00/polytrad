<template>
  <div class="m-btc">
    <!-- Tab selector -->
    <div class="m-tabs">
      <div v-for="t in timeTabs" :key="t.key" class="m-tab-item" :class="{ active: activeTab === t.key }" @click="activeTab = t.key">
        {{ t.label }}
      </div>
    </div>

    <!-- Market list -->
    <div class="market-list">
      <div v-if="loading" class="empty-hint">加载中...</div>
      <div v-else-if="filteredMarkets.length === 0" class="empty-hint">暂无市场</div>
      <div v-for="m in filteredMarkets" :key="m.event_slug" class="market-card" @click="selectMarket(m)">
        <div class="market-title">{{ m.title_zh || m.title }}</div>
        <div class="market-time">{{ m.start_time_bj }} ~ {{ m.end_time_bj }}</div>
        <div class="market-prices">
          <span class="price-up">UP ${{ getYesPrice(m) }}</span>
          <span class="price-down">DOWN ${{ getNoPrice(m) }}</span>
        </div>
      </div>
    </div>

    <!-- Order sheet -->
    <div v-if="showSheet" class="m-sheet-mask" @click.self="showSheet = false">
      <div class="m-sheet">
        <div class="sheet-header">
          <span>{{ selectedMarket?.title_zh || '下单' }}</span>
          <span class="sheet-close" @click="showSheet = false">✕</span>
        </div>

        <div class="sheet-body">
          <div class="sheet-field">
            <label>方向</label>
            <div class="dir-btns">
              <button class="dir-btn up" :class="{ active: direction === 'UP' }" @click="direction = 'UP'">UP (YES)</button>
              <button class="dir-btn down" :class="{ active: direction === 'DOWN' }" @click="direction = 'DOWN'">DOWN (NO)</button>
            </div>
          </div>

          <div class="sheet-field">
            <label>金额 (USDC)</label>
            <input type="number" v-model.number="amount" min="1" class="sheet-input" />
          </div>

          <button class="sheet-submit" :disabled="ordering" @click="placeOrder">
            {{ ordering ? '下单中...' : `买入 ${direction}` }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { btcApi } from '../../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const markets = ref<any[]>([])
const activeTab = ref('15m')
const showSheet = ref(false)
const selectedMarket = ref<any>(null)
const direction = ref('UP')
const amount = ref(10)
const ordering = ref(false)

const timeTabs = [
  { key: '5m', label: '5分钟' },
  { key: '15m', label: '15分钟' },
  { key: '1h', label: '1小时' },
  { key: '4h', label: '4小时' },
  { key: '1d', label: '1天' },
]

const filteredMarkets = computed(() => {
  const labelMap: Record<string, string> = { '5m': '5分钟', '15m': '15分钟', '1h': '1小时', '4h': '4小时', '1d': '1天' }
  const label = labelMap[activeTab.value]
  return markets.value.filter(m => m.series_label === label)
})

function getYesPrice(m: any) {
  const mk = m.markets?.[0]
  return mk ? mk.yes_price.toFixed(3) : '-'
}

function getNoPrice(m: any) {
  const mk = m.markets?.[0]
  return mk ? mk.no_price.toFixed(3) : '-'
}

function selectMarket(m: any) {
  selectedMarket.value = m
  showSheet.value = true
}

async function loadMarkets() {
  loading.value = true
  try {
    const { data } = await btcApi.markets()
    markets.value = data.short_markets || []
  } catch {} finally { loading.value = false }
}

async function placeOrder() {
  const m = selectedMarket.value
  if (!m) return
  const mk = m.markets?.[0]
  if (!mk?.token_ids?.length) { ElMessage.warning('缺少 token 信息'); return }
  const tokenId = direction.value === 'DOWN' ? mk.token_ids[1] : mk.token_ids[0]
  if (!tokenId) { ElMessage.warning('缺少对应方向 token'); return }
  ordering.value = true
  try {
    const { data } = await btcApi.order({
      token_id: tokenId,
      side: 'BUY',
      order_type: 'GTC',
      tick_size: mk.tick_size || '0.01',
      neg_risk: mk.neg_risk || false,
      market_slug: mk.slug || m.event_slug || '',
      condition_id: mk.condition_id || '',
      usdc_amount: amount.value,
    })
    ElMessage.success(`买入成功: $${amount.value} → ${data.size} 份 @ $${data.price}`)
    showSheet.value = false
  } catch (err: any) {
    const msg = err?.response?.data?.detail || err?.message || '下单失败'
    ElMessage.error(msg)
  } finally { ordering.value = false }
}

onMounted(loadMarkets)
</script>

<style scoped>
.m-btc {
  padding: 12px;
}

.m-tabs {
  display: flex;
  gap: 0;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 12px;
}

.m-tab-item {
  flex: 1;
  text-align: center;
  padding: 10px 0;
  font-size: 13px;
  color: #606266;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  -webkit-tap-highlight-color: transparent;
}

.m-tab-item.active {
  color: #409eff;
  border-bottom-color: #409eff;
  font-weight: bold;
}

.market-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.market-card {
  background: #fff;
  border-radius: 10px;
  padding: 14px 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.market-title {
  font-size: 14px;
  font-weight: bold;
  color: #303133;
  margin-bottom: 6px;
}

.market-time {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.market-prices {
  display: flex;
  gap: 20px;
  font-size: 13px;
  font-weight: bold;
}

.price-up { color: #67c23a; }
.price-down { color: #f56c6c; }

/* Sheet */
.m-sheet-mask {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  z-index: 100;
  display: flex;
  align-items: flex-end;
}

.m-sheet {
  width: 100%;
  background: #fff;
  border-radius: 16px 16px 0 0;
  padding: 0 0 env(safe-area-inset-bottom, 16px);
  animation: slideUp 0.25s ease;
}

@keyframes slideUp {
  from { transform: translateY(100%); }
  to { transform: translateY(0); }
}

.sheet-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  font-size: 16px;
  font-weight: bold;
  border-bottom: 1px solid #f0f0f0;
}

.sheet-close {
  font-size: 20px;
  color: #909399;
  cursor: pointer;
}

.sheet-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sheet-field label {
  display: block;
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}

.dir-btns {
  display: flex;
  gap: 8px;
}

.dir-btn {
  flex: 1;
  padding: 12px;
  border: 2px solid #dcdfe6;
  border-radius: 8px;
  background: #fff;
  font-size: 14px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s;
}

.dir-btn.up.active {
  border-color: #67c23a;
  background: #f0f9eb;
  color: #67c23a;
}

.dir-btn.down.active {
  border-color: #f56c6c;
  background: #fef0f0;
  color: #f56c6c;
}

.sheet-input {
  width: 100%;
  padding: 12px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  font-size: 16px;
  box-sizing: border-box;
  outline: none;
}

.sheet-input:focus {
  border-color: #409eff;
}

.sheet-submit {
  width: 100%;
  padding: 14px;
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
}

.sheet-submit:disabled {
  opacity: 0.6;
}

.empty-hint {
  text-align: center;
  color: #909399;
  padding: 40px 0;
  font-size: 14px;
}
</style>
