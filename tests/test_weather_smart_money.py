from app.services.intelligence import _closed_position_stats, _is_weather_market


def test_weather_market_detection_matches_temperature_titles():
    assert _is_weather_market({
        "title": "Will the highest temperature in Shanghai be 30C on June 2?",
        "slug": "highest-temperature-in-shanghai-on-june-2-2026-30c",
    })
    assert _is_weather_market({"title": "Will rainfall in New York exceed 1 inch today?"})


def test_weather_market_detection_ignores_non_weather_sports():
    assert not _is_weather_market({"title": "Will Japan win on 2026-03-28?", "slug": "fif-sco-jpn-2026-03-28-jpn"})


def test_closed_position_stats_can_filter_weather_history():
    items = [
        {"title": "Will the highest temperature in Shanghai be 19C on April 16?", "realizedPnl": 46.7},
        {"title": "Will rainfall in Miami exceed 1 inch?", "realizedPnl": -12.0},
        {"title": "Will Japan win on 2026-03-28?", "realizedPnl": 120.9},
    ]

    stats = _closed_position_stats(items, _is_weather_market)

    assert stats["closed_count"] == 2
    assert stats["closed_pnl"] == 34.7
    assert stats["closed_win_rate"] == 50.0
