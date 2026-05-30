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
        <div class="card-meta" v-if="e.created_at_bj || e.start_date_bj">创建: {{ e.created_at_bj || e.start_date_bj }}</div>
        <div class="market-list">
          <div v-for="m in e.markets" :key="m.slug" class="market-row" @click="buyMarket(m)">
            <span class="m-name">{{ m.question_zh || m.question }}</span>
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
          <button class="submit-btn" :disabled="ordering" @click="placeOrder">
            {{ ordering ? '下单中...' : `买入 ${direction}` }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { politicalApi } from '../../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const events = ref<any[]>([])
const showSheet = ref(false)
const selectedMarket = ref<any>(null)
const amount = ref(10)
const ordering = ref(false)
const direction = ref('YES')

async function loadData() {
  loading.value = true
  try {
    const { data } = await politicalApi.scan()
    events.value = data || []
  } catch {} finally { loading.value = false }
}

function buyMarket(m: any) {
  selectedMarket.value = m
  showSheet.value = true
}

async function placeOrder() {
  const m = selectedMarket.value
  if (!m?.token_ids?.length) { ElMessage.warning('缺少 token'); return }
  const tokenId = direction.value === 'NO' ? m.token_ids[1] : m.token_ids[0]
  if (!tokenId) { ElMessage.warning('缺少对应方向 token'); return }
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

onMounted(loadData)
</script>

<style scoped>
.m-political { padding: 12px; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.back-btn { background: none; border: none; font-size: 14px; color: #409eff; cursor: pointer; padding: 8px 0; }
.page-title { font-size: 16px; font-weight: bold; }
.list { display: flex; flex-direction: column; gap: 8px; }
.card { background: #fff; border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.card-title { font-size: 14px; font-weight: bold; color: #303133; margin-bottom: 6px; }
.card-meta { font-size: 12px; color: #909399; margin-bottom: 8px; }
.market-list { border-top: 1px solid #f0f0f0; padding-top: 8px; }
.market-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f5f5f5; cursor: pointer; }
.market-row:last-child { border-bottom: none; }
.m-name { font-size: 13px; color: #303133; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.m-price { font-size: 13px; font-weight: bold; color: #409eff; margin-left: 8px; }
.empty-hint { text-align: center; color: #909399; padding: 40px 0; font-size: 14px; }
.sheet-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100; display: flex; align-items: flex-end; }
.sheet { width: 100%; background: #fff; border-radius: 16px 16px 0 0; padding-bottom: env(safe-area-inset-bottom, 16px); animation: slideUp 0.25s ease; }
@keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
.sheet-header { display: flex; justify-content: space-between; padding: 16px; font-size: 16px; font-weight: bold; border-bottom: 1px solid #f0f0f0; }
.sheet-close { font-size: 20px; color: #909399; cursor: pointer; }
.sheet-body { padding: 16px; display: flex; flex-direction: column; gap: 16px; }
.field label { display: block; font-size: 13px; color: #606266; margin-bottom: 6px; }
.dir-btns { display: flex; gap: 8px; }
.dir-btn { flex: 1; padding: 12px; border: 2px solid #dcdfe6; border-radius: 8px; background: #fff; font-size: 14px; font-weight: bold; cursor: pointer; }
.dir-btn.up.active { border-color: #67c23a; background: #f0f9eb; color: #67c23a; }
.dir-btn.down.active { border-color: #f56c6c; background: #fef0f0; color: #f56c6c; }
.input { width: 100%; padding: 12px; border: 1px solid #dcdfe6; border-radius: 8px; font-size: 16px; box-sizing: border-box; outline: none; }
.input:focus { border-color: #409eff; }
.submit-btn { width: 100%; padding: 14px; background: #409eff; color: #fff; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; }
.submit-btn:disabled { opacity: 0.6; }
</style>
