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

回答要简洁直接，用中文。"""


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
    return await analyze(config, prompt)


async def analyze_arbitrage(config: AIConfig, event_data: dict, yes_sum: float) -> str:
    import json
    prompt = f"""事件套利分析:
事件: {event_data.get('title', '')}
各市场 YES 价格之和: {yes_sum:.4f} (理论值应为 1.0)
偏离: {abs(yes_sum - 1.0):.4f}

市场详情:
{json.dumps(event_data.get('markets', []), ensure_ascii=False, indent=2)}

请评估套利机会和风险。"""
    return await analyze(config, prompt)
