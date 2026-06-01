from datetime import datetime, timedelta, timezone

from app.services.sports_live import is_stale, normalize_polymarket_sport_result


def test_normalize_polymarket_sport_result():
    state = normalize_polymarket_sport_result(
        {
            "slug": "mci-liv-2025-02-03",
            "live": True,
            "ended": False,
            "score": "1-0",
            "period": "1H",
            "elapsed": "32:15",
            "last_update": "2025-02-03T19:50:16.939Z",
        }
    )

    assert state.slug == "mci-liv-2025-02-03"
    assert state.live is True
    assert state.ended is False
    assert state.home_score == 1
    assert state.away_score == 0
    assert state.score_diff == 1
    assert state.last_update is not None


def test_normalize_polymarket_sport_result_bad_score():
    state = normalize_polymarket_sport_result({"slug": "x", "score": "pending"})

    assert state.home_score is None
    assert state.away_score is None
    assert state.score_diff is None


def test_is_stale_without_timestamp():
    state = normalize_polymarket_sport_result({"slug": "x"})

    assert is_stale(state, datetime.now(timezone.utc))


def test_is_stale_by_age():
    now = datetime.now(timezone.utc)
    state = normalize_polymarket_sport_result(
        {
            "slug": "x",
            "last_update": (now - timedelta(seconds=120)).isoformat(),
        }
    )

    assert is_stale(state, now, max_age_seconds=90)
    assert not is_stale(state, now, max_age_seconds=180)
