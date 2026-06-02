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
      <span>{{ tradeBarLabel }}</span>
      <input v-if="tab !== 'schedule'" v-model.number="quickAmount" type="number" min="1" step="1" />
      <input v-if="tab === 'smart' || tab === 'weatherSmart'" v-model.number="smartAutoSeconds" type="number" min="0" step="5" placeholder="刷新秒" />
      <select v-if="tab === 'news' || tab === 'schedule'" v-model="aiConfigId" class="trade-select">
        <option :value="null">AI模型</option>
        <option v-for="p in aiProviders" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>
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
          <div class="action-row">
            <button class="action-btn secondary" :disabled="busyKey === actionKey(item, 'basket-advice')" @click="reviewAdvice(item, 'basket', { min_profit_pct: 0.2 })">AI风控</button>
            <button class="action-btn primary" :disabled="!item.executable || item.direction !== 'BUY_YES' || busyKey === actionKey(item, 'basket')" @click="buyBasket(item)">
              {{ busyKey === actionKey(item, 'basket') ? '提交中...' : '一键买入篮子' }}
            </button>
          </div>
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
          <div class="action-row">
            <button class="action-btn secondary" :disabled="busyKey === actionKey(item, 'slippage-advice')" @click="reviewAdvice(item, 'slippage', { max_slippage_pct: 5 })">AI风控</button>
            <button class="action-btn primary" :disabled="busyKey === actionKey(item, 'slippage')" @click="buySlippage(item)">
              {{ busyKey === actionKey(item, 'slippage') ? '提交中...' : '买入' }}
            </button>
          </div>
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
          <div class="action-row">
            <button class="action-btn secondary" :disabled="busyKey === actionKey(item, 'cross-advice')" @click="reviewAdvice(item, 'cross', { min_profit_pct: 0.2 })">AI风控</button>
            <button class="action-btn primary" :disabled="!item.executable || busyKey === actionKey(item, 'cross-smart')" @click="buyCrossHedge(item)">
              {{ busyKey === actionKey(item, 'cross-smart') ? '提交中...' : '智能双边套利' }}
            </button>
          </div>
        </template>

        <template v-else-if="tab === 'rewards'">
          <div class="card-title">{{ item.question_zh || item.question }}</div>
          <div class="card-info">
            <span>点差 {{ (item.spread * 100).toFixed(2) }}%</span>
            <span>{{ item.fit ? '达标' : '偏宽' }}</span>
          </div>
          <div class="card-note">到期 {{ item.end_date_bj || '-' }}，奖励要求 {{ item.rewards_min_size }}份 / {{ (item.rewards_max_spread * 100).toFixed(2) }}%</div>
          <div class="action-row">
            <button class="action-btn secondary" :disabled="busyKey === actionKey(item, 'rewards-advice')" @click="reviewAdvice(item, 'rewards')">AI风控</button>
            <button class="action-btn primary" :disabled="busyKey === actionKey(item, 'maker')" @click="quoteMaker(item)">
              {{ busyKey === actionKey(item, 'maker') ? '提交中...' : '挂双边做市' }}
            </button>
          </div>
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
            <button class="action-btn secondary" :disabled="busyKey === actionKey(item, 'resolution-advice')" @click="reviewAdvice(item, 'resolution')">AI</button>
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
          <div class="action-row">
            <button class="action-btn secondary" :disabled="busyKey === actionKey(item, 'btc-advice')" @click="reviewAdvice(item, 'btc')">AI风控</button>
            <button class="action-btn primary" :disabled="busyKey === actionKey(item, 'btc')" @click="buyBtcAlert(item)">
              {{ busyKey === actionKey(item, 'btc') ? '提交中...' : '买入' }}
            </button>
          </div>
        </template>

        <template v-else-if="tab === 'news'">
          <div class="card-title">{{ item.title_zh || item.title }}</div>
          <div class="card-info">
            <span>热度 {{ item.signal_level }} {{ Number(item.signal_score || 0).toFixed(0) }}</span>
            <span>新闻 {{ item.news_count }}</span>
            <span>YES ${{ Number(item.yes_price || 0).toFixed(3) }}</span>
          </div>
          <div class="card-note">{{ item.latest_headline_zh || item.latest_headline || '暂无近期新闻标题' }}</div>
          <div class="card-note">最新 {{ item.latest_news_bj || '-' }}，到期 {{ item.end_date_bj || '-' }}</div>
          <div class="action-row">
            <button class="action-btn secondary" :disabled="busyKey === actionKey(item, 'news-ai')" @click="reviewMobileAi(item, 'news')">AI复核</button>
            <button class="action-btn primary" :disabled="busyKey === actionKey(item, 'news-ai') || busyKey === actionKey(item, 'news-yes')" @click="buyNews(item, 0, 'YES')">买YES</button>
            <button class="action-btn primary" :disabled="!item.token_ids?.[1] || busyKey === actionKey(item, 'news-ai') || busyKey === actionKey(item, 'news-no')" @click="buyNews(item, 1, 'NO')">买NO</button>
          </div>
        </template>

        <template v-else-if="tab === 'schedule'">
          <div class="card-title">{{ item.title_zh || item.title }}</div>
          <div class="card-info">
            <span>{{ item.league || item.league_guess || '长期盘' }}</span>
            <span>{{ item.game_status }}</span>
            <span>{{ item.risk_level }}</span>
          </div>
          <div class="card-note">{{ item.game || item.teams || '未匹配单场赛程' }}</div>
          <div class="card-note">比赛 {{ item.game_time_bj || '-' }}，市场到期 {{ item.end_date_bj || '-' }}</div>
          <div class="card-note">YES ${{ Number(item.yes_price || 0).toFixed(3) }} / NO ${{ Number(item.no_price || 0).toFixed(3) }}</div>
          <div class="card-note">{{ item.action }}</div>
          <div class="action-row">
            <button class="action-btn secondary" :disabled="busyKey === actionKey(item, 'schedule-ai')" @click="reviewMobileAi(item, 'schedule')">AI复核</button>
            <button class="action-btn primary" :disabled="!item.can_buy || busyKey === actionKey(item, 'schedule-ai') || busyKey === actionKey(item, 'schedule-yes')" @click="buySchedule(item, 0, 'YES')">买YES</button>
            <button class="action-btn primary" :disabled="!item.can_buy || !item.token_ids?.[1] || busyKey === actionKey(item, 'schedule-ai') || busyKey === actionKey(item, 'schedule-no')" @click="buySchedule(item, 1, 'NO')">买NO</button>
          </div>
        </template>

        <template v-else-if="tab === 'smart' || tab === 'weatherSmart'">
          <div class="card-title">{{ item.pseudonym || item.name || item.wallet }}</div>
          <div class="card-info">
            <span>评分 {{ Number(item.smart_score || 0).toFixed(1) }}</span>
            <span>成交 ${{ Number(item.total_notional || 0).toFixed(0) }}</span>
            <span>{{ tab === 'weatherSmart' ? '天气胜率' : '胜率' }} {{ item.closed_win_rate == null ? '-' : `${Number(item.closed_win_rate).toFixed(1)}%` }}</span>
            <span v-if="tab === 'weatherSmart'">样本 {{ item.weather_closed_count || 0 }}</span>
          </div>
          <div class="card-note">最新 {{ tab === 'weatherSmart' ? '天气' : '' }}BUY：{{ item.last_buy_trade?.title_zh || item.last_buy_trade?.title || '-' }}</div>
          <div class="card-note">{{ item.risk_note }}</div>
          <div class="action-row">
            <button class="action-btn secondary" :disabled="busyKey === actionKey(item, 'smart-advice')" @click="reviewAdvice(smartAdviceItem(item), 'smart_money', smartAdviceContext(item))">AI风控</button>
            <button class="action-btn primary" :disabled="!item.last_buy_trade || (tab === 'weatherSmart' && !item.weather_qualified) || busyKey === actionKey(item, 'smart-follow')" @click="followSmartMoney(item)">
              {{ busyKey === actionKey(item, 'smart-follow') ? '提交中...' : (tab === 'weatherSmart' ? '跟买天气BUY' : '跟买最近BUY') }}
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { aiApi, arbitrageApi, opportunityApi } from '../../api'
import { ElMessage } from 'element-plus'

const tab = ref('basket')
const loading = ref(false)
const dataMap = ref<Record<string, any[]>>({})
const quickAmount = ref(10)
const busyKey = ref('')
const smartAutoSeconds = ref(0)
const aiConfigId = ref<number | null>(null)
const aiProviders = ref<any[]>([])
let smartAutoTimer: ReturnType<typeof setInterval> | null = null

const tabs = [
  { key: 'basket', label: '篮子' },
  { key: 'slippage', label: '滑点' },
  { key: 'cross', label: '价差' },
  { key: 'rewards', label: '做市' },
  { key: 'resolution', label: '结算' },
  { key: 'btc', label: 'BTC' },
  { key: 'news', label: '新闻' },
  { key: 'schedule', label: '赛程' },
  { key: 'smart', label: '聪明钱' },
  { key: 'weatherSmart', label: '天气跟单' },
]

const items = computed(() => dataMap.value[tab.value] || [])
const tradeBarLabel = computed(() => {
  if (tab.value === 'basket') return '预算'
  if (tab.value === 'rewards') return '单边金额'
  if (tab.value === 'cross') return '双边预算'
  if (tab.value === 'schedule') return '赛程匹配'
  if (tab.value === 'smart') return '跟买金额'
  if (tab.value === 'weatherSmart') return '天气跟买'
  return '买入金额'
})

async function switchTab(key: string) {
  tab.value = key
  if (!dataMap.value[key]) await loadData()
}

async function reload() {
  dataMap.value = { ...dataMap.value, [tab.value]: [] }
  await loadData()
}

async function loadData() {
  if (loading.value) return
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
    } else if (tab.value === 'news') {
      const resp = await opportunityApi.newsCatalysts({ category: 'politics', lookback_hours: 48, max_candidates: 16 })
      data = resp.data || []
    } else if (tab.value === 'schedule') {
      const resp = await opportunityApi.sportsSchedule({ days_ahead: 7, max_candidates: 100, include_unsupported: true })
      data = resp.data || []
    } else if (tab.value === 'smart') {
      const resp = await opportunityApi.smartMoney({ lookback_hours: 72, limit: 2500, min_notional: 10, top_wallets: 24 })
      data = resp.data?.wallets || []
    } else if (tab.value === 'weatherSmart') {
      const resp = await opportunityApi.weatherSmartMoney({
        lookback_hours: 72,
        limit: 5000,
        min_notional: 5,
        top_wallets: 24,
        min_weather_win_rate: 55,
        min_weather_closed: 2,
        qualified_only: true,
      })
      data = resp.data?.wallets || []
    }
    dataMap.value = { ...dataMap.value, [tab.value]: data }
  } catch {
    dataMap.value = { ...dataMap.value, [tab.value]: [] }
  } finally {
    loading.value = false
  }
}

function actionKey(row: any, action: string) {
  return `${action}:${row?.event_slug || row?.market_slug || row?.slug || row?.token_id || row?.wallet || row?.topic || row?.title || ''}`
}

function basketStatusLabel(item: any) {
  if (!item?.integrity?.ok) return '漏项风险'
  if (item.executable) return '可执行'
  if (item.can_shadow) return '可补腿'
  return '观察'
}

function adviceKindFromAction(action: string) {
  if (action.startsWith('res-')) return 'resolution'
  if (action.startsWith('news-')) return 'news'
  if (action.startsWith('schedule-')) return 'schedule'
  if (action.startsWith('smart')) return 'smart_money'
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

async function reviewAdvice(item: any, kind: string, context: any = {}) {
  const key = actionKey(item, `${kind}-advice`)
  busyKey.value = key
  try {
    const { data } = await opportunityApi.advice({ kind, item, amount: Number(quickAmount.value || 0), context })
    window.alert(data.confirm_text || data.summary || '没有风控结果')
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || 'AI 风控失败')
  } finally {
    busyKey.value = ''
  }
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

function buyNews(item: any, idx: number, label: string) {
  return confirmMobileAi(item, 'news', label).then((ok) => {
    if (!ok) return
    return quickBuy(item, `news-${label.toLowerCase()}`, {
      token_id: item.token_ids?.[idx],
      market_slug: item.slug || '',
      condition_id: item.condition_id || '',
      tick_size: item.tick_size || '0.01',
      neg_risk: item.neg_risk || false,
      advice_kind: 'news',
    })
  })
}

function buySchedule(item: any, idx: number, label: string) {
  if (!item.can_buy) {
    ElMessage.warning(item.trade_disabled_reason || '该赛程市场当前不可下单')
    return
  }
  return confirmMobileAi(item, 'schedule', label).then((ok) => {
    if (!ok) return
    return quickBuy(item, `schedule-${label.toLowerCase()}`, {
      token_id: item.token_ids?.[idx],
      market_slug: item.market_slug || item.slug || '',
      condition_id: item.condition_id || '',
      tick_size: item.tick_size || '0.01',
      neg_risk: item.neg_risk || false,
      advice_kind: 'schedule',
    })
  })
}

async function confirmMobileAi(item: any, kind: 'news' | 'schedule', side: string) {
  if (!aiConfigId.value) {
    ElMessage.warning('没有可用 AI 模型，已阻断新闻/赛程快捷买入')
    return false
  }
  const key = actionKey(item, `${kind}-ai`)
  const payload = {
    kind,
    side,
    title: item.title_zh || item.question_zh || item.title || item.question,
    yes_price: item.yes_price,
    no_price: item.no_price,
    end_date_bj: item.end_date_bj,
    latest_headline: item.latest_headline_zh || item.latest_headline,
    game_status: item.game_status,
    game_time_bj: item.game_time_bj,
    league: item.league || item.league_guess,
  }
  busyKey.value = key
  try {
    const { data } = await aiApi.analyze({
      ai_config_id: aiConfigId.value,
      system_prompt: '你是 Polymarket 交易前风控员，资金安全第一。必须用简体中文回答。',
      prompt: `请复核这个${kind === 'news' ? '新闻催化' : '赛程'}交易。第一行必须写：结论：通过 / 谨慎 / 禁止。若信息不足或不建议买入 ${side}，请写禁止。\n${JSON.stringify(payload, null, 2)}`,
    })
    const text = data.result || ''
    window.alert(text)
    if (/结论[:：]\s*禁止|禁止下单|不要下单|不建议/.test(text)) return false
    return window.confirm(`AI 未阻断，继续提交 ${side} FOK 买入？`)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || 'AI 复核失败')
    return false
  } finally {
    busyKey.value = ''
  }
}

async function reviewMobileAi(item: any, kind: 'news' | 'schedule') {
  if (!aiConfigId.value) {
    ElMessage.warning('没有可用 AI 模型')
    return
  }
  const key = actionKey(item, `${kind}-ai`)
  busyKey.value = key
  try {
    const { data } = await aiApi.analyze({
      ai_config_id: aiConfigId.value,
      system_prompt: '你是 Polymarket 交易前风控员，资金安全第一。必须用简体中文回答。',
      prompt: `请复核这个${kind === 'news' ? '新闻催化' : '赛程'}机会。第一行必须写：结论：通过 / 谨慎 / 禁止。判断信息是否和市场规则直接相关，以及当前价格是否值得买。\n${JSON.stringify(item, null, 2).slice(0, 6000)}`,
    })
    window.alert(data.result || 'AI 没有返回内容')
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || 'AI 复核失败')
  } finally {
    busyKey.value = ''
  }
}

function smartAdviceItem(item: any) {
  const trade = item.last_buy_trade || item
  return { ...trade, ...item, last_buy_trade: trade }
}

function smartAdviceContext(item: any) {
  if (item.category === 'weather') {
    return { wallet: item.wallet, category: 'weather', min_weather_win_rate: 55, min_weather_closed: 2 }
  }
  return { wallet: item.wallet }
}

function followSmartMoney(item: any) {
  const trade = item.last_buy_trade
  if (!trade?.token_id) {
    ElMessage.warning('没有可跟买的最近 BUY token')
    return
  }
  const adviceItem = { ...trade, ...item, last_buy_trade: trade }
  const context = item.category === 'weather'
    ? { wallet: item.wallet, category: 'weather', min_weather_win_rate: 55, min_weather_closed: 2 }
    : { wallet: item.wallet }
  return quickBuy(adviceItem, 'smart-follow', {
    token_id: trade.token_id,
    market_slug: trade.market_slug || '',
    condition_id: trade.condition_id || '',
    tick_size: '0.01',
    advice_kind: 'smart_money',
    advice_context: context,
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

function resetSmartAutoRefresh() {
  if (smartAutoTimer) {
    clearInterval(smartAutoTimer)
    smartAutoTimer = null
  }
  const seconds = Number(smartAutoSeconds.value || 0)
  if ((tab.value === 'smart' || tab.value === 'weatherSmart') && seconds >= 5) {
    smartAutoTimer = setInterval(() => {
      loadData()
    }, seconds * 1000)
  }
}

watch([smartAutoSeconds, tab], resetSmartAutoRefresh)

onMounted(() => {
  loadData()
  aiApi.providers().then(({ data }) => {
    aiProviders.value = data || []
    if (data?.[0]) aiConfigId.value = data[0].id
  }).catch(() => {})
})
onUnmounted(() => {
  if (smartAutoTimer) clearInterval(smartAutoTimer)
})
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
.trade-select { flex: 1; min-width: 0; height: 32px; border: 1px solid #dcdfe6; border-radius: 6px; padding: 0 8px; font-size: 13px; background: #fff; }
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
.action-btn.secondary { background: #ecf5ff; color: #409eff; border: 1px solid #b3d8ff; }
.action-btn.warn { background: #e6a23c; color: #fff; }
.action-btn:disabled { opacity: 0.45; }
.empty-hint { text-align: center; color: #909399; padding: 40px 0; font-size: 14px; }
</style>
