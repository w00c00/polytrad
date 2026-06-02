import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { aiApi, btcApi } from '../../api'

type ReviewPayload = {
  kind: 'btc' | 'sports' | 'hot' | 'political'
  side: string
  amount: number
  title: string
  question?: string
  price?: number
  yes_price?: number
  no_price?: number
  end_date_bj?: string
  horizon_minutes?: number
  market_slug?: string
  context?: Record<string, any>
}

function blockedByText(text: string) {
  return /AI 分析失败|结论[:：]\s*禁止|禁止下单|不要下单|不建议.{0,12}(买入|下单|操作)|交易建议[:：]\s*观望|建议[:：]\s*观望|信息不足/.test(text)
}

function directionConflict(text: string, side: string) {
  if (side === 'UP') return /买DOWN|做空|下跌概率更高|不建议.{0,10}UP/.test(text)
  if (side === 'DOWN') return /买UP|做多|上涨概率更高|不建议.{0,10}DOWN/.test(text)
  if (side === 'YES') return /买NO|买入NO|不建议.{0,10}YES/.test(text)
  if (side === 'NO') return /买YES|买入YES|不建议.{0,10}NO/.test(text)
  return false
}

function compactPayload(payload: ReviewPayload) {
  return {
    market_type: payload.kind,
    intended_side: payload.side,
    amount_usdc: payload.amount,
    title: payload.title,
    question: payload.question,
    current_price: payload.price,
    yes_price: payload.yes_price,
    no_price: payload.no_price,
    end_date_bj: payload.end_date_bj,
    market_slug: payload.market_slug,
    context: payload.context || {},
  }
}

function reviewPrompt(payload: ReviewPayload) {
  return [
    '请对这笔移动端 Polymarket 下单做交易前 AI 风控。',
    `用户准备买入方向：${payload.side}，金额：${payload.amount} USDC。`,
    '第一行必须严格写：结论：通过 / 谨慎 / 禁止。',
    `如果信息不足、价格没有优势、到期/赛程/新闻无法确认、或不应该买 ${payload.side}，第一行必须写“结论：禁止”。`,
    '然后用简体中文给出 3 条以内理由、关键风险、建议操作。',
    JSON.stringify(compactPayload(payload), null, 2),
  ].join('\n')
}

export function useMobileAiReview() {
  const providers = ref<any[]>([])
  const aiConfigId = ref<number | null>(null)
  const aiBeforeOrder = ref(true)
  const aiBusy = ref(false)
  const aiResult = ref('')
  const aiBlocked = ref(false)

  async function loadAiProviders() {
    try {
      const { data } = await aiApi.providers()
      providers.value = data || []
      if (!aiConfigId.value && providers.value.length) aiConfigId.value = providers.value[0].id
    } catch {
      providers.value = []
    }
  }

  function resetAiReview() {
    aiResult.value = ''
    aiBlocked.value = false
  }

  async function runAiReview(payload: ReviewPayload) {
    if (!aiConfigId.value) {
      ElMessage.warning('没有可用 AI 模型，请先在设置里配置')
      return null
    }
    aiBusy.value = true
    aiResult.value = ''
    aiBlocked.value = false
    try {
      if (payload.kind === 'btc') {
        const { data } = await btcApi.predict({
          ai_config_id: aiConfigId.value,
          horizon_minutes: payload.horizon_minutes || 15,
          market_question: payload.title,
          up_price: payload.yes_price || 0.5,
          down_price: payload.no_price || 0.5,
        })
        const localAction = data?.local?.action || '不交易'
        const expectedAction = payload.side === 'DOWN' ? '买DOWN' : '买UP'
        const localLine = `本地信号：${localAction}${data?.local?.edge ? `，${data.local.edge}` : ''}`
        const aiText = data?.ai || 'AI 没有返回内容'
        aiResult.value = `${localLine}\n\n${aiText}`
        aiBlocked.value = localAction !== expectedAction || blockedByText(aiText) || directionConflict(aiText, payload.side)
        return aiResult.value
      }

      const { data } = await aiApi.analyze({
        ai_config_id: aiConfigId.value,
        system_prompt: '你是 Polymarket 移动端交易前风控员，资金安全第一。必须用简体中文回答，第一行必须给出结论。',
        prompt: reviewPrompt(payload),
      })
      aiResult.value = data.result || 'AI 没有返回内容'
      aiBlocked.value = blockedByText(aiResult.value) || directionConflict(aiResult.value, payload.side)
      return aiResult.value
    } catch (err: any) {
      const message = err?.response?.data?.detail || err?.message || 'AI 复核失败'
      aiResult.value = `AI 复核失败: ${message}`
      aiBlocked.value = true
      ElMessage.error(message)
      return null
    } finally {
      aiBusy.value = false
    }
  }

  async function confirmAiBeforeOrder(payload: ReviewPayload) {
    if (!aiBeforeOrder.value) return true
    const result = await runAiReview(payload)
    if (!result) return false
    if (aiBlocked.value) {
      ElMessage.error('AI 复核不建议提交这笔订单')
      return false
    }
    return window.confirm('AI 复核未阻断，继续提交订单？')
  }

  return {
    providers,
    aiConfigId,
    aiBeforeOrder,
    aiBusy,
    aiResult,
    aiBlocked,
    loadAiProviders,
    resetAiReview,
    runAiReview,
    confirmAiBeforeOrder,
  }
}
