<template>
  <div class="m-sports">
    <!-- Tabs -->
    <div class="m-tabs">
      <div class="m-tab-item" :class="{ active: tab === 'games' }" @click="tab = 'games'">近期比赛</div>
      <div class="m-tab-item" :class="{ active: tab === 'champs' }" @click="tab = 'champs'">赛事冠军</div>
    </div>

    <div class="event-list">
      <div v-if="loading" class="empty-hint">加载中...</div>
      <div v-else-if="filtered.length === 0" class="empty-hint">暂无赛事</div>
      <div v-for="e in filtered" :key="e.event_slug" class="event-card" @click="selectEvent(e)">
        <div class="event-title">{{ e.title_zh || e.title }}</div>
        <div class="event-meta">
          <span v-if="e.end_date_bj">截止: {{ e.end_date_bj }}</span>
          <span>${{ (e.volume_24h || 0).toLocaleString() }}</span>
        </div>
        <div class="event-markets" v-if="selectedEvent?.event_slug === e.event_slug">
          <div v-for="m in e.markets" :key="m.slug" class="market-row" @click.stop="buyMarket(m)">
            <span class="m-name">
              <span>{{ m.question_zh || m.question }}</span>
              <small>到期 {{ m.end_date_bj || e.end_date_bj || '-' }}</small>
            </span>
            <span class="m-price">${{ (m.yes_price || 0).toFixed(3) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Order sheet -->
    <div v-if="showSheet" class="m-sheet-mask" @click.self="showSheet = false">
      <div class="m-sheet">
        <div class="sheet-header">
          <span>{{ sheetTitle }}</span>
          <span class="sheet-close" @click="showSheet = false">✕</span>
        </div>
        <div class="sheet-body">
          <div class="sheet-expiry">到期: {{ selectedMarket?.end_date_bj || selectedEvent?.end_date_bj || '-' }}</div>
          <div class="sheet-field">
            <label>方向</label>
            <div class="dir-btns">
              <button class="dir-btn up" :class="{ active: direction === 'YES' }" @click="direction = 'YES'">YES</button>
              <button class="dir-btn down" :class="{ active: direction === 'NO' }" @click="direction = 'NO'">NO</button>
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
import { sportsApi } from '../../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const events = ref<any[]>([])
const tab = ref('games')
const selectedEvent = ref<any>(null)
const showSheet = ref(false)
const selectedMarket = ref<any>(null)
const direction = ref('YES')
const amount = ref(10)
const ordering = ref(false)

const filtered = computed(() => {
  if (tab.value === 'games') return events.value.filter(e => e.is_game)
  return events.value.filter(e => !e.is_game)
})

const sheetTitle = computed(() => selectedMarket.value?.question_zh || selectedMarket.value?.question || '下单')

function selectEvent(e: any) {
  selectedEvent.value = selectedEvent.value?.event_slug === e.event_slug ? null : e
}

function buyMarket(m: any) {
  selectedMarket.value = m
  showSheet.value = true
}

async function loadEvents() {
  loading.value = true
  try {
    const { data } = await sportsApi.events()
    events.value = data || []
  } catch {} finally { loading.value = false }
}

async function placeOrder() {
  const m = selectedMarket.value
  if (!m?.token_ids?.length) { ElMessage.warning('缺少 token 信息'); return }
  const tokenId = direction.value === 'NO' ? m.token_ids[1] : m.token_ids[0]
  if (!tokenId) { ElMessage.warning('缺少对应方向 token'); return }
  ordering.value = true
  try {
    const { data } = await sportsApi.order({
      token_id: tokenId,
      side: 'BUY',
      order_type: 'GTC',
      tick_size: m.tick_size || '0.01',
      neg_risk: m.neg_risk || false,
      market_slug: m.slug || '',
      condition_id: m.condition_id || '',
      usdc_amount: amount.value,
    })
    ElMessage.success(`买入成功: $${amount.value} → ${data.size} 份 @ $${data.price}`)
    showSheet.value = false
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '下单失败')
  } finally { ordering.value = false }
}

onMounted(loadEvents)
</script>

<style scoped>
.m-sports { padding: 12px; }

.m-tabs {
  display: flex;
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

.event-list { display: flex; flex-direction: column; gap: 8px; }

.event-card {
  background: #fff;
  border-radius: 10px;
  padding: 14px 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.event-title { font-size: 14px; font-weight: bold; color: #303133; margin-bottom: 6px; }
.event-meta { font-size: 12px; color: #909399; display: flex; gap: 12px; margin-bottom: 4px; }

.event-markets {
  margin-top: 10px;
  border-top: 1px solid #f0f0f0;
  padding-top: 8px;
}

.market-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f5f5f5;
}

.market-row:last-child { border-bottom: none; }
.m-name { font-size: 13px; color: #303133; flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.m-name span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.m-name small { color: #f56c6c; font-size: 11px; font-weight: normal; }
.m-price { font-size: 13px; font-weight: bold; color: #409eff; margin-left: 8px; }

/* Sheet */
.m-sheet-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100; display: flex; align-items: flex-end; }
.m-sheet { width: 100%; background: #fff; border-radius: 16px 16px 0 0; padding-bottom: env(safe-area-inset-bottom, 16px); animation: slideUp 0.25s ease; }
@keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
.sheet-header { display: flex; justify-content: space-between; padding: 16px; font-size: 16px; font-weight: bold; border-bottom: 1px solid #f0f0f0; }
.sheet-close { font-size: 20px; color: #909399; cursor: pointer; }
.sheet-body { padding: 16px; display: flex; flex-direction: column; gap: 16px; }
.sheet-expiry { font-size: 12px; color: #f56c6c; line-height: 1.4; }
.sheet-field label { display: block; font-size: 13px; color: #606266; margin-bottom: 8px; }
.dir-btns { display: flex; gap: 8px; }
.dir-btn { flex: 1; padding: 12px; border: 2px solid #dcdfe6; border-radius: 8px; background: #fff; font-size: 14px; font-weight: bold; cursor: pointer; }
.dir-btn.up.active { border-color: #67c23a; background: #f0f9eb; color: #67c23a; }
.dir-btn.down.active { border-color: #f56c6c; background: #fef0f0; color: #f56c6c; }
.sheet-input { width: 100%; padding: 12px; border: 1px solid #dcdfe6; border-radius: 8px; font-size: 16px; box-sizing: border-box; outline: none; }
.sheet-input:focus { border-color: #409eff; }
.sheet-submit { width: 100%; padding: 14px; background: #409eff; color: #fff; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; }
.sheet-submit:disabled { opacity: 0.6; }
.empty-hint { text-align: center; color: #909399; padding: 40px 0; font-size: 14px; }
</style>
