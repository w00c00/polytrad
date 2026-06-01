<template>
  <div class="m-opps">
    <div class="page-header">
      <button class="back-btn" @click="$router.push('/m/more')">← 返回</button>
      <span class="page-title">机会中心</span>
    </div>

    <div class="seg-tabs">
      <button v-for="t in tabs" :key="t.key" class="seg-tab" :class="{ active: tab === t.key }" @click="switchTab(t.key)">{{ t.label }}</button>
    </div>

    <div class="trade-bar">
      <span>{{ tab === 'basket' ? '预算' : tab === 'rewards' ? '单边金额' : tab === 'cross' ? '双边预算' : '买入金额' }}</span>
      <input v-model.number="quickAmount" type="number" min="1" step="1" />
      <button v-if="tab === 'rewards'" class="scan-btn danger" :disabled="busyKey === 'cancel-all'" @click="cancelAllOrders">全撤</button>
      <button class="scan-btn" @click="reload">重扫</button>
    </div>

    <div v-if="loading" class="empty-hint">扫描中...</div>
    <div v-else-if="items.length === 0" class="empty-hint">暂无机会</div>

    <div v-else class="list">
      <div v-for="(item, idx) in items" :key="item.event_slug || item.slug || item.topic || idx" class="card">
        <template v-if="tab === 'basket'">
          <div class="card-title">{{ item.title_zh || item.title }}</div>
          <div class="card-info">
            <span>毛利 ${{ Number(item.estimated_profit || 0).toFixed(2) }}</span>
            <span>{{ Number(item.estimated_profit_pct || 0).toFixed(1) }}%</span>
            <span>{{ item.direction }}</span>
            <span>{{ basketStatusLabel(item) }}</span>
            <span>完整 {{ item.integrity?.captured_count || item.markets?.length || 0 }}/{{ item.integrity?.official_count || '?' }}</span>
          </div>
          <div class="card-note risk-time">到期 {{ item.end_date_bj || '-' }}</div>
          <div class="card-note">{{ item.execution_note }}</div>
          <button class="action-btn primary" :disabled="!item.executable || item.direction !== 'BUY_YES' || busyKey === actionKey(item, 'basket')" @click="buyBasket(item)">
            {{ busyKey === actionKey(item, 'basket') ? '提交中...' : '一键买入篮子' }}
          </button>
        </template>

        <template v-else-if="tab === 'slippage'">
          <div class="card-title">{{ item.title_zh || item.title }}</div>
          <div class="card-info">
            <span>{{ item.direction }}</span>
            <span>均价 ${{ item.depth.avg_price.toFixed(4) }}</span>
            <span>冲击 {{ item.depth.slippage_pct.toFixed(2) }}%</span>
            <span>兑付毛利 ${{ Number(item.depth.gross_profit_if_win || 0).toFixed(2) }}</span>
          </div>
          <div class="card-note">到期 {{ item.end_date_bj || '-' }}，兑付 ROI {{ Number(item.depth.gross_roi_if_win_pct || 0).toFixed(1) }}%，可买 {{ item.depth.shares.toFixed(2) }} 份，24h量 ${{ Math.round(item.volume_24h).toLocaleString() }}</div>
          <button class="action-btn primary" :disabled="busyKey === actionKey(item, 'slippage')" @click="buySlippage(item)">
            {{ busyKey === actionKey(item, 'slippage') ? '提交中...' : '买入' }}
          </button>
        </template>

        <template v-else-if="tab === 'cross'">
          <div class="card-title">{{ item.topic_zh || item.topic }}</div>
          <div class="card-info">
            <span>价差 {{ (item.spread * 100).toFixed(1) }}%</span>
            <span>{{ item.executable ? `预算成本 $${Number(item.pair_depth?.total_cost || item.pair_depth?.capacity_usdc || 0).toFixed(2)}` : '观察' }}</span>
            <span>{{ item.executable ? `预算毛利 $${Number(item.pair_depth?.expected_profit || 0).toFixed(2)}` : '无正毛利' }}</span>
          </div>
          <div class="card-note">{{ item.strategy_label || item.relation_type }}；买 YES: {{ item.buy_candidate?.question_zh }}，到期 {{ item.buy_candidate?.end_date_bj || '-' }}</div>
          <div class="card-note">对冲 NO: {{ item.sell_reference?.question_zh }}，到期 {{ item.sell_reference?.end_date_bj || '-' }}</div>
          <div class="card-note">最大可盈利盘口约 ${{ Number(item.pair_depth?.max_capacity_usdc || 0).toFixed(2) }}；按当前双边预算执行。</div>
          <button class="action-btn primary" :disabled="!item.executable || busyKey === actionKey(item, 'cross-smart')" @click="buyCrossHedge(item)">
            {{ busyKey === actionKey(item, 'cross-smart') ? '提交中...' : '智能双边套利' }}
          </button>
        </template>

        <template v-else-if="tab === 'rewards'">
          <div class="card-title">{{ item.question_zh || item.question }}</div>
          <div class="card-info">
            <span>点差 {{ (item.spread * 100).toFixed(2) }}%</span>
            <span>{{ item.fit ? '达标' : '偏宽' }}</span>
          </div>
          <div class="card-note">到期 {{ item.end_date_bj || '-' }}，奖励要求 {{ item.rewards_min_size }}份 / {{ (item.rewards_max_spread * 100).toFixed(2) }}%</div>
          <button class="action-btn primary" :disabled="busyKey === actionKey(item, 'maker')" @click="quoteMaker(item)">
            {{ busyKey === actionKey(item, 'maker') ? '提交中...' : '挂双边做市' }}
          </button>
        </template>

        <template v-else-if="tab === 'resolution'">
          <div class="card-title">{{ item.question_zh || item.question }}</div>
          <div class="card-info">
            <span>YES ${{ item.yes_price.toFixed(3) }}</span>
            <span>{{ item.hours_left ?? '-' }}h</span>
            <span>{{ item.uma_status }}</span>
            <span>{{ item.can_buy ? '可下单' : '观察' }}</span>
          </div>
          <div class="card-note">结束 {{ item.end_date_bj || '-' }}</div>
          <div class="action-row">
            <button class="action-btn primary" :disabled="!item.can_buy || busyKey === actionKey(item, 'res-yes')" @click="buyOutcome(item, 0, 'YES')">买YES</button>
            <button class="action-btn primary" :disabled="!item.can_buy || !item.token_ids?.[1] || busyKey === actionKey(item, 'res-no')" @click="buyOutcome(item, 1, 'NO')">买NO</button>
          </div>
        </template>

        <template v-else-if="tab === 'btc'">
          <div class="card-title">{{ item.title_zh || item.title }}</div>
          <div class="card-info">
            <span>{{ item.series_label }}</span>
            <span>{{ item.action }}</span>
            <span>Edge {{ (item.edge * 100).toFixed(1) }}%</span>
          </div>
          <div class="card-note">UP 概率 {{ (item.signal.prob_up * 100).toFixed(1) }}%，截止 {{ item.end_time_bj || '-' }}</div>
          <button class="action-btn primary" :disabled="busyKey === actionKey(item, 'btc')" @click="buyBtcAlert(item)">
            {{ busyKey === actionKey(item, 'btc') ? '提交中...' : '买入' }}
          </button>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { arbitrageApi, opportunityApi } from '../../api'
import { ElMessage } from 'element-plus'

const tab = ref('basket')
const loading = ref(false)
const dataMap = ref<Record<string, any[]>>({})
const quickAmount = ref(10)
const busyKey = ref('')

const tabs = [
  { key: 'basket', label: '篮子' },
  { key: 'slippage', label: '滑点' },
  { key: 'cross', label: '价差' },
  { key: 'rewards', label: '做市' },
  { key: 'resolution', label: '结算' },
  { key: 'btc', label: 'BTC' },
]

const items = computed(() => dataMap.value[tab.value] || [])

async function switchTab(key: string) {
  tab.value = key
  if (!dataMap.value[key]) await loadData()
}

async function reload() {
  dataMap.value = { ...dataMap.value, [tab.value]: [] }
  await loadData()
}

async function loadData() {
  loading.value = true
  try {
    let data: any[] = []
    if (tab.value === 'basket') {
      const resp = await arbitrageApi.scan(0.03, quickAmount.value)
      data = resp.data || []
    } else if (tab.value === 'slippage') {
      const resp = await opportunityApi.slippage({ amount: quickAmount.value, max_slippage_pct: 5, min_volume_24h: 1000, max_candidates: 60 })
      data = resp.data || []
    } else if (tab.value === 'cross') {
      const resp = await opportunityApi.crossEvent({ min_spread: 0.05, max_candidates: 120, budget: quickAmount.value })
      data = resp.data || []
    } else if (tab.value === 'rewards') {
      const resp = await opportunityApi.rewards({ max_candidates: 120 })
      data = resp.data || []
    } else if (tab.value === 'resolution') {
      const resp = await opportunityApi.resolutionWatch({ hours: 12, min_volume_24h: 1000 })
      data = resp.data || []
    } else if (tab.value === 'btc') {
      const resp = await opportunityApi.btcAlerts({ min_edge: 0.04 })
      data = resp.data || []
    }
    dataMap.value = { ...dataMap.value, [tab.value]: data }
  } catch {
    dataMap.value = { ...dataMap.value, [tab.value]: [] }
  } finally {
    loading.value = false
  }
}

function actionKey(row: any, action: string) {
  return `${action}:${row?.event_slug || row?.slug || row?.token_id || row?.topic || row?.title || ''}`
}

function basketStatusLabel(item: any) {
  if (!item?.integrity?.ok) return '漏项风险'
  if (item.executable) return '可执行'
  if (item.can_shadow) return '可补腿'
  return '观察'
}

function adviceKindFromAction(action: string) {
  if (action.startsWith('res-')) return 'resolution'
  if (action === 'slippage') return 'slippage'
  if (action === 'btc') return 'btc'
  if (action === 'maker') return 'rewards'
  if (action.startsWith('cross')) return 'cross'
  return 'unknown'
}

async function confirmAdvice(item: any, kind: string, amount: number, context: any = {}) {
  const { data } = await opportunityApi.advice({ kind, item, amount, context })
  if (!data.allowed) {
    window.alert(data.confirm_text)
    return false
  }
  return window.confirm(data.confirm_text)
}

async function quickBuy(row: any, action: string, extra: any = {}) {
  const tokenId = extra.token_id || row?.token_id || row?.token_ids?.[0]
  if (!tokenId) {
    ElMessage.warning('缺少 token_id，无法下单')
    return
  }
  try {
    const ok = await confirmAdvice(row, extra.advice_kind || adviceKindFromAction(action), Number(quickAmount.value || 0), extra.advice_context || {})
    if (!ok) return
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || 'AI 风控失败')
    return
  }
  const key = actionKey(row, action)
  busyKey.value = key
  try {
    const { data } = await opportunityApi.quickBuy({
      token_id: tokenId,
      amount: quickAmount.value,
      size: extra.size || 0,
      limit_price: extra.limit_price || 0,
      order_type: extra.order_type || 'FOK',
      tick_size: row?.tick_size || extra.tick_size || '0.01',
      neg_risk: Boolean(row?.neg_risk ?? extra.neg_risk ?? false),
      market_slug: row?.slug || extra.market_slug || '',
      condition_id: row?.condition_id || extra.condition_id || '',
    })
    ElMessage.success(`订单已提交 @ $${data.price}`)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '下单失败')
  } finally {
    busyKey.value = ''
  }
}

async function buyBasket(item: any) {
  if (!item.integrity?.ok) {
    ElMessage.error(item.integrity?.note || '池子完整性未通过，禁止一键买入')
    return
  }
  const raw = window.prompt('本次篮子预算（USDC，总预算，不是单腿金额）', String(quickAmount.value))
  if (raw === null) return
  const budget = Number(raw)
  if (!Number.isFinite(budget) || budget < 5 || budget > 10000) {
    ElMessage.warning('篮子预算请输入 5 - 10000 USDC')
    return
  }
  quickAmount.value = Math.round(budget * 100) / 100
  const key = actionKey(item, 'basket')
  busyKey.value = key
  try {
    const checkResp = await opportunityApi.basketPrecheck({
      event_slug: item.event_slug,
      budget: quickAmount.value,
    })
    const check = checkResp.data
    if (!check.fillable) {
      ElMessage.warning(check.note || '当前盘口预检不可执行')
      return
    }
    const merged = { ...item, ...check, event_slug: item.event_slug, direction: item.direction || 'BUY_YES', executable: check.fillable }
    if (!await confirmAdvice(merged, 'basket', quickAmount.value, { min_profit_pct: 0.2 })) return
    const { data } = await opportunityApi.basketBuy({
      event_slug: item.event_slug,
      budget: quickAmount.value,
      min_profit_pct: 0.2,
    })
    ElMessage.success(`篮子已提交：${data.orders?.length || 0} 条`)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '篮子买入失败')
  } finally {
    busyKey.value = ''
  }
}

function buySlippage(item: any) {
  return quickBuy(item, 'slippage', {
    size: item.depth?.shares || 0,
    limit_price: item.depth?.worst_price || 0,
    advice_kind: 'slippage',
    advice_context: { max_slippage_pct: 5 },
  })
}

async function buyCrossHedge(item: any) {
  if (!item?.buy_candidate || !item?.sell_reference) {
    ElMessage.warning('缺少低价候选或高价参考')
    return
  }
  if (!item.executable) {
    ElMessage.warning(item.pair_depth?.reason || '当前可盈利双边深度不足')
    return
  }
  if (!await confirmAdvice(item, 'cross', quickAmount.value, { min_profit_pct: 0.2 })) return
  const key = actionKey(item, 'cross-smart')
  busyKey.value = key
  try {
    const { data } = await opportunityApi.crossHedgeBuy({
      buy_candidate: item.buy_candidate,
      sell_reference: item.sell_reference,
      amount: quickAmount.value,
      min_profit_pct: 0.2,
    })
    if (data.success) {
      ElMessage.success(`双边已提交：成本 $${data.depth?.total_cost}，份额 ${data.depth?.target_shares}`)
    } else {
      ElMessage.warning('双边订单未完全成功，系统已尝试撤单，请到订单页核对')
    }
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '双边套利失败')
  } finally {
    busyKey.value = ''
  }
}

function buyOutcome(item: any, idx: number, label: string) {
  if (!item.can_buy) {
    ElMessage.warning(item.trade_disabled_reason || '该临近结算市场当前不可下单')
    return
  }
  return quickBuy(item, `res-${label.toLowerCase()}`, { token_id: item.token_ids?.[idx], advice_kind: 'resolution' })
}

function buyBtcAlert(item: any) {
  const market = item.market || {}
  const idx = item.action === '买DOWN' ? 1 : 0
  return quickBuy(item, 'btc', {
    token_id: market.token_ids?.[idx],
    market_slug: market.slug || '',
    condition_id: market.condition_id || '',
    tick_size: market.tick_size || '0.01',
    neg_risk: market.neg_risk || false,
    advice_kind: 'btc',
  })
}

async function quoteMaker(item: any) {
  if (!await confirmAdvice(item, 'rewards', quickAmount.value)) return
  const key = actionKey(item, 'maker')
  busyKey.value = key
  try {
    const { data } = await opportunityApi.makerQuote({
      market_slug: item.slug,
      amount_per_side: quickAmount.value,
      improve_ticks: 0,
    })
    ElMessage.success(`做市委托已提交：${data.orders?.length || 0} 条`)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '挂单失败')
  } finally {
    busyKey.value = ''
  }
}

async function cancelAllOrders() {
  if (!window.confirm('确认撤销当前账号所有未成交挂单？')) return
  busyKey.value = 'cancel-all'
  try {
    await opportunityApi.cancelAll()
    ElMessage.success('已提交全部撤单')
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '撤单失败')
  } finally {
    busyKey.value = ''
  }
}

onMounted(loadData)
</script>

<style scoped>
.m-opps { padding: 12px; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.back-btn { background: none; border: none; font-size: 14px; color: #409eff; cursor: pointer; padding: 8px 0; }
.page-title { font-size: 16px; font-weight: bold; }
.seg-tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px; }
.seg-tab { height: 36px; border: 1px solid #dcdfe6; background: #fff; border-radius: 8px; font-size: 13px; color: #606266; }
.seg-tab.active { border-color: #409eff; color: #409eff; background: #ecf5ff; font-weight: bold; }
.trade-bar { display: flex; align-items: center; gap: 8px; background: #fff; border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; font-size: 13px; color: #606266; }
.trade-bar input { flex: 1; min-width: 0; height: 32px; border: 1px solid #dcdfe6; border-radius: 6px; padding: 0 8px; font-size: 14px; }
.scan-btn { height: 32px; border: 1px solid #409eff; color: #409eff; background: #fff; border-radius: 6px; padding: 0 12px; }
.scan-btn.danger { border-color: #f56c6c; color: #f56c6c; }
.list { display: flex; flex-direction: column; gap: 8px; }
.card { background: #fff; border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.card-title { font-size: 14px; font-weight: bold; color: #303133; margin-bottom: 8px; line-height: 1.4; }
.card-info { font-size: 13px; color: #606266; display: flex; flex-wrap: wrap; gap: 8px 14px; margin-top: 4px; }
.card-note { font-size: 12px; color: #909399; margin-top: 6px; line-height: 1.4; }
.risk-time { color: #f56c6c; }
.action-row { display: flex; gap: 8px; margin-top: 10px; }
.action-btn { margin-top: 10px; width: 100%; height: 34px; border: none; border-radius: 7px; font-size: 13px; font-weight: bold; }
.action-row .action-btn { margin-top: 0; flex: 1; }
.action-btn.primary { background: #409eff; color: #fff; }
.action-btn.warn { background: #e6a23c; color: #fff; }
.action-btn:disabled { opacity: 0.45; }
.empty-hint { text-align: center; color: #909399; padding: 40px 0; font-size: 14px; }
</style>
