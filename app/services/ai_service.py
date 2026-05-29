import logging
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AIConfig
from app.crypto import decrypt_secret

logger = logging.getLogger(__name__)

PROVIDER_BASE_URLS = {
    "minimax": "https://api.minimax.chat/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "volcano": "https://ark.cn-beijing.volces.com/api/v3",
    "custom": None,  # 使用配置中的 base_url
}

MARKET_ANALYSIS_PROMPT = """你是一个专业的 Polymarket 预测市场交易分析师。
根据提供的市场数据，给出：
1. 概率判断 (YES/NO 各自的概率)
2. 置信度 (高/中/低)
3. 交易建议 (买入YES/买入NO/观望)
4. 风险评估
5. 简要分析理由

【重要】必须使用简体中文回答，不要使用英文。专有名词（如NBA、NFL等）可保留。"""

CRYPTO_ANALYSIS_PROMPT = """你是一个专业的加密货币短线交易分析师，专注于 BTC/ETH 的短期价格走势预测。

你需要综合分析以下数据源，给出精准的短期价格预测：

【数据源】
1. Binance 实时技术指标（RSI、EMA、MACD、布林带等）
2. Polymarket 本地技术分析（概率模型、动量、波动率）
3. 市场情绪指标（成交量、买卖盘口）

【分析要求】
1. 短期趋势判断（看涨/看跌/震荡，置信度）
2. 关键支撑位和阻力位
3. RSI 超买超卖信号（>70 超买, <30 超卖）
4. 均线排列（多头排列 vs 空头排列）
5. MACD 金叉/死叉信号
6. 明确的交易建议：
   - 建议操作：做多 / 做空 / 观望
   - 建议入场价格区间
   - 止损价格
   - 目标价格
   - 预期盈亏比
7. 风险提示

【输出格式】
使用结构化格式，便于用户快速阅读：
```
🎯 趋势判断：[看涨/看跌/震荡] (置信度：高/中/低)
📊 概率预测：上涨 XX% | 下跌 XX%
💰 当前价格：$XXX
📈 目标价位：$XXX ~ $XXX
📉 止损价位：$XXX
💡 交易建议：[做多/做空/观望]
⚠️ 风险提示：...
```

【重要】必须使用简体中文回答。价格数据保留 2 位小数。百分比保留 1 位小数。"""


def get_ai_client(config: AIConfig) -> OpenAI:
    base_url = config.base_url or PROVIDER_BASE_URLS.get(config.provider)
    if not base_url:
        raise ValueError(f"未知 AI 提供商: {config.provider}")
    api_key = decrypt_secret(config.encrypted_api_key)
    return OpenAI(api_key=api_key, base_url=base_url)


async def get_active_ai_config(db: AsyncSession, config_id: int) -> AIConfig:
    result = await db.execute(select(AIConfig).where(AIConfig.id == config_id, AIConfig.is_active == True))
    config = result.scalar_one_or_none()
    if not config:
        raise ValueError("AI 配置不存在或未启用")
    return config


async def analyze(config: AIConfig, prompt: str, system_prompt: str = MARKET_ANALYSIS_PROMPT) -> str:
    client = get_ai_client(config)
    # 确保 system_prompt 包含中文指令
    if "中文" not in system_prompt:
        system_prompt += "\n【重要】必须使用简体中文回答。"
    try:
        resp = client.chat.completions.create(
            model=config.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1500,
        )
        return resp.choices[0].message.content
    except Exception as e:
        logger.error(f"AI 分析失败: {e}")
        return f"AI 分析失败: {e}"


async def analyze_market(config: AIConfig, market_data: dict, question: str = "") -> str:
    import json
    prompt = f"""市场数据:
{json.dumps(market_data, ensure_ascii=False, indent=2)}

{question or '请分析这个市场的交易机会。'}"""
    return await analyze(config, prompt, MARKET_ANALYSIS_PROMPT)


async def analyze_arbitrage(config: AIConfig, event_data: dict, yes_sum: float) -> str:
    import json
    prompt = f"""事件套利分析:
事件: {event_data.get('title', '')}
各市场 YES 价格之和: {yes_sum:.4f} (理论值应为 1.0)
偏离: {abs(yes_sum - 1.0):.4f}

市场详情:
{json.dumps(event_data.get('markets', []), ensure_ascii=False, indent=2)}

请评估套利机会和风险，用简体中文回答。"""
    return await analyze(config, prompt)
