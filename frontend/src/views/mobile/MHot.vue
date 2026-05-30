<template>
  <div class="m-hot">
    <div class="page-header">
      <button class="back-btn" @click="$router.push('/m/more')">← 返回</button>
      <span class="page-title">热门尾盘</span>
    </div>
    <div class="list">
      <div v-if="loading" class="empty-hint">扫描中...</div>
      <div v-else-if="markets.length === 0" class="empty-hint">暂无热门市场</div>
      <div v-for="m in markets" :key="m.event_slug" class="card" @click="buyMarket(m)">
        <div class="card-title">{{ m.title_zh || m.title }}</div>
        <div class="card-meta">
          <span>截止: {{ m.end_date_bj || '-' }}</span>
          <span>成交量: ${{ (m.volume_24h || 0).toLocaleString() }}</span>
        </div>
        <div class="card-prices" v-if="m.markets?.[0]">
          <span class="price-yes">YES ${{ (m.markets[0].yes_price || 0).toFixed(3) }}</span>
          <span class="price-no">NO ${{ (m.markets[0].no_price || 0).toFixed(3) }}</span>
        </div>
      </div>
    </div>

    <!-- Order sheet -->
    <div v-if="showSheet" class="sheet-mask" @click.self="showSheet = false">
      <div class="sheet">
        <div class="sheet-header">
          <span>{{ selectedMarket?.title_zh || '下单' }}</span>
          <span class="sheet-close" @click="showSheet = false">✕</span>
        </div>
        <div class="sheet-body">
          <div class="field">
            <label>金额 (USDC)</label>
            <input type="number" v-model.number="amount" min="1" class="input" />
          </div>
          <button class="submit-btn" :disabled="ordering" @click="placeOrder">
            {{ ordering ? '下单中...' : '买入 YES' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { hotApi } from '../../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const markets = ref<any[]>([])
const showSheet = ref(false)
const selectedMarket = ref<any>(null)
const amount = ref(10)
const ordering = ref(false)

async function loadMarkets() {
  loading.value = true
  try {
    const { data } = await hotApi.scan()
    markets.value = data || []
  } catch {} finally { loading.value = false }
}

function buyMarket(m: any) {
  selectedMarket.value = m
  showSheet.value = true
}

async function placeOrder() {
  const m = selectedMarket.value
  const mk = m?.markets?.[0]
  if (!mk?.token_ids?.length) { ElMessage.warning('缺少 token'); return }
  ordering.value = true
  try {
    const { data } = await hotApi.order({
      token_id: mk.token_ids[0],
      side: 'BUY',
      order_type: 'GTC',
      tick_size: mk.tick_size || '0.01',
      neg_risk: mk.neg_risk || false,
      usdc_amount: amount.value,
    })
    ElMessage.success(`买入成功: $${amount.value} → ${data.size} 份 @ $${data.price}`)
    showSheet.value = false
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '下单失败')
  } finally { ordering.value = false }
}

onMounted(loadMarkets)
</script>

<style scoped>
.m-hot { padding: 12px; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.back-btn { background: none; border: none; font-size: 14px; color: #409eff; cursor: pointer; padding: 8px 0; }
.page-title { font-size: 16px; font-weight: bold; }
.list { display: flex; flex-direction: column; gap: 8px; }
.card { background: #fff; border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); cursor: pointer; }
.card-title { font-size: 14px; font-weight: bold; color: #303133; margin-bottom: 6px; }
.card-meta { font-size: 12px; color: #909399; display: flex; gap: 12px; margin-bottom: 8px; }
.card-prices { display: flex; gap: 16px; font-size: 13px; font-weight: bold; }
.price-yes { color: #67c23a; }
.price-no { color: #f56c6c; }
.empty-hint { text-align: center; color: #909399; padding: 40px 0; font-size: 14px; }
.sheet-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100; display: flex; align-items: flex-end; }
.sheet { width: 100%; background: #fff; border-radius: 16px 16px 0 0; padding-bottom: env(safe-area-inset-bottom, 16px); animation: slideUp 0.25s ease; }
@keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
.sheet-header { display: flex; justify-content: space-between; padding: 16px; font-size: 16px; font-weight: bold; border-bottom: 1px solid #f0f0f0; }
.sheet-close { font-size: 20px; color: #909399; cursor: pointer; }
.sheet-body { padding: 16px; display: flex; flex-direction: column; gap: 16px; }
.field label { display: block; font-size: 13px; color: #606266; margin-bottom: 6px; }
.input { width: 100%; padding: 12px; border: 1px solid #dcdfe6; border-radius: 8px; font-size: 16px; box-sizing: border-box; outline: none; }
.input:focus { border-color: #409eff; }
.submit-btn { width: 100%; padding: 14px; background: #409eff; color: #fff; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; }
.submit-btn:disabled { opacity: 0.6; }
</style>
