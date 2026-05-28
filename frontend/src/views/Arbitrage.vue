<template>
  <div>
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
        <el-table-column label="市场数" width="80">
          <template #default="{ row }">{{ row.markets?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" @click="expandDetail(row)">详情</el-button>
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

    <el-dialog v-model="showHelp" title="套利说明" width="650">
      <div style="line-height:1.8;font-size:14px">
        <h3>什么是 Polymarket 事件套利？</h3>
        <p>Polymarket 的一个事件（Event）下有多个互斥的市场（Market），例如"谁赢NBA总冠军"下面有"湖人赢"、"凯尔特人赢"、"勇士赢"等多个选项。这些选项的<strong>YES价格之和理论上应该等于 1.0</strong>（即100%概率）。</p>

        <h3>套利原理</h3>
        <p>当所有选项的 YES 价格之和偏离 1.0 时，就存在套利机会：</p>
        <ul>
          <li><strong>YES总和 > 1.0</strong>：说明整体价格偏高，可以卖出（SELL）YES 赚取差价</li>
          <li><strong>YES总和 < 1.0</strong>：说明整体价格偏低，可以买入（BUY）YES 赚取差价</li>
        </ul>
        <p>例如：3个选项的 YES 价格分别是 0.40、0.35、0.30，总和 = 1.05。你可以同时卖出这3个选项的 YES，总成本 1.05，但最终必有一个选项结算为 1.0，净赚 0.05。</p>

        <h3>如何操作</h3>
        <ol>
          <li>设置偏差阈值（默认 0.03 即 3%），点击"扫描"</li>
          <li>在结果中选择一个套利机会，点击"详情"查看各市场</li>
          <li>点击"执行"按钮对单个市场下单（需逐个市场操作）</li>
          <li>也可以用"AI 套利分析"让 AI 评估风险和建议</li>
        </ol>

        <h3>风险提示</h3>
        <ul>
          <li>套利需要同时买入/卖出多个市场，单边执行有价格变动风险</li>
          <li>流动性不足可能导致滑点，实际利润低于理论值</li>
          <li>交易手续费会侵蚀利润，偏差太小时不建议操作</li>
          <li>建议先用 AI 分析评估后再决定是否执行</li>
        </ul>
      </div>
    </el-dialog>

    <el-dialog v-model="showDetail" title="套利详情" width="700">
      <el-descriptions :column="2" border size="small" v-if="selected">
        <el-descriptions-item label="事件">{{ selected.title_zh || selected.title }}</el-descriptions-item>
        <el-descriptions-item label="YES总和">{{ selected.yes_sum.toFixed(4) }}</el-descriptions-item>
        <el-descriptions-item label="偏差">{{ selected.deviation.toFixed(4) }}</el-descriptions-item>
        <el-descriptions-item label="建议方向">
          <el-tag :type="selected.direction === 'SELL_YES' ? 'danger' : 'success'">{{ selected.direction }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <el-form inline size="small" style="margin:12px 0">
        <el-form-item label="执行金额 ($)">
          <el-input-number v-model="orderAmount" :min="1" :step="1" style="width:120px" />
        </el-form-item>
      </el-form>
      <el-table :data="selected?.markets || []" size="small">
        <el-table-column prop="question" label="市场" show-overflow-tooltip />
        <el-table-column label="YES价格" width="100">
          <template #default="{ row }">${{ row.yes_price.toFixed(3) }}</template>
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
import { arbitrageApi, aiApi } from '../api'
import { ElMessage } from 'element-plus'

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
  prediction.value = ''
}

function expandDetail(row: any) {
  selected.value = row
  showDetail.value = true
  prediction.value = ''
}

async function executeArb(row: any) {
  if (!row.token_ids?.length) return
  const price = row.yes_price || 0.5
  const size = Math.floor(orderAmount.value / price)
  try {
    await arbitrageApi.execute({
      token_id: row.token_ids[0],
      price,
      size,
      side: 'BUY',
      neg_risk: true,
      tick_size: row.tick_size || '0.01',
    })
    ElMessage.success(`套利下单成功: ${size} shares @ $${price.toFixed(3)}`)
  } catch {}
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

watch(aiProviders, (list) => {
  if (list.length === 1 && !aiConfigId.value) aiConfigId.value = list[0].id
})

onMounted(() => {
  aiApi.providers().then(({ data }) => { aiProviders.value = data }).catch(() => {})
})
</script>
