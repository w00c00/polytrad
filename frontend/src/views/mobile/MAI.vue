<template>
  <div class="m-ai">
    <div class="m-card">
      <div class="card-title">AI 预测分析</div>

      <div class="field">
        <label>AI 模型</label>
        <select v-model="aiConfigId" class="m-select">
          <option :value="null" disabled>选择模型</option>
          <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </div>

      <div class="field">
        <label>市场类型</label>
        <div class="type-btns">
          <button class="type-btn" :class="{ active: predType === 'btc' }" @click="predType = 'btc'">BTC 短周期</button>
          <button class="type-btn" :class="{ active: predType === 'market' }" @click="predType = 'market'">其他市场</button>
        </div>
      </div>

      <div v-if="predType === 'btc'" class="field">
        <label>时间周期</label>
        <div class="type-btns">
          <button v-for="h in horizons" :key="h.value" class="type-btn small" :class="{ active: horizon === h.value }" @click="horizon = h.value">
            {{ h.label }}
          </button>
        </div>
      </div>

      <div v-if="predType === 'market'" class="field">
        <label>市场 Slug</label>
        <input v-model="marketSlug" class="m-input" placeholder="输入 Polymarket slug" />
      </div>

      <button class="run-btn" :disabled="!aiConfigId || predicting" @click="runPredict">
        {{ predicting ? '分析中...' : '开始分析' }}
      </button>
    </div>

    <!-- Result -->
    <div v-if="result" class="m-card result-card">
      <div class="card-title">分析结果</div>
      <div class="result-content">{{ result }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { btcApi, aiApi } from '../../api'
import { ElMessage } from 'element-plus'

const providers = ref<any[]>([])
const aiConfigId = ref<number | null>(null)
const predType = ref('btc')
const horizon = ref(15)
const marketSlug = ref('')
const predicting = ref(false)
const result = ref('')

const horizons = [
  { value: 5, label: '5分钟' },
  { value: 15, label: '15分钟' },
  { value: 60, label: '1小时' },
  { value: 240, label: '4小时' },
]

async function runPredict() {
  if (!aiConfigId.value) return
  predicting.value = true
  result.value = ''
  try {
    if (predType.value === 'btc') {
      const { data } = await btcApi.predict({
        ai_config_id: aiConfigId.value,
        horizon_minutes: horizon.value,
      })
      result.value = data.ai || '无分析结果'
    } else {
      if (!marketSlug.value) { ElMessage.warning('请输入 slug'); return }
      const { data } = await aiApi.analyzeMarket({
        ai_config_id: aiConfigId.value,
        market_slug: marketSlug.value,
        question: '分析这个市场的交易机会。',
      })
      result.value = data.analysis || '无分析结果'
    }
  } catch (err: any) {
    result.value = `分析失败: ${err?.response?.data?.detail || err?.message || '未知错误'}`
  } finally { predicting.value = false }
}

onMounted(async () => {
  try {
    const { data } = await aiApi.providers()
    providers.value = data
    if (data.length === 1) aiConfigId.value = data[0].id
  } catch {}
})
</script>

<style scoped>
.m-ai { padding: 12px; display: flex; flex-direction: column; gap: 12px; }

.m-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.card-title { font-size: 15px; font-weight: bold; color: #303133; margin-bottom: 14px; }

.field { margin-bottom: 14px; }
.field label { display: block; font-size: 13px; color: #606266; margin-bottom: 6px; }

.m-select {
  width: 100%;
  padding: 10px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  font-size: 14px;
  background: #fff;
  box-sizing: border-box;
}

.m-input {
  width: 100%;
  padding: 10px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  font-size: 14px;
  box-sizing: border-box;
  outline: none;
}

.m-input:focus { border-color: #409eff; }

.type-btns { display: flex; gap: 6px; flex-wrap: wrap; }

.type-btn {
  padding: 8px 14px;
  border: 2px solid #dcdfe6;
  border-radius: 8px;
  background: #fff;
  font-size: 13px;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.type-btn.small { padding: 6px 10px; font-size: 12px; }
.type-btn.active { border-color: #409eff; color: #409eff; background: #ecf5ff; font-weight: bold; }

.run-btn {
  width: 100%;
  padding: 14px;
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
}

.run-btn:disabled { opacity: 0.6; }

.result-content {
  font-size: 13px;
  line-height: 1.7;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
