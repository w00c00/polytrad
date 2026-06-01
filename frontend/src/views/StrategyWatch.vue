<template>
  <div class="strategy-watch">
    <div class="page-bar">
      <div>
        <h2>策略观察</h2>
        <div class="subtle">只读信号、纸面记录和盘口评估</div>
      </div>
      <el-button type="primary" :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
    </div>

    <el-row :gutter="16">
      <el-col :span="14">
        <el-card class="panel">
          <template #header>
            <div class="panel-header">
              <span>策略模块</span>
              <el-tag type="info" effect="plain">read-only / paper</el-tag>
            </div>
          </template>
          <el-table :data="modules" size="small" height="280">
            <el-table-column prop="module_id" label="模块" width="220" show-overflow-tooltip />
            <el-table-column prop="domain" label="领域" width="110" />
            <el-table-column prop="execution_mode" label="模式" width="150" />
            <el-table-column label="风险控制" show-overflow-tooltip>
              <template #default="{ row }">{{ row.risk_controls?.join(', ') }}</template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="panel">
          <template #header>
            <div class="panel-header">
              <span>跨行业候选</span>
              <el-tag type="info" effect="plain">fit score</el-tag>
            </div>
          </template>
          <el-table :data="domainCandidates" size="small" height="320">
            <el-table-column prop="name" label="行业" width="210" show-overflow-tooltip />
            <el-table-column prop="category" label="类别" width="100" />
            <el-table-column label="评分" width="90">
              <template #default="{ row }">{{ formatPct(row.fit.score) }}</template>
            </el-table-column>
            <el-table-column label="建议" width="140">
              <template #default="{ row }">
                <el-tag :type="recommendationType(row.recommendation)" effect="plain">{{ row.recommendation }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="主要风险" show-overflow-tooltip>
              <template #default="{ row }">{{ row.fit.blocking_risks?.join(', ') || '-' }}</template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="panel">
          <template #header>
            <div class="panel-header">
              <span>纸面信号</span>
              <el-button size="small" :icon="Refresh" @click="loadSignals">刷新记录</el-button>
            </div>
          </template>
          <el-table :data="signals" size="small" height="360" highlight-current-row @row-click="selectSignal">
            <el-table-column label="策略" width="190" show-overflow-tooltip>
              <template #default="{ row }">{{ row.signal.strategy_name }}</template>
            </el-table-column>
            <el-table-column label="市场" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.signal.market_slug }}</template>
            </el-table-column>
            <el-table-column label="动作" width="80">
              <template #default="{ row }">
                <el-tag :type="actionType(row.signal.action)" effect="plain">{{ row.signal.action }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="Edge" width="90">
              <template #default="{ row }">{{ formatPct(row.signal.edge) }}</template>
            </el-table-column>
            <el-table-column label="置信" width="90">
              <template #default="{ row }">{{ formatPct(row.signal.confidence) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card class="panel">
          <template #header>纸面评估</template>
          <el-form label-position="top" size="small">
            <el-form-item label="当前信号">
              <el-input :model-value="selectedSignal?.signal?.market_slug || '未选择纸面信号'" disabled />
            </el-form-item>
            <el-form-item label="YES 当前价格">
              <el-input-number v-model="quoteForm.yes_price" :min="0" :max="1" :step="0.01" style="width:100%" />
            </el-form-item>
            <el-row :gutter="8">
              <el-col :span="12">
                <el-form-item label="Best bid">
                  <el-input-number v-model="quoteForm.best_bid" :min="0" :max="1" :step="0.01" style="width:100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="Best ask">
                  <el-input-number v-model="quoteForm.best_ask" :min="0" :max="1" :step="0.01" style="width:100%" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="8">
              <el-col :span="12">
                <el-form-item label="Spread">
                  <el-input-number v-model="quoteForm.spread" :min="0" :max="1" :step="0.01" style="width:100%" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="Liquidity">
                  <el-input-number v-model="quoteForm.liquidity" :min="0" :step="100" style="width:100%" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="结算结果">
              <el-segmented v-model="resolutionMode" :options="resolutionOptions" style="width:100%" />
            </el-form-item>
            <el-button type="primary" :icon="DataLine" :disabled="!selectedSignal" :loading="evaluating" style="width:100%" @click="evaluateSignal">
              评估纸面盈亏
            </el-button>
          </el-form>
        </el-card>

        <el-card class="panel">
          <template #header>评估结果</template>
          <el-descriptions v-if="evaluation" :column="1" border size="small">
            <el-descriptions-item label="状态">{{ evaluation.status }}</el-descriptions-item>
            <el-descriptions-item label="动作">{{ evaluation.action }}</el-descriptions-item>
            <el-descriptions-item label="入场价">{{ formatPrice(evaluation.entry_price) }}</el-descriptions-item>
            <el-descriptions-item label="估值/结算价">{{ formatPrice(evaluation.mark_price) }}</el-descriptions-item>
            <el-descriptions-item label="PnL">{{ formatSigned(evaluation.pnl) }}</el-descriptions-item>
            <el-descriptions-item label="PnL %">{{ evaluation.pnl_pct == null ? '-' : formatPct(evaluation.pnl_pct) }}</el-descriptions-item>
            <el-descriptions-item label="说明">{{ evaluation.reason }}</el-descriptions-item>
          </el-descriptions>
          <el-empty v-else description="选择纸面信号后评估" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { DataLine, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { strategyApi } from '../api'

type StrategyModule = {
  module_id: string
  domain: string
  execution_mode: string
  risk_controls: string[]
}

type PaperSignalRow = {
  id: number
  signal: {
    strategy_name: string
    market_slug: string
    token_id: string
    action: string
    edge: number
    confidence: number
    quote: Record<string, number | string | null>
  }
}

type DomainCandidate = {
  domain_id: string
  name: string
  category: string
  recommendation: string
  fit: {
    score: number
    blocking_risks: string[]
  }
}

const loading = ref(false)
const evaluating = ref(false)
const modules = ref<StrategyModule[]>([])
const domainCandidates = ref<DomainCandidate[]>([])
const signals = ref<PaperSignalRow[]>([])
const selectedSignal = ref<PaperSignalRow | null>(null)
const evaluation = ref<any>(null)
const resolutionMode = ref<'open' | 'yes' | 'no'>('open')
const resolutionOptions = [
  { label: '当前盘口', value: 'open' },
  { label: 'YES 结算', value: 'yes' },
  { label: 'NO 结算', value: 'no' },
]

const quoteForm = reactive({
  yes_price: 0.5,
  best_bid: 0.49,
  best_ask: 0.51,
  spread: 0.02,
  liquidity: 0,
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

function fillQuoteFromSignal(row: PaperSignalRow) {
  const quote = row.signal.quote || {}
  quoteForm.yes_price = numberFromQuote(quote.yes_price, 0.5)
  quoteForm.best_bid = numberFromQuote(quote.best_bid, quoteForm.yes_price)
  quoteForm.best_ask = numberFromQuote(quote.best_ask, quoteForm.yes_price)
  quoteForm.spread = numberFromQuote(quote.spread, Math.max(quoteForm.best_ask - quoteForm.best_bid, 0))
  quoteForm.liquidity = numberFromQuote(quote.liquidity, 0)
}

async function loadModules() {
  const { data } = await strategyApi.modules()
  modules.value = data.items || []
}

async function loadDomainCandidates() {
  const { data } = await strategyApi.domainCandidates()
  domainCandidates.value = data.items || []
}

async function loadSignals() {
  const { data } = await strategyApi.paperSignals(30)
  signals.value = data.items || []
  if (!selectedSignal.value && signals.value.length) {
    selectSignal(signals.value[0])
  }
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadModules(), loadDomainCandidates(), loadSignals()])
  } finally {
    loading.value = false
  }
}

function selectSignal(row: PaperSignalRow) {
  selectedSignal.value = row
  evaluation.value = null
  fillQuoteFromSignal(row)
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
  } catch {
    ElMessage.error('纸面评估失败')
  } finally {
    evaluating.value = false
  }
}

function actionType(action: string) {
  if (action === 'BUY') return 'success'
  if (action === 'SELL') return 'warning'
  if (action === 'WATCH') return 'info'
  return ''
}

function recommendationType(recommendation: string) {
  if (recommendation === 'pilot') return 'success'
  if (recommendation === 'watchlist_after_risk_fix') return 'warning'
  if (recommendation === 'research_only') return 'info'
  return 'danger'
}

function formatPct(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

function formatPrice(value: number | null) {
  return value == null ? '-' : `$${value.toFixed(3)}`
}

function formatSigned(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(3)}`
}

onMounted(loadAll)
</script>

<style scoped>
.strategy-watch {
  min-width: 960px;
}

.page-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-bar h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
}

.subtle {
  color: #6b7280;
  font-size: 13px;
  margin-top: 4px;
}

.panel {
  margin-bottom: 16px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
