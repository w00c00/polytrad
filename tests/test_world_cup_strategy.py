from app.services.world_cup_strategy import classify_world_cup_market, list_world_cup_market_tags


def test_list_world_cup_market_tags_exposes_live_knockout_and_champion_sets():
    tags = list_world_cup_market_tags()
    ids = {tag.tag_id for tag in tags}

    assert "world_cup_live_fun" in ids
    assert "world_cup_knockout_equal_strength" in ids
    assert "world_cup_champion_early" in ids
    assert all("hold_discipline" in tag.risk_controls or "paper_only" in tag.risk_controls for tag in tags)


def test_classify_world_cup_market_matches_champion_market():
    tags = classify_world_cup_market("2026 FIFA World Cup winner")

    assert any(tag.tag_id == "world_cup_champion_early" for tag in tags)
