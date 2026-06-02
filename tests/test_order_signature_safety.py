from datetime import datetime, timedelta, timezone

import pytest

from app.models import Credential
from app.services import opportunities
from app.services.trading import _effective_signature_type


def _cred(wallet: str, funder: str | None, signature_type: int = 0) -> Credential:
    return Credential(
        user_id=1,
        wallet_address=wallet,
        funder_address=funder,
        encrypted_private_key="x",
        encrypted_api_key="x",
        encrypted_api_secret="x",
        encrypted_api_passphrase="x",
        chain_id=137,
        signature_type=signature_type,
    )


def test_effective_signature_type_treats_legacy_self_funder_as_eoa():
    cred = _cred("0xAbC", "0xabc", 0)
    assert _effective_signature_type(cred) == (0, None)


def test_effective_signature_type_keeps_legacy_external_funder_as_deposit_wallet():
    cred = _cred("0x111", "0x222", 0)
    assert _effective_signature_type(cred) == (3, "0x222")


def test_effective_signature_type_uses_explicit_proxy_type():
    cred = _cred("0x111", "0x222", 1)
    assert _effective_signature_type(cred) == (1, "0x222")


@pytest.mark.asyncio
async def test_quick_buy_hydrates_market_metadata_for_copy_trade(monkeypatch):
    captured = {}

    async def fake_market(slug):
        assert slug == "weather-market"
        return {
            "slug": "weather-market",
            "conditionId": "0xcond",
            "active": True,
            "closed": False,
            "acceptingOrders": True,
            "endDate": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
            "clobTokenIds": ["yes-token", "no-token"],
            "minimumTickSize": "0.001",
            "negRisk": True,
        }

    async def fake_place_limit_order(user, db, **kwargs):
        captured.update(kwargs)
        return {"trade_id": 1, "order_id": "order-1"}

    monkeypatch.setattr(opportunities.gamma_api, "get_market_by_slug", fake_market)
    monkeypatch.setattr(opportunities, "place_limit_order", fake_place_limit_order)

    result = await opportunities.quick_buy_token(
        user=object(),
        db=object(),
        token_id="yes-token",
        amount_usdc=10,
        order_type="FOK",
        tick_size="0.01",
        neg_risk=False,
        market_slug="weather-market",
    )

    assert result["message"] == "已提交快捷买入订单"
    assert captured["tick_size"] == "0.001"
    assert captured["neg_risk"] is True
    assert captured["condition_id"] == "0xcond"
    assert captured["market_slug"] == "weather-market"
    assert captured["usdc_amount"] == 10
