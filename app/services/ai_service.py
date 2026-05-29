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


def format_binance_indicators(indicators: dict) -> str:
    """将 Binance 技术指标格式化为 AI 易读的结构化文本"""
    if not indicators or "error" in indicators:
        return f"数据不可用: {indicators.get('error', '未知错误')}"

    lines = []
    price = indicators.get("current_price", 0)
    change = indicators.get("price_change_24h", 0)
    lines.append(f"【价格】当前 ${price:,.2f}，24h 涨跌 {change:+.2f}%")
    lines.append(f"【24h 区间】${indicators.get('low_24h', 0):,.2f} ~ ${indicators.get('high_24h', 0):,.2f}")
    lines.append(f"【24h 成交量】{indicators.get('quote_volume_24h', 0) / 1e6:,.1f}M USDT，{indicators.get('trades_count_24h', 0)} 笔")

    # RSI
    rsi_15m = indicators.get("rsi_15m")
    rsi_1h = indicators.get("rsi_1h")
    if rsi_15m is not None:
        rsi_15m_signal = "超买" if rsi_15m > 70 else "超卖" if rsi_15m < 30 else "中性"
        lines.append(f"【RSI 15m】{rsi_15m:.1f} ({rsi_15m_signal})")
    if rsi_1h is not None:
        rsi_1h_signal = "超买" if rsi_1h > 70 else "超卖" if rsi_1h < 30 else "中性"
        lines.append(f"【RSI 1h】{rsi_1h:.1f} ({rsi_1h_signal})")

    # EMA
    ema_9_15m = indicators.get("ema_9_15m")
    ema_21_15m = indicators.get("ema_21_15m")
    ema_50_15m = indicators.get("ema_50_15m")
    if ema_9_15m and ema_21_15m:
        trend_15m = "多头排列" if ema_9_15m > ema_21_15m else "空头排列"
        lines.append(f"【EMA 15m】9={ema_9_15m:,.2f}, 21={ema_21_15m:,.2f}, 50={ema_50_15m:,.2f} → {trend_15m}")
    if indicator_price := price:
        above_below = "价格在 EMA21 上方" if ema_21_15m and indicator_price > ema_21_15m else "价格在 EMA21 下方"
        lines.append(f"        {above_below}")

    ema_9_1h = indicators.get("ema_9_1h")
    ema_21_1h = indicators.get("ema_21_1h")
    if ema_9_1h and ema_21_1h:
        trend_1h = "多头排列" if ema_9_1h > ema_21_1h else "空头排列"
        lines.append(f"【EMA 1h】9={ema_9_1h:,.2f}, 21={ema_21_1h:,.2f} → {trend_1h}")

    # MACD
    macd_15m = indicators.get("macd_15m")
    if macd_15m:
        macd_signal = "金叉" if macd_15m.get("histogram", 0) > 0 else "死叉"
        lines.append(f"【MACD 15m】{macd_signal}，柱状图={macd_15m.get('histogram', 0):.2f}")
    macd_1h = indicators.get("macd_1h")
    if macd_1h:
        macd_signal_1h = "金叉" if macd_1h.get("histogram", 0) > 0 else "死叉"
        lines.append(f"【MACD 1h】{macd_signal_1h}，柱状图={macd_1h.get('histogram', 0):.2f}")

    # 布林带
    bb_15m = indicators.get("bollinger_15m")
    if bb_15m:
        bw = bb_15m.get("bandwidth", 0)
        pos = "上轨附近" if price >= bb_15m.get("upper", 0) * 0.98 else "下轨附近" if price <= bb_15m.get("lower", 0) * 1.02 else "中轨附近"
        lines.append(f"【布林带 15m】{bb_15m.get('lower', 0):,.2f} ~ {bb_15m.get('upper', 0):,.2f}，带宽 {bw:.2f}%，价格{pos}")

    # 成交量
    vr = indicators.get("volume_ratio_15m")
    if vr:
        vol_signal = "放量" if vr > 1.5 else "缩量" if vr < 0.7 else "正常"
        lines.append(f"【成交量 15m】{vr:.2f}x ({vol_signal})")

    # 近期涨跌
    for key, label in [("price_change_5_15m", "5根15m"), ("price_change_10_15m", "10根15m"), ("price_change_20_15m", "20根15m")]:
        val = indicators.get(key)
        if val is not None:
            lines.append(f"【涨跌 {label}】{val:+.2f}%")

    # 近期高低点
    lines.append(f"【近期区间】低 ${indicators.get('recent_low', 0):,.2f} ~ 高 ${indicators.get('recent_high', 0):,.2f}")

    return "\n".join(lines)


def build_crypto_prompt(signal: dict, binance_indicators: dict, market_info: dict) -> str:
    """构建加密货币专用分析 prompt"""
    return f"""请基于以下多源数据，预测 BTC 在未来 {market_info['horizon_minutes']} 分钟内的走势。

═══════════════════════════════════════
数据源 1：Polymarket 本地动量模型（{market_info['horizon_minutes']} 分钟周期）
═══════════════════════════════════════
- BTC 现价：${signal['price']:,.2f}
- 本地预测上涨概率：{signal['prob_up']:.1%}，下跌概率：{signal['prob_down']:.1%}
- 本地置信度：{signal['confidence']}（数值 {signal['confidence_value']:.2f}）
- 短期动量 (fast={signal['fast_window']}min)：{signal['ret_fast']:+.3%}
- 中期动量 (mid={signal['mid_window']}min)：{signal['ret_mid']:+.3%}
- 长期动量 (slow={signal['slow_window']}min)：{signal['ret_slow']:+.3%}
- 本地 RSI：{signal['rsi']:.1f}
- 本地波动率：{signal['vol']:.4%}
- 本地 EMA 快/慢：${signal['ema_fast']:,.2f} / ${signal['ema_slow']:,.2f}

═══════════════════════════════════════
数据源 2：Binance 实时技术指标
═══════════════════════════════════════
{format_binance_indicators(binance_indicators)}

═══════════════════════════════════════
数据源 3：市场报价（Polymarket）
═══════════════════════════════════════
- 市场问题：{market_info.get('question', '未指定')}
- UP (YES) 买入价：${market_info['up_price']:.3f}（隐含上涨概率）
- DOWN (NO) 买入价：${market_info['down_price']:.3f}（隐含下跌概率）
- 本地预测 vs 报价边际：
  · UP 边际：{signal['prob_up'] - market_info['up_price']:+.1%}（正数=有利）
  · DOWN 边际：{signal['prob_down'] - market_info['down_price']:+.1%}（正数=有利）

═══════════════════════════════════════
分析要求
═══════════════════════════════════════
请综合以上三组数据，严格按以下格式输出：

🎯 趋势判断：[看涨/看跌/震荡] (置信度：高/中/低)
📊 概率预测：上涨 XX.X% | 下跌 XX.X%
💰 当前价格：$XXXX.XX
📈 目标价位：$XXXX ~ $XXXX
📉 止损价位：$XXXX
💡 交易建议：做多/做空/观望
   · Polymarket 操作：买 UP / 买 DOWN / 不交易
   · 建议入场价区间：$X.XXX ~ $X.XXX
📊 关键依据：
   · RSI 信号：...
   · 均线信号：...
   · MACD 信号：...
   · 布林带：...
⚠️ 风险提示：...

【分析要点】
1. 重点关注 15m 和 1h RSI 是否背离或共振
2. 判断 EMA 15m 和 1h 的排列方向是否一致（多周期共振）
3. MACD 金叉/死叉与价格位置的关系
4. 布林带位置判断短期超买超卖
5. 成交量比确认趋势有效性
6. 当 Polymarket 报价边际 > 4% 且置信度高时才建议交易"""


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
