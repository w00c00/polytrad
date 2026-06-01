from app.services.strategy_core import CatalystReliability, score_event_driven_domain


def test_score_event_driven_domain_accepts_live_sports_shape():
    fit = score_event_driven_domain(
        domain="live sports",
        has_realtime_feed=True,
        feed_latency_seconds=5,
        has_liquid_polymarket_markets=True,
        catalyst_reliability=CatalystReliability.HIGH,
        market_reacts_gradually=True,
        objective_resolution=True,
    )

    assert fit.applicable is True
    assert fit.score >= 0.9
    assert "quote_snapshot" in fit.required_modules


def test_score_event_driven_domain_blocks_subjective_markets():
    fit = score_event_driven_domain(
        domain="celebrity rumor",
        has_realtime_feed=True,
        feed_latency_seconds=30,
        has_liquid_polymarket_markets=True,
        catalyst_reliability=CatalystReliability.LOW,
        market_reacts_gradually=True,
        objective_resolution=False,
    )

    assert fit.applicable is False
    assert "resolution is subjective or ambiguous" in fit.blocking_risks


def test_score_event_driven_domain_blocks_no_feed():
    fit = score_event_driven_domain(
        domain="private company outcome",
        has_realtime_feed=False,
        feed_latency_seconds=None,
        has_liquid_polymarket_markets=True,
        catalyst_reliability=CatalystReliability.MEDIUM,
        market_reacts_gradually=True,
        objective_resolution=True,
    )

    assert fit.applicable is False
    assert "no realtime feed" in fit.blocking_risks
    assert "unknown feed latency" in fit.blocking_risks
