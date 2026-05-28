import httpx
from datetime import datetime, timezone, timedelta
from typing import Any
from app.config import get_settings

settings = get_settings()

BJT = timezone(timedelta(hours=8))


def to_beijing_time(iso_str: str | None) -> str | None:
    """将 ISO 时间字符串转为北京时间显示"""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_bj = dt.astimezone(BJT)
        return dt_bj.strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_str


def _et_to_bj_time(time_str: str) -> str:
    """将美东时间字符串 (如 '6:30PM') 转为北京时间 24 小时制"""
    try:
        from datetime import datetime
        t = datetime.strptime(time_str.strip(), "%I:%M%p")
        # ET = UTC-4 (EDT) or UTC-5 (EST), 北京 = UTC+8, 差 12 或 13 小时
        # 用 EDT (夏令时) 差 12 小时
        h = (t.hour + 12) % 24
        return f"{h:02d}:{t.minute:02d}"
    except (ValueError, TypeError):
        return time_str


# Polymarket 标题中常见实体的中文翻译
_ENTITIES = {
    # 球队
    "San Antonio Spurs": "圣安东尼奥马刺队", "Boston Celtics": "波士顿凯尔特人队",
    "Los Angeles Lakers": "洛杉矶湖人队", "Golden State Warriors": "金州勇士队",
    "Miami Heat": "迈阿密热火队", "Denver Nuggets": "丹佛掘金队",
    "Dallas Mavericks": "达拉斯独行侠队", "Milwaukee Bucks": "密尔沃基雄鹿队",
    "Phoenix Suns": "菲尼克斯太阳队", "Philadelphia 76ers": "费城76人队",
    "New York Knicks": "纽约尼克斯队", "Chicago Bulls": "芝加哥公牛队",
    "Brooklyn Nets": "布鲁克林篮网队", "Houston Rockets": "休斯顿火箭队",
    "Memphis Grizzlies": "孟菲斯灰熊队", "Cleveland Cavaliers": "克利夫兰骑士队",
    "Atlanta Hawks": "亚特兰大老鹰队", "Minnesota Timberwolves": "明尼苏达森林狼队",
    "Oklahoma City Thunder": "俄克拉荷马城雷霆队", "Sacramento Kings": "萨克拉门托国王队",
    "Indiana Pacers": "印第安纳步行者队", "Orlando Magic": "奥兰多魔术队",
    "New Orleans Pelicans": "新奥尔良鹈鹕队", "Portland Trail Blazers": "波特兰开拓者队",
    "Toronto Raptors": "多伦多猛龙队", "Utah Jazz": "犹他爵士队",
    "Washington Wizards": "华盛顿奇才队", "Detroit Pistons": "底特律活塞队",
    "Charlotte Hornets": "夏洛特黄蜂队", "LA Clippers": "洛杉矶快船队",
    # 足球国家
    "France": "法国", "Brazil": "巴西", "Germany": "德国", "Argentina": "阿根廷",
    "Spain": "西班牙", "England": "英格兰", "Portugal": "葡萄牙", "Italy": "意大利",
    "Netherlands": "荷兰", "Belgium": "比利时", "Croatia": "克罗地亚",
    "Morocco": "摩洛哥", "Japan": "日本", "South Korea": "韩国",
    "Mexico": "墨西哥", "USA": "美国", "United States": "美国",
    "Australia": "澳大利亚", "Canada": "加拿大", "Colombia": "哥伦比亚",
    "Uruguay": "乌拉圭", "Ecuador": "厄瓜多尔", "Senegal": "塞内加尔",
    "Cameroon": "喀麦隆", "Ghana": "加纳", "Nigeria": "尼日利亚",
    "Poland": "波兰", "Switzerland": "瑞士", "Denmark": "丹麦",
    "Sweden": "瑞典", "Wales": "威尔士", "Scotland": "苏格兰",
    "Ireland": "爱尔兰", "Norway": "挪威", "Austria": "奥地利",
    "Czech Republic": "捷克", "Turkey": "土耳其", "Serbia": "塞尔维亚",
    # 网球运动员
    "Novak Djokovic": "德约科维奇", "Carlos Alcaraz": "阿尔卡拉斯",
    "Jannik Sinner": "辛纳", "Daniil Medvedev": "梅德韦杰夫",
    "Iga Swiatek": "斯瓦泰克", "Aryna Sabalenka": "萨巴伦卡",
    "Coco Gauff": "高芙", "Xinyu Wang": "王欣瑜",
    # MMA / UFC
    "Conor McGregor": "麦格雷戈", "Jon Jones": "琼斯",
    "Islam Makhachev": "马哈切夫", "Khabib": "哈比布",
    # F1
    "Max Verstappen": "维斯塔潘", "Lewis Hamilton": "汉密尔顿",
    "Charles Leclerc": "勒克莱尔", "Lando Norris": "诺里斯",
    # 政治人物
    "Trump": "特朗普", "Biden": "拜登", "DeSantis": "德桑蒂斯",
    "Harris": "哈里斯", "Vance": "万斯", "Newsom": "纽森",
    "Ramaley": "拉马利", "Haley": "黑利", "RFK": "小肯尼迪",
}

# 完整短语替换（优先于单词替换）
_PHRASES = [
    ("Bitcoin Up or Down", "BTC 涨跌"),
    ("Ethereum Up or Down", "ETH 涨跌"),
    ("Up or Down", "涨还是跌"),
    ("NBA Finals", "NBA 总决赛"),
    ("NBA Championship", "NBA 总冠军"),
    ("NBA Champion", "NBA 冠军"),
    ("NBA Playoffs", "NBA 季后赛"),
    ("World Cup", "世界杯"),
    ("Super Bowl", "超级碗"),
    ("World Series", "世界大赛"),
    ("Champions League", "欧冠"),
    ("Premier League", "英超"),
    ("La Liga", "西甲"),
    ("Bundesliga", "德甲"),
    ("Serie A", "意甲"),
    ("Ligue 1", "法甲"),
    ("Roland Garros", "法网"),
    ("Wimbledon", "温网"),
    ("US Open", "美网"),
    ("Australian Open", "澳网"),
    ("World Series", "世界大赛"),
    ("Stanley Cup", "斯坦利杯"),
    ("March Madness", "疯狂三月"),
    ("FIFA World Cup", "FIFA 世界杯"),
    ("2026 FIFA World Cup", "2026 FIFA 世界杯"),
    ("2026 NBA Finals", "2026 NBA 总决赛"),
    ("Winner", "冠军"), ("Western Conference", "西部"), ("Eastern Conference", "东部"),
    ("Conference Champion", "联盟冠军"),
    ("end of", "结束前"),
    ("above", "高于"), ("below", "低于"),
    ("finals", "总决赛"), ("championship", "冠军赛"),
    ("Champion", "冠军"), ("Top 4", "前四"), ("Relegate", "降级"),
    ("election", "选举"), ("president", "总统"),
    ("governor", "州长"), ("senate", "参议院"), ("congress", "国会"),
    ("democrat", "民主党"), ("republican", "共和党"),
    ("win the", "赢得"), ("beat", "击败"), ("win", "赢得"),
    ("be the next", "成为下一任"),
]

# 简单词汇替换（最后执行）
_WORDS = {
    "Bitcoin": "比特币", "Ethereum": "以太坊",
    "NFL": "NFL", "NBA": "NBA", "MLB": "MLB", "NHL": "NHL",
    "UFC": "UFC", "F1": "F1",
    "WTA": "WTA", "ATP": "ATP",
    "above": "高于", "below": "低于",
}


def translate_title(title: str) -> str:
    """翻译 Polymarket 标题为中文"""
    import re
    result = title

    # BTC 短周期：提取 ET 时间并转为北京时间
    btc_m = re.search(r"(Bitcoin|Ethereum|BTC|ETH)\s+Up or Down\s*-\s*\w+ \d+,?\s*(\d{1,2}:\d{2}[AP]M)\s*-\s*(\d{1,2}:\d{2}[AP]M)\s*ET", result, re.IGNORECASE)
    if btc_m:
        coin = "BTC" if btc_m.group(1).lower() in ("bitcoin", "btc") else "ETH"
        t1 = _et_to_bj_time(btc_m.group(2))
        t2 = _et_to_bj_time(btc_m.group(3))
        return f"{coin} 涨跌 {t1}-{t2}"

    # 先用实体字典替换（球队、国家、人名等）
    for en, zh in _ENTITIES.items():
        result = result.replace(en, zh)
    # 清理 "the " 在中文实体前的残留
    result = re.sub(r'\bthe\s+([一-鿿])', r'\1', result)
    # 清理句首多余的 "the "
    result = re.sub(r'^the\s+', '', result)

    # 短语替换
    for en, zh in _PHRASES:
        result = result.replace(en, zh)

    # 句式匹配
    # "Will X win Y?" / "Will X 赢得 Y?"
    m = re.match(r"^Will\s+(.+?)\s+(?:win|赢得)\s+(.+?)\?$", result)
    if m:
        return f"{m.group(1)} 赢得 {m.group(2)}？"

    # "Will X beat Y?"
    m = re.match(r"^Will\s+(.+?)\s+(?:beat|击败)\s+(.+?)\?$", result)
    if m:
        return f"{m.group(1)} 击败 {m.group(2)}？"

    # "Will X be the next Y?"
    m = re.match(r"^Will\s+(.+?)\s+(?:be the next|成为下一任)\s+(.+?)\?$", result)
    if m:
        return f"{m.group(1)} 成为下一任 {m.group(2)}？"

    # "Will X be above Y by end of Z?"
    m = re.match(r"^Will\s+(.+?)\s+be\s+(?:above|高于)\s+(.+?)\s+by\s+(?:end of|结束前)\s+(.+?)\??$", result, re.IGNORECASE)
    if m:
        return f"{m.group(1)} 在 {m.group(3)} 前高于 {m.group(2)}？"

    # "Will X be above/below Y?"
    m = re.match(r"^Will\s+(.+?)\s+be\s+(above|below|高于|低于)\s+(.+?)\?$", result, re.IGNORECASE)
    if m:
        op = "高于" if m.group(2).lower() in ("above", "高于") else "低于"
        return f"{m.group(1)} {op} {m.group(3)}？"

    # "Will X finish in the top N?"
    m = re.match(r"^Will\s+(.+?)\s+finish in the top\s+(\d+)\??$", result, re.IGNORECASE)
    if m:
        return f"{m.group(1)} 进入前 {m.group(2)}？"

    # "X vs Y" / "X vs. Y"
    m = re.match(r"^(.+?)\s+vs\.?\s+(.+)$", result)
    if m:
        return f"{m.group(1)} vs {m.group(2)}"

    # "NBA/NFL: Will X beat Y by more than N points..."
    m = re.match(r"^(NBA|NFL):\s+Will\s+(.+?)\s+(?:beat|击败)\s+(.+?)\s+by more than\s+(\S+)\s+points?\s+in their\s+(.+?)\s+matchup\??$", result, re.IGNORECASE)
    if m:
        return f"{m.group(1)}: {m.group(2)} vs {m.group(3)} 净胜 {m.group(4)} 分以上？"

    # Generic "Will X?" → "X 会发生吗？"
    m = re.match(r"^Will\s+(.+?)\?$", result)
    if m:
        return f"{m.group(1)} 会发生吗？"

    # 最后做简单的单词替换
    for en, zh in _WORDS.items():
        result = re.sub(rf'\b{en}\b', zh, result, flags=re.IGNORECASE)

    return result


class GammaAPI:
    """Polymarket Gamma API - 市场发现与元数据 (无需认证)"""

    def __init__(self):
        self.base = settings.polymarket_gamma_host
        self.client = httpx.AsyncClient(timeout=30)

    async def get_events(self, **params) -> list[dict]:
        params.setdefault("active", "true")
        params.setdefault("closed", "false")
        params.setdefault("limit", 50)
        resp = await self.client.get(f"{self.base}/events", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_event(self, slug: str) -> dict | None:
        resp = await self.client.get(f"{self.base}/events", params={"slug": slug})
        resp.raise_for_status()
        events = resp.json()
        return events[0] if events else None

    async def get_markets(self, **params) -> list[dict]:
        params.setdefault("active", "true")
        params.setdefault("closed", "false")
        params.setdefault("limit", 50)
        resp = await self.client.get(f"{self.base}/markets", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_market_by_slug(self, slug: str) -> dict | None:
        resp = await self.client.get(f"{self.base}/markets", params={"slug": slug})
        resp.raise_for_status()
        markets = resp.json()
        return markets[0] if markets else None

    async def search(self, query: str) -> list[dict]:
        """通过 events + markets 过滤实现搜索（/search 端点已下线）"""
        keywords = query.lower().split()
        results = []
        for ep in ["/events", "/markets"]:
            resp = await self.client.get(f"{self.base}{ep}", params={"active": "true", "closed": "false", "limit": 100})
            if resp.status_code == 200:
                for item in resp.json():
                    text = (item.get("title", "") + item.get("question", "") + item.get("slug", "")).lower()
                    if any(kw in text for kw in keywords):
                        results.append(item)
        return results

    async def get_tags(self) -> list[dict]:
        resp = await self.client.get(f"{self.base}/tags")
        resp.raise_for_status()
        return resp.json()

    async def get_series(self, slug: str) -> dict | None:
        """获取 series 信息及其 events（用于 BTC 短周期等循环市场）"""
        resp = await self.client.get(f"{self.base}/series", params={"slug": slug})
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data[0] if data else None

    async def get_prices_history(self, market_id: str, interval: str = "1d") -> list:
        resp = await self.client.get(
            f"{self.base}/prices-history",
            params={"market": market_id, "interval": interval},
        )
        resp.raise_for_status()
        return resp.json()


class DataAPI:
    """Polymarket Data API - 持仓、交易历史 (无需认证)"""

    def __init__(self):
        self.base = settings.polymarket_data_host
        self.client = httpx.AsyncClient(timeout=30)

    async def get_positions(self, wallet_address: str) -> list[dict]:
        resp = await self.client.get(f"{self.base}/positions", params={"user": wallet_address})
        resp.raise_for_status()
        return resp.json()

    async def get_closed_positions(self, wallet_address: str) -> list[dict]:
        resp = await self.client.get(f"{self.base}/closed-positions", params={"user": wallet_address})
        resp.raise_for_status()
        return resp.json()

    async def get_value(self, wallet_address: str) -> dict:
        resp = await self.client.get(f"{self.base}/value", params={"user": wallet_address})
        resp.raise_for_status()
        return resp.json()

    async def get_trades(self, wallet_address: str, limit: int = 100) -> list[dict]:
        resp = await self.client.get(f"{self.base}/trades", params={"user": wallet_address, "limit": limit})
        resp.raise_for_status()
        return resp.json()


class CLOBAPI:
    """Polymarket CLOB API - 订单簿、价格 (公开读取无需认证)"""

    def __init__(self):
        self.base = settings.polymarket_clob_host
        self.client = httpx.AsyncClient(timeout=30)

    async def get_midpoint(self, token_id: str) -> float:
        resp = await self.client.get(f"{self.base}/midpoint", params={"token_id": token_id})
        resp.raise_for_status()
        return float(resp.json().get("mid", 0))

    async def get_price(self, token_id: str, side: str = "BUY") -> float:
        resp = await self.client.get(f"{self.base}/price", params={"token_id": token_id, "side": side})
        resp.raise_for_status()
        return float(resp.json().get("price", 0))

    async def get_orderbook(self, token_id: str) -> dict:
        resp = await self.client.get(f"{self.base}/book", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()

    async def get_spread(self, token_id: str) -> dict:
        resp = await self.client.get(f"{self.base}/spread", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()

    async def get_tick_size(self, token_id: str) -> str:
        resp = await self.client.get(f"{self.base}/tick-size", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json().get("tick_size", "0.01")

    async def get_last_trade(self, token_id: str) -> dict:
        resp = await self.client.get(f"{self.base}/last-trade-price", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()


gamma_api = GammaAPI()
data_api = DataAPI()
clob_api = CLOBAPI()
