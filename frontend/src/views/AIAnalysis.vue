<template>
  <div>
    <el-row :gutter="20">
      <el-col :span="14">
        <el-card>
          <template #header>AI 市场分析</template>
          <el-form label-position="top" size="small">
            <el-form-item label="AI 模型">
              <el-select v-model="form.ai_config_id" placeholder="选择模型" style="width:100%">
                <el-option v-for="p in providers" :key="p.id" :label="`${p.name} (${p.model_name})`" :value="p.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="市场 Slug">
              <el-tooltip content="slug 来自 Polymarket URL，例如 polymarket.com/event/btc-above-100k 中的 btc-above-100k" placement="top">
                <el-input v-model="form.market_slug" placeholder="从 Polymarket URL 获取，如 btc-above-100k" />
              </el-tooltip>
            </el-form-item>
            <el-form-item label="分析问题">
              <el-input v-model="form.question" type="textarea" :rows="2" placeholder="想问 AI 什么?" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="analyzing" @click="analyzeMarket" style="width:100%">分析市场</el-button>
            </el-form-item>
          </el-form>

          <el-divider>自定义分析</el-divider>
          <el-form label-position="top" size="small">
            <el-form-item label="Prompt">
              <el-input v-model="customPrompt" type="textarea" :rows="4" placeholder="输入任意分析需求..." />
            </el-form-item>
            <el-form-item>
              <el-button type="success" :loading="customAnalyzing" @click="customAnalyze" style="width:100%">发送分析</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card>
          <template #header>分析结果</template>
          <div v-if="result" style="white-space:pre-wrap;font-size:13px;line-height:1.6">{{ result }}</div>
          <div v-else style="text-align:center;color:#999;padding:60px">选择模型和市场开始分析</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted } from 'vue'
import { aiApi } from '../api'
import { ElMessage } from 'element-plus'

const providers = ref<any[]>([])
const analyzing = ref(false)
const customAnalyzing = ref(false)
const result = ref('')
const customPrompt = ref('')
const form = reactive({ ai_config_id: null as number | null, market_slug: '', question: '分析这个市场的走势和交易机会' })

async function analyzeMarket() {
  if (!form.ai_config_id || !form.market_slug) { ElMessage.warning('请选择模型和输入市场slug'); return }
  analyzing.value = true
  try {
    const { data } = await aiApi.analyzeMarket(form)
    result.value = data.analysis
  } catch {} finally { analyzing.value = false }
}

async function customAnalyze() {
  if (!form.ai_config_id || !customPrompt.value) { ElMessage.warning('请选择模型和输入prompt'); return }
  customAnalyzing.value = true
  try {
    const { data } = await aiApi.analyze({ ai_config_id: form.ai_config_id, prompt: customPrompt.value })
    result.value = data.result
  } catch {} finally { customAnalyzing.value = false }
}

watch(providers, (list) => {
  if (list.length === 1 && !form.ai_config_id) form.ai_config_id = list[0].id
})

onMounted(async () => {
  try {
    const { data } = await aiApi.providers()
    providers.value = data
    if (data.length === 1) form.ai_config_id = data[0].id
  } catch {}
})
</script>
