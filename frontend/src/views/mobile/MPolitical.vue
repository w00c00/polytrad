<template>
  <div class="m-political">
    <div class="page-header">
      <button class="back-btn" @click="$router.push('/m/more')">← 返回</button>
      <span class="page-title">政治打新</span>
    </div>
    <div class="list">
      <div v-if="loading" class="empty-hint">扫描中...</div>
      <div v-else-if="events.length === 0" class="empty-hint">暂无新事件</div>
      <div v-for="e in events" :key="e.event_slug" class="card">
        <div class="card-title">{{ e.title_zh || e.title }}</div>
        <div class="card-meta">
          <span v-if="e.created_at_bj || e.start_date_bj">创建: {{ e.created_at_bj || e.start_date_bj }}</span>
          <span>到期: {{ e.end_date_bj || '-' }}</span>
        </div>
        <div class="market-list">
          <div v-for="m in e.markets" :key="m.slug" class="market-row" @click="buyMarket(m, e)">
            <span class="m-name">
              <span>{{ m.question_zh || m.question }}</span>
              <small>到期 {{ m.end_date_bj || e.end_date_bj || '-' }}</small>
            </span>
            <span class="m-price">${{ (m.yes_price || 0).toFixed(3) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showSheet" class="sheet-mask" @click.self="showSheet = false">
      <div class="sheet">
        <div class="sheet-header">
          <span>下单</span>
          <span class="sheet-close" @click="showSheet = false">✕</span>
        </div>
        <div class="sheet-body">
          <div class="sheet-title">{{ selectedMarket?.question_zh || selectedMarket?.question || selectedEvent?.title_zh || selectedEvent?.title }}</div>
          <div class="sheet-expiry">到期: {{ selectedMarket?.end_date_bj || selectedEvent?.end_date_bj || '-' }}</div>
          <div class="sheet-price">YES ${{ Number(selectedMarket?.yes_price || 0).toFixed(3) }} / NO ${{ Number(selectedMarket?.no_price || 0).toFixed(3) }}</div>
          <div class="field">
            <label>方向</label>
            <div class="dir-btns">
              <button class="dir-btn up" :class="{ active: direction === 'YES' }" @click="direction = 'YES'">YES</button>
              <button class="dir-btn down" :class="{ active: direction === 'NO' }" @click="direction = 'NO'">NO</button>
            </div>
          </div>
          <div class="field">
            <label>金额 (USDC)</label>
            <input type="number" v-model.number="amount" min="1" class="input" />
          </div>
          <div class="ai-panel">
            <div class="ai-row">
              <select v-model="aiConfigId" class="ai-select" :disabled="aiBusy">
                <option :value="null">AI模型</option>
                <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
              <label class="ai-check">
                <input v-model="aiBeforeOrder" type="checkbox" />
                下单前AI
              </label>
            </div>
            <button class="ai-btn" :disabled="aiBusy || !aiConfigId" @click="reviewOrderAi">
              {{ aiBusy ? 'AI复核中...' : 'AI复核' }}
            </button>
            <div v-if="aiResult" class="ai-result" :class="{ danger: aiBlocked }">{{ aiResult }}</div>
          </div>
          <button class="submit-btn" :disabled="ordering" @click="placeOrder">
            {{ ordering ? '下单中...' : `买入 ${direction}` }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { politicalApi } from '../../api'
import { ElMessage } from 'element-plus'
import { useMobileAiReview } from './useMobileAiReview'

const loading = ref(false)
const events = ref<any[]>([])
const showSheet = ref(false)
const selectedMarket = ref<any>(null)
const selectedEvent = ref<any>(null)
const amount = ref(10)
const ordering = ref(false)
const direction = ref('YES')
const {
  providers,
  aiConfigId,
  aiBeforeOrder,
  aiBusy,
  aiResult,
  aiBlocked,
  loadAiProviders,
  resetAiReview,
  runAiReview,
  confirmAiBeforeOrder,
} = useMobileAiReview()

async function loadData() {
  loading.value = true
  try {
    const { data } = await politicalApi.scan()
    events.value = data || []
  } catch {} finally { loading.value = false }
}

function buyMarket(m: any, e: any) {
  selectedMarket.value = m
  selectedEvent.value = e
  showSheet.value = true
  resetAiReview()
}

function currentAiPayload() {
  const m = selectedMarket.value || {}
  const e = selectedEvent.value || {}
  return {
    kind: 'political' as const,
    side: direction.value,
    amount: Number(amount.value || 0),
    title: m.question_zh || m.question || e.title_zh || e.title || '政治打新',
    question: m.question || e.title || '',
    price: Number(direction.value === 'NO' ? m.no_price || 0 : m.yes_price || 0),
    yes_price: Number(m.yes_price || 0),
    no_price: Number(m.no_price || 0),
    end_date_bj: m.end_date_bj || e.end_date_bj || '',
    market_slug: m.slug || e.event_slug || '',
    context: {
      event_title: e.title_zh || e.title,
      created_at_bj: e.created_at_bj || e.start_date_bj,
      volume_24h: e.volume_24h,
    },
  }
}

function reviewOrderAi() {
  return runAiReview(currentAiPayload())
}

async function placeOrder() {
  const m = selectedMarket.value
  if (!m?.token_ids?.length) { ElMessage.warning('缺少 token'); return }
  const tokenId = direction.value === 'NO' ? m.token_ids[1] : m.token_ids[0]
  if (!tokenId) { ElMessage.warning('缺少对应方向 token'); return }
  if (!await confirmAiBeforeOrder(currentAiPayload())) return
  ordering.value = true
  try {
    const { data } = await politicalApi.order({
      token_id: tokenId,
      side: 'BUY',
      order_type: 'GTC',
      tick_size: m.tick_size || '0.01',
      neg_risk: m.neg_risk || false,
      market_slug: m.slug || '',
      condition_id: m.condition_id || '',
      usdc_amount: amount.value,
    })
    ElMessage.success(`买入 ${direction.value} 成功: $${amount.value} → ${data.size} 份 @ $${data.price}`)
    showSheet.value = false
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '下单失败')
  } finally { ordering.value = false }
}

watch([direction, amount, selectedMarket], resetAiReview)

onMounted(() => {
  loadData()
  loadAiProviders()
})
</script>

<style scoped>
.m-political { padding: 12px; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.back-btn { background: none; border: none; font-size: 14px; color: #409eff; cursor: pointer; padding: 8px 0; }
.page-title { font-size: 16px; font-weight: bold; }
.list { display: flex; flex-direction: column; gap: 8px; }
.card { background: #fff; border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.card-title { font-size: 14px; font-weight: bold; color: #303133; margin-bottom: 6px; }
.card-meta { font-size: 12px; color: #909399; margin-bottom: 8px; display: flex; flex-wrap: wrap; gap: 8px 12px; }
.market-list { border-top: 1px solid #f0f0f0; padding-top: 8px; }
.market-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f5f5f5; cursor: pointer; }
.market-row:last-child { border-bottom: none; }
.m-name { font-size: 13px; color: #303133; flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.m-name span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.m-name small { color: #f56c6c; font-size: 11px; font-weight: normal; }
.m-price { font-size: 13px; font-weight: bold; color: #409eff; margin-left: 8px; }
.empty-hint { text-align: center; color: #909399; padding: 40px 0; font-size: 14px; }
.sheet-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100; display: flex; align-items: flex-end; }
.sheet { width: 100%; background: #fff; border-radius: 16px 16px 0 0; padding-bottom: env(safe-area-inset-bottom, 16px); animation: slideUp 0.25s ease; }
@keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
.sheet-header { display: flex; justify-content: space-between; padding: 16px; font-size: 16px; font-weight: bold; border-bottom: 1px solid #f0f0f0; }
.sheet-close { font-size: 20px; color: #909399; cursor: pointer; }
.sheet-body { padding: 16px; display: flex; flex-direction: column; gap: 16px; }
.sheet-title { font-size: 14px; font-weight: bold; color: #303133; line-height: 1.4; overflow-wrap: anywhere; }
.sheet-expiry { font-size: 12px; color: #f56c6c; line-height: 1.4; }
.sheet-price { font-size: 13px; color: #303133; font-weight: bold; }
.field label { display: block; font-size: 13px; color: #606266; margin-bottom: 6px; }
.dir-btns { display: flex; gap: 8px; }
.dir-btn { flex: 1; padding: 12px; border: 2px solid #dcdfe6; border-radius: 8px; background: #fff; font-size: 14px; font-weight: bold; cursor: pointer; }
.dir-btn.up.active { border-color: #67c23a; background: #f0f9eb; color: #67c23a; }
.dir-btn.down.active { border-color: #f56c6c; background: #fef0f0; color: #f56c6c; }
.input { width: 100%; padding: 12px; border: 1px solid #dcdfe6; border-radius: 8px; font-size: 16px; box-sizing: border-box; outline: none; }
.input:focus { border-color: #409eff; }
.submit-btn { width: 100%; padding: 14px; background: #409eff; color: #fff; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; }
.submit-btn:disabled { opacity: 0.6; }
.ai-panel { display: flex; flex-direction: column; gap: 8px; }
.ai-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; }
.ai-select { width: 100%; height: 36px; border: 1px solid #dcdfe6; border-radius: 8px; background: #fff; padding: 0 8px; font-size: 13px; }
.ai-check { display: flex; align-items: center; gap: 4px; font-size: 12px; color: #606266; white-space: nowrap; }
.ai-btn { height: 34px; border: 1px solid #409eff; color: #409eff; background: #ecf5ff; border-radius: 8px; font-size: 13px; font-weight: bold; }
.ai-btn:disabled { opacity: 0.5; }
.ai-result { max-height: 140px; overflow-y: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; line-height: 1.5; color: #303133; background: #f5f7fa; border-left: 3px solid #409eff; border-radius: 6px; padding: 8px 10px; }
.ai-result.danger { border-left-color: #f56c6c; background: #fef0f0; }
</style>
