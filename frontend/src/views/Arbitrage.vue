<template>
  <div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="篮子套利" name="basket">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>事件套利扫描</span>
              <div>
                <el-button size="small" @click="showHelp = true" style="margin-right:8px">套利说明</el-button>
                <span style="margin-right:8px">偏差阈值:</span>
                <el-input-number v-model="threshold" :min="0.01" :max="0.5" :step="0.01" :precision="2" size="small" style="width:100px;margin-right:8px" />
                <el-button type="primary" size="small" @click="scan" :loading="loading">扫描</el-button>
              </div>
            </div>
          </template>

          <el-table :data="results" size="small" v-loading="loading" @row-click="selectRow" highlight-current-row>
            <el-table-column label="事件" show-overflow-tooltip>
              <template #default="{ row }">{{ row.title_zh || row.title }}</template>
            </el-table-column>
            <el-table-column label="YES总和" width="100">
              <template #default="{ row }">{{ row.yes_sum.toFixed(4) }}</template>
            </el-table-column>
            <el-table-column label="偏差" width="100">
              <template #default="{ row }">{{ row.deviation.toFixed(4) }}</template>
            </el-table-column>
            <el-table-column label="方向" width="100">
              <template #default="{ row }">
                <el-tag :type="row.direction === 'SELL_YES' ? 'danger' : 'success'" size="small">{{ row.direction }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="可执行" width="90">
              <template #default="{ row }">
                <el-tag :type="row.executable ? 'success' : 'warning'" size="small">{{ row.executable ? '可买入' : '需库存' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="市场数" width="80">
              <template #default="{ row }">{{ row.markets?.length || 0 }}</template>
            </el-table-column>
            <el-table-column label="操作" width="150">
              <template #default="{ row }">
                <el-button size="small" @click.stop="expandDetail(row)">详情</el-button>
                <el-button size="small" type="primary" link @click.stop="precheckRow(row)">预检</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card style="margin-top:16px">
          <template #header>AI 套利分析</template>
          <el-row :gutter="12" align="middle">
            <el-col :span="8">
              <el-select v-model="aiConfigId" placeholder="选择AI模型" size="small" style="width:100%">
                <el-option v-for="p in aiProviders" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-col>
            <el-col :span="8">
              <el-button size="small" type="primary" @click="runPredict" :loading="predicting" :disabled="!selected || !aiConfigId" style="width:100%">AI 套利分析</el-button>
            </el-col>
          </el-row>
          <div v-if="prediction" style="margin-top:12px;white-space:pre-wrap;font-size:13px">{{ prediction }}</div>
          <div v-if="!selected" style="margin-top:8px;color:#999;font-size:12px">请先点击表格行选择一个套利机会</div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="盘口滑点" name="slippage">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>低滑点盘口</span>
              <div>
                <span style="margin-right:8px">金额</span>
                <el-input-number v-model="slippageParams.amount" :min="1" :max="1000" size="small" style="width:110px;margin-right:8px" />
                <span style="margin-right:8px">最大滑点%</span>
                <el-input-number v-model="slippageParams.max_slippage_pct" :min="0.1" :max="20" :step="0.1" size="small" style="width:110px;margin-right:8px" />
                <el-button size="small" type="primary" :loading="slippageLoading" @click="loadSlippage">扫描</el-button>
              </div>
            </div>
          </template>
          <el-table :data="slippageResults" size="small" v-loading="slippageLoading" max-height="560">
            <el-table-column label="市场" show-overflow-tooltip>
              <template #default="{ row }">{{ row.title_zh || row.title }}</template>
            </el-table-column>
            <el-table-column prop="direction" label="方向" width="70" />
            <el-table-column label="均价" width="80">
              <template #default="{ row }">${{ row.depth.avg_price.toFixed(4) }}</template>
            </el-table-column>
            <el-table-column label="最差价" width="80">
              <template #default="{ row }">${{ row.depth.worst_price.toFixed(4) }}</template>
            </el-table-column>
            <el-table-column label="滑点" width="80">
              <template #default="{ row }">{{ row.depth.slippage_pct.toFixed(2) }}%</template>
            </el-table-column>
            <el-table-column label="可买份额" width="100">
              <template #default="{ row }">{{ row.depth.shares.toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="24h量" width="110">
              <template #default="{ row }">${{ Math.round(row.volume_24h).toLocaleString() }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="同题价差" name="cross">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>跨事件同题价差</span>
              <div>
                <span style="margin-right:8px">价差</span>
                <el-input-number v-model="crossParams.min_spread" :min="0.01" :max="0.8" :step="0.01" :precision="2" size="small" style="width:100px;margin-right:8px" />
                <el-button size="small" type="primary" :loading="crossLoading" @click="loadCross">扫描</el-button>
              </div>
            </div>
          </template>
          <el-table :data="crossResults" size="small" v-loading="crossLoading" max-height="560">
            <el-table-column label="主题" show-overflow-tooltip>
              <template #default="{ row }">{{ row.topic_zh || row.topic }}</template>
            </el-table-column>
            <el-table-column label="价差" width="90">
              <template #default="{ row }">{{ (row.spread * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="低价买入候选" show-overflow-tooltip>
              <template #default="{ row }">{{ row.buy_candidate.question_zh }}</template>
            </el-table-column>
            <el-table-column label="高价参考" show-overflow-tooltip>
              <template #default="{ row }">{{ row.sell_reference.question_zh }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="奖励做市" name="rewards">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>奖励市场做市面板</span>
              <el-button size="small" type="primary" :loading="rewardsLoading" @click="loadRewards">扫描</el-button>
            </div>
          </template>
          <el-table :data="rewardsResults" size="small" v-loading="rewardsLoading" max-height="560">
            <el-table-column label="市场" show-overflow-tooltip>
              <template #default="{ row }">{{ row.question_zh || row.question }}</template>
            </el-table-column>
            <el-table-column label="买/卖" width="115">
              <template #default="{ row }">${{ row.best_bid.toFixed(3) }} / ${{ row.best_ask.toFixed(3) }}</template>
            </el-table-column>
            <el-table-column label="点差" width="80">
              <template #default="{ row }">{{ (row.spread * 100).toFixed(2) }}%</template>
            </el-table-column>
            <el-table-column label="奖励要求" width="150">
              <template #default="{ row }">{{ row.rewards_min_size }}份 / {{ (row.rewards_max_spread * 100).toFixed(2) }}%</template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.fit ? 'success' : 'warning'" size="small">{{ row.fit ? '达标' : '偏宽' }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="临近结算" name="resolution">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>临近结算 / UMA 状态</span>
              <div>
                <span style="margin-right:8px">小时</span>
                <el-input-number v-model="resolutionParams.hours" :min="1" :max="168" size="small" style="width:100px;margin-right:8px" />
                <el-button size="small" type="primary" :loading="resolutionLoading" @click="loadResolution">扫描</el-button>
              </div>
            </div>
          </template>
          <el-table :data="resolutionResults" size="small" v-loading="resolutionLoading" max-height="560">
            <el-table-column label="市场" show-overflow-tooltip>
              <template #default="{ row }">{{ row.question_zh || row.question }}</template>
            </el-table-column>
            <el-table-column label="YES" width="80">
              <template #default="{ row }">${{ row.yes_price.toFixed(3) }}</template>
            </el-table-column>
            <el-table-column label="剩余小时" width="90">
              <template #default="{ row }">{{ row.hours_left ?? '-' }}</template>
            </el-table-column>
            <el-table-column prop="end_date_bj" label="结束" width="110" />
            <el-table-column prop="uma_status" label="状态" width="120" />
            <el-table-column label="24h量" width="110">
              <template #default="{ row }">${{ Math.round(row.volume_24h).toLocaleString() }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="持仓对冲" name="hedges">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>持仓对冲建议</span>
              <el-button size="small" type="primary" :loading="hedgeLoading" @click="loadHedges">刷新</el-button>
            </div>
          </template>
          <el-table :data="hedgeResults" size="small" v-loading="hedgeLoading" max-height="560">
            <el-table-column label="持仓" show-overflow-tooltip>
              <template #default="{ row }">{{ row.title_zh || row.title }}</template>
            </el-table-column>
            <el-table-column prop="outcome" label="结果" width="90" />
            <el-table-column label="份额" width="90">
              <template #default="{ row }">{{ row.size.toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="价格" width="80">
              <template #default="{ row }">${{ row.price.toFixed(3) }}</template>
            </el-table-column>
            <el-table-column label="盈亏" width="90">
              <template #default="{ row }">{{ row.pnl >= 0 ? '+' : '' }}${{ row.pnl.toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="risk" label="类型" width="110" />
            <el-table-column prop="action" label="建议" show-overflow-tooltip />
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="BTC提醒" name="btc">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>BTC 短周期动量提醒</span>
              <div>
                <span style="margin-right:8px">最小 edge</span>
                <el-input-number v-model="btcParams.min_edge" :min="0.01" :max="0.5" :step="0.01" :precision="2" size="small" style="width:100px;margin-right:8px" />
                <el-button size="small" type="primary" :loading="btcLoading" @click="loadBtcAlerts">扫描</el-button>
                <el-button size="small" :loading="btcNotifyLoading" @click="notifyBtc">推送</el-button>
              </div>
            </div>
          </template>
          <el-table :data="btcResults" size="small" v-loading="btcLoading" max-height="560">
            <el-table-column label="市场" show-overflow-tooltip>
              <template #default="{ row }">{{ row.title_zh || row.title }}</template>
            </el-table-column>
            <el-table-column prop="series_label" label="周期" width="80" />
            <el-table-column prop="action" label="动作" width="80" />
            <el-table-column label="Edge" width="90">
              <template #default="{ row }">{{ (row.edge * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="概率" width="130">
              <template #default="{ row }">UP {{ (row.signal.prob_up * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column prop="end_time_bj" label="截止" width="110" />
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="showHelp" title="套利说明" width="650">
      <div style="line-height:1.8;font-size:14px">
        <h3>什么是 Polymarket 事件套利？</h3>
        <p>一个负风险事件下多个结果互斥，买入所有 YES 的同等份额后，理论上最终会有一个结果兑付 1 USDC。</p>

        <h3>套利原理</h3>
        <ul>
          <li><strong>YES卖价总和 < 1.0</strong>：可逐项买入全部 YES，理论到期兑付 1 USDC</li>
          <li><strong>YES买价总和 > 1.0</strong>：只有在已有库存或完整做市流程下才适合卖出全部 YES</li>
        </ul>

        <h3>风险提示</h3>
        <ul>
          <li>套利需要同时买入/卖出多个市场，单边执行有价格变动风险</li>
          <li>流动性不足可能导致滑点，实际利润低于理论值</li>
          <li>交易手续费会侵蚀利润，偏差太小时不建议操作</li>
        </ul>
      </div>
    </el-dialog>

    <el-dialog v-model="showDetail" title="套利详情" width="820">
      <el-descriptions :column="2" border size="small" v-if="selected">
        <el-descriptions-item label="事件">{{ selected.title_zh || selected.title }}</el-descriptions-item>
        <el-descriptions-item label="YES总和">{{ selected.yes_sum.toFixed(4) }}</el-descriptions-item>
        <el-descriptions-item label="偏差">{{ selected.deviation.toFixed(4) }}</el-descriptions-item>
        <el-descriptions-item label="预估毛利">{{ selected.estimated_profit_pct?.toFixed?.(2) || (selected.deviation * 100).toFixed(2) }}%</el-descriptions-item>
        <el-descriptions-item label="建议方向">
          <el-tag :type="selected.direction === 'SELL_YES' ? 'danger' : 'success'">{{ selected.direction }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="执行提示">{{ selected.execution_note || '-' }}</el-descriptions-item>
      </el-descriptions>
      <el-form inline size="small" style="margin:12px 0">
        <el-form-item label="预检预算 ($)">
          <el-input-number v-model="precheckBudget" :min="5" :step="5" style="width:120px" />
        </el-form-item>
        <el-form-item label="单腿金额 ($)">
          <el-input-number v-model="orderAmount" :min="1" :step="1" style="width:120px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="precheckLoading" @click="precheckSelectedBasket">篮子预检</el-button>
        </el-form-item>
      </el-form>
      <el-alert v-if="basketCheck" :type="basketCheck.fillable ? 'success' : 'warning'" show-icon :closable="false" style="margin-bottom:12px" :description="basketCheck.note">
        <template #title>
          成本 ${{ basketCheck.total_cost }}，理论兑付 ${{ basketCheck.payout_if_complete }}，预估毛利 ${{ basketCheck.estimated_profit }}（{{ basketCheck.estimated_profit_pct }}%）
        </template>
      </el-alert>
      <el-table :data="selected?.markets || []" size="small">
        <el-table-column label="市场" show-overflow-tooltip>
          <template #default="{ row }">{{ row.question_zh || row.question }}</template>
        </el-table-column>
        <el-table-column label="YES价格" width="100">
          <template #default="{ row }">${{ row.yes_price.toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="买/卖" width="110">
          <template #default="{ row }">${{ (row.best_ask || row.yes_price).toFixed(3) }} / ${{ (row.best_bid || row.yes_price).toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="executeArb(row)">执行</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { arbitrageApi, aiApi, opportunityApi } from '../api'
import { ElMessage } from 'element-plus'

const activeTab = ref('basket')
const loading = ref(false)
const threshold = ref(0.03)
const results = ref<any[]>([])
const showDetail = ref(false)
const showHelp = ref(false)
const selected = ref<any>(null)
const aiProviders = ref<any[]>([])
const aiConfigId = ref<number | null>(null)
const predicting = ref(false)
const prediction = ref('')
const orderAmount = ref(10)
const precheckBudget = ref(100)
const precheckLoading = ref(false)
const basketCheck = ref<any>(null)

const slippageLoading = ref(false)
const slippageParams = ref({ amount: 25, max_slippage_pct: 2, min_volume_24h: 5000, max_candidates: 120 })
const slippageResults = ref<any[]>([])

const crossLoading = ref(false)
const crossParams = ref({ min_spread: 0.08, max_candidates: 300 })
const crossResults = ref<any[]>([])

const rewardsLoading = ref(false)
const rewardsResults = ref<any[]>([])

const resolutionLoading = ref(false)
const resolutionParams = ref({ hours: 12, min_volume_24h: 1000 })
const resolutionResults = ref<any[]>([])

const hedgeLoading = ref(false)
const hedgeResults = ref<any[]>([])

const btcLoading = ref(false)
const btcNotifyLoading = ref(false)
const btcParams = ref({ min_edge: 0.04 })
const btcResults = ref<any[]>([])

async function scan() {
  loading.value = true
  try {
    const { data } = await arbitrageApi.scan(threshold.value)
    results.value = data || []
    if (results.value.length === 0) ElMessage.info('未发现套利机会')
  } catch {} finally { loading.value = false }
}

function selectRow(row: any) {
  selected.value = row
  basketCheck.value = null
  prediction.value = ''
}

function expandDetail(row: any) {
  selected.value = row
  basketCheck.value = null
  showDetail.value = true
  prediction.value = ''
}

async function precheckRow(row: any) {
  selected.value = row
  await precheckSelectedBasket()
  showDetail.value = true
}

async function precheckSelectedBasket() {
  if (!selected.value?.event_slug) return
  precheckLoading.value = true
  try {
    const { data } = await opportunityApi.basketPrecheck({ event_slug: selected.value.event_slug, budget: precheckBudget.value })
    basketCheck.value = data
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '预检失败')
  } finally { precheckLoading.value = false }
}

async function executeArb(row: any) {
  if (!row.token_ids?.length) return
  if (selected.value?.direction !== 'BUY_YES') {
    ElMessage.warning('SELL_YES 需要已有 YES 库存或完整做市流程，当前不做一键卖出')
    return
  }
  try {
    const resp = await arbitrageApi.execute({
      token_id: row.token_ids[0],
      side: 'BUY',
      neg_risk: true,
      tick_size: row.tick_size || '0.01',
      market_slug: row.slug || '',
      condition_id: row.condition_id || '',
      usdc_amount: orderAmount.value,
    })
    const d = resp.data
    ElMessage.success(`套利下单成功: $${orderAmount.value} → ${d.size} 份 @ $${d.price}`)
  } catch (err: any) {
    const raw = err?.response?.data?.detail || err?.message || '未知错误'
    ElMessage.error({ message: `下单失败: ${raw}`, duration: 5000 })
  }
}

async function runPredict() {
  if (!selected.value || !aiConfigId.value) return
  predicting.value = true
  prediction.value = ''
  try {
    const { data } = await aiApi.analyzeArbitrage({ ai_config_id: aiConfigId.value, event_slug: selected.value.event_slug, yes_sum: selected.value.yes_sum })
    prediction.value = data.analysis
  } catch {} finally { predicting.value = false }
}

async function loadSlippage() {
  slippageLoading.value = true
  try {
    const { data } = await opportunityApi.slippage(slippageParams.value)
    slippageResults.value = data || []
  } finally { slippageLoading.value = false }
}

async function loadCross() {
  crossLoading.value = true
  try {
    const { data } = await opportunityApi.crossEvent(crossParams.value)
    crossResults.value = data || []
  } finally { crossLoading.value = false }
}

async function loadRewards() {
  rewardsLoading.value = true
  try {
    const { data } = await opportunityApi.rewards()
    rewardsResults.value = data || []
  } finally { rewardsLoading.value = false }
}

async function loadResolution() {
  resolutionLoading.value = true
  try {
    const { data } = await opportunityApi.resolutionWatch(resolutionParams.value)
    resolutionResults.value = data || []
  } finally { resolutionLoading.value = false }
}

async function loadHedges() {
  hedgeLoading.value = true
  try {
    const { data } = await opportunityApi.hedges()
    hedgeResults.value = data || []
  } finally { hedgeLoading.value = false }
}

async function loadBtcAlerts() {
  btcLoading.value = true
  try {
    const { data } = await opportunityApi.btcAlerts(btcParams.value)
    btcResults.value = data || []
    if (btcResults.value.length === 0) ElMessage.info('暂无满足条件的 BTC 提醒')
  } finally { btcLoading.value = false }
}

async function notifyBtc() {
  btcNotifyLoading.value = true
  try {
    const { data } = await opportunityApi.notifyBtcAlerts(btcParams.value)
    ElMessage.success(data.message || '已推送')
  } finally { btcNotifyLoading.value = false }
}

watch(aiProviders, (list) => {
  if (list.length === 1 && !aiConfigId.value) aiConfigId.value = list[0].id
})

onMounted(() => {
  aiApi.providers().then(({ data }) => { aiProviders.value = data }).catch(() => {})
})
</script>
