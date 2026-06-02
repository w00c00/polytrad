<template>
  <div class="m-strategy">
    <div class="page-header">
      <button class="back-btn" @click="$router.push('/m/more')">← 返回</button>
      <span class="page-title">策略观察</span>
      <button class="scan-btn" :disabled="loading" @click="loadAll">{{ loading ? '刷新中' : '刷新' }}</button>
    </div>

    <div class="seg-tabs">
      <button v-for="t in tabs" :key="t.key" class="seg-tab" :class="{ active: tab === t.key }" @click="tab = t.key">{{ t.label }}</button>
    </div>

    <div v-if="loading && activeItems.length === 0" class="empty-hint">加载中...</div>

    <div v-else-if="tab === 'modules'" class="list">
      <div v-for="item in modules" :key="item.module_id" class="card">
        <div class="card-title">{{ item.name || item.module_id }}</div>
        <div class="card-info">
          <span>{{ item.domain }}</span>
          <span>{{ item.execution_mode }}</span>
          <span>{{ item.status || 'paper' }}</span>
        </div>
        <div class="card-note">{{ item.summary }}</div>
        <div class="chip-row">
          <span v-for="risk in (item.risk_controls || []).slice(0, 4)" :key="risk" class="chip">{{ risk }}</span>
        </div>
      </div>
    </div>

    <div v-else-if="tab === 'domains'" class="list">
      <div v-for="item in domains" :key="item.domain_id" class="card">
        <div class="card-title">{{ item.name }}</div>
        <div class="card-info">
          <span>{{ item.category }}</span>
          <span>评分 {{ formatPct(item.fit?.score) }}</span>
          <span>{{ item.recommendation }}</span>
        </div>
        <div class="card-note">{{ (item.fit?.blocking_risks || []).join(' / ') || item.fit?.reason || '-' }}</div>
      </div>
    </div>

    <div v-else class="list">
      <div v-if="signals.length === 0" class="empty-hint">暂无纸面信号</div>
      <div v-for="row in signals" :key="row.id" class="card" :class="{ selected: selectedSignal?.id === row.id }" @click="selectSignal(row)">
        <div class="card-title">{{ row.signal?.strategy_name || '-' }}</div>
        <div class="card-note">{{ row.signal?.market_slug || '-' }}</div>
        <div class="card-info">
          <span>{{ row.signal?.action }}</span>
          <span>Edge {{ formatPct(row.signal?.edge) }}</span>
          <span>置信 {{ formatPct(row.signal?.confidence) }}</span>
        </div>
      </div>

      <div class="card eval-card">
        <div class="card-title">纸面评估</div>
        <div class="form-row">
          <label>YES 当前价</label>
          <input v-model.number="quoteForm.yes_price" type="number" min="0" max="1" step="0.01" />
        </div>
        <div class="form-grid">
          <div class="form-row">
            <label>Best bid</label>
            <input v-model.number="quoteForm.best_bid" type="number" min="0" max="1" step="0.01" />
          </div>
          <div class="form-row">
            <label>Best ask</label>
            <input v-model.number="quoteForm.best_ask" type="number" min="0" max="1" step="0.01" />
          </div>
        </div>
        <div class="form-grid">
          <div class="form-row">
            <label>Spread</label>
            <input v-model.number="quoteForm.spread" type="number" min="0" max="1" step="0.01" />
          </div>
          <div class="form-row">
            <label>Liquidity</label>
            <input v-model.number="quoteForm.liquidity" type="number" min="0" step="100" />
          </div>
        </div>
        <div class="mode-row">
          <button v-for="m in resolutionModes" :key="m.value" class="mode-btn" :class="{ active: resolutionMode === m.value }" @click="resolutionMode = m.value">{{ m.label }}</button>
        </div>
        <button class="action-btn primary" :disabled="!selectedSignal || evaluating" @click="evaluateSignal">
          {{ evaluating ? '评估中...' : '评估纸面盈亏' }}
        </button>
        <div v-if="evaluation" class="eval-result">
          <div><span>状态</span><strong>{{ evaluation.status }}</strong></div>
          <div><span>动作</span><strong>{{ evaluation.action }}</strong></div>
          <div><span>入场价</span><strong>{{ formatPrice(evaluation.entry_price) }}</strong></div>
          <div><span>估值/结算</span><strong>{{ formatPrice(evaluation.mark_price) }}</strong></div>
          <div><span>PnL</span><strong :class="{ good: evaluation.pnl >= 0, bad: evaluation.pnl < 0 }">{{ formatSigned(evaluation.pnl) }}</strong></div>
          <div><span>PnL %</span><strong>{{ evaluation.pnl_pct == null ? '-' : formatPct(evaluation.pnl_pct) }}</strong></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { strategyApi } from '../../api'

const tab = ref<'modules' | 'domains' | 'signals'>('modules')
const loading = ref(false)
const evaluating = ref(false)
const modules = ref<any[]>([])
const domains = ref<any[]>([])
const signals = ref<any[]>([])
const selectedSignal = ref<any | null>(null)
const evaluation = ref<any>(null)
const resolutionMode = ref<'open' | 'yes' | 'no'>('open')

const tabs = [
  { key: 'modules', label: '模块' },
  { key: 'domains', label: '候选' },
  { key: 'signals', label: '纸面' },
] as const

const resolutionModes = [
  { label: '当前盘口', value: 'open' },
  { label: 'YES结算', value: 'yes' },
  { label: 'NO结算', value: 'no' },
] as const

const quoteForm = reactive({
  yes_price: 0.5,
  best_bid: 0.49,
  best_ask: 0.51,
  spread: 0.02,
  liquidity: 0,
})

const activeItems = computed(() => {
  if (tab.value === 'modules') return modules.value
  if (tab.value === 'domains') return domains.value
  return signals.value
})

const resolvedYes = computed(() => {
  if (resolutionMode.value === 'yes') return true
  if (resolutionMode.value === 'no') return false
  return null
})

function numberFromQuote(value: unknown, fallback: number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function fillQuoteFromSignal(row: any) {
  const quote = row?.signal?.quote || {}
  quoteForm.yes_price = numberFromQuote(quote.yes_price, 0.5)
  quoteForm.best_bid = numberFromQuote(quote.best_bid, quoteForm.yes_price)
  quoteForm.best_ask = numberFromQuote(quote.best_ask, quoteForm.yes_price)
  quoteForm.spread = numberFromQuote(quote.spread, Math.max(quoteForm.best_ask - quoteForm.best_bid, 0))
  quoteForm.liquidity = numberFromQuote(quote.liquidity, 0)
}

function selectSignal(row: any) {
  selectedSignal.value = row
  evaluation.value = null
  fillQuoteFromSignal(row)
}

async function loadAll() {
  loading.value = true
  try {
    const [moduleResp, domainResp, signalResp] = await Promise.all([
      strategyApi.modules(),
      strategyApi.domainCandidates(),
      strategyApi.paperSignals(30),
    ])
    modules.value = moduleResp.data?.items || []
    domains.value = domainResp.data?.items || []
    signals.value = signalResp.data?.items || []
    if (!selectedSignal.value && signals.value.length) selectSignal(signals.value[0])
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '策略观察加载失败')
  } finally {
    loading.value = false
  }
}

async function evaluateSignal() {
  if (!selectedSignal.value) return
  evaluating.value = true
  try {
    const currentQuote = {
      market_slug: selectedSignal.value.signal.market_slug,
      token_id: selectedSignal.value.signal.token_id,
      yes_price: quoteForm.yes_price,
      best_bid: quoteForm.best_bid,
      best_ask: quoteForm.best_ask,
      spread: quoteForm.spread,
      liquidity: quoteForm.liquidity,
    }
    const { data } = await strategyApi.paperEvaluate({
      signal: selectedSignal.value.signal,
      current_quote: currentQuote,
      resolved_yes: resolvedYes.value,
    })
    evaluation.value = data
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '纸面评估失败')
  } finally {
    evaluating.value = false
  }
}

function formatPct(value: unknown) {
  const num = Number(value || 0)
  return `${(num * 100).toFixed(1)}%`
}

function formatPrice(value: number | null) {
  return value == null ? '-' : `$${Number(value).toFixed(3)}`
}

function formatSigned(value: number) {
  const num = Number(value || 0)
  return `${num >= 0 ? '+' : ''}${num.toFixed(3)}`
}

onMounted(loadAll)
</script>

<style scoped>
.m-strategy { padding: 12px; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.back-btn { background: none; border: none; font-size: 14px; color: #409eff; cursor: pointer; padding: 8px 0; }
.page-title { flex: 1; font-size: 16px; font-weight: bold; }
.scan-btn { height: 32px; border: 1px solid #409eff; color: #409eff; background: #fff; border-radius: 6px; padding: 0 12px; }
.seg-tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px; }
.seg-tab { height: 36px; border: 1px solid #dcdfe6; background: #fff; border-radius: 8px; font-size: 13px; color: #606266; }
.seg-tab.active { border-color: #409eff; color: #409eff; background: #ecf5ff; font-weight: bold; }
.list { display: flex; flex-direction: column; gap: 8px; }
.card { background: #fff; border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.card.selected { border: 1px solid #409eff; }
.card-title { font-size: 14px; font-weight: bold; color: #303133; margin-bottom: 8px; line-height: 1.4; overflow-wrap: anywhere; }
.card-info { font-size: 13px; color: #606266; display: flex; flex-wrap: wrap; gap: 8px 14px; }
.card-note { font-size: 12px; color: #909399; margin-top: 6px; line-height: 1.4; overflow-wrap: anywhere; }
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.chip { font-size: 11px; color: #409eff; background: #ecf5ff; border: 1px solid #d9ecff; border-radius: 999px; padding: 3px 7px; max-width: 100%; overflow-wrap: anywhere; }
.eval-card { margin-top: 4px; }
.form-row { display: flex; flex-direction: column; gap: 5px; margin-top: 10px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.form-row label { font-size: 12px; color: #606266; }
.form-row input { width: 100%; box-sizing: border-box; height: 34px; border: 1px solid #dcdfe6; border-radius: 6px; padding: 0 8px; font-size: 14px; }
.mode-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
.mode-btn { height: 32px; border: 1px solid #dcdfe6; background: #fff; border-radius: 6px; font-size: 12px; color: #606266; }
.mode-btn.active { border-color: #409eff; color: #409eff; background: #ecf5ff; }
.action-btn { margin-top: 12px; width: 100%; height: 34px; border: none; border-radius: 7px; font-size: 13px; font-weight: bold; }
.action-btn.primary { background: #409eff; color: #fff; }
.action-btn:disabled { opacity: 0.45; }
.eval-result { margin-top: 12px; border-top: 1px solid #ebeef5; padding-top: 8px; display: grid; gap: 7px; font-size: 13px; }
.eval-result div { display: flex; justify-content: space-between; gap: 10px; }
.eval-result span { color: #909399; }
.eval-result strong { color: #303133; }
.eval-result strong.good { color: #67c23a; }
.eval-result strong.bad { color: #f56c6c; }
.empty-hint { text-align: center; color: #909399; padding: 40px 0; font-size: 14px; }
</style>
