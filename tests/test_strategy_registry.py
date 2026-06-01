from dataclasses import asdict

from app.services.strategy_registry import get_strategy_module, list_strategy_modules


def test_list_strategy_modules_exposes_additive_modules():
    modules = list_strategy_modules()
    ids = {module.module_id for module in modules}

    assert "sports_in_play_v1" in ids
    assert "sports_championship_early_v1" in ids
    assert "world_cup_tagging_v1" in ids
    assert "event_domain_fit_v1" in ids
    assert "election_live_count_v1" in ids
    assert all(module.execution_mode in {"read_only", "read_only_paper"} for module in modules)


def test_get_strategy_module_returns_definition():
    module = get_strategy_module("sports_in_play_v1")

    assert module is not None
    assert module.domain == "sports"
    assert "/api/strategy/in-play" in module.api_paths
    assert "/api/strategy/discipline" in module.api_paths
    assert "feed_staleness_check" in module.risk_controls
    assert "hold_discipline" in module.risk_controls


def test_strategy_module_definition_is_json_ready():
    module = get_strategy_module("event_domain_fit_v1")

    assert module is not None
    payload = asdict(module)
    assert payload["module_id"] == "event_domain_fit_v1"
    assert "required_inputs" in payload


def test_election_live_count_module_is_paper_only():
    module = get_strategy_module("election_live_count_v1")

    assert module is not None
    assert module.domain == "politics"
    assert module.execution_mode == "read_only_paper"
    assert "/api/strategy/election-live-count" in module.api_paths


def test_world_cup_tag_module_is_additive_read_only():
    module = get_strategy_module("world_cup_tagging_v1")

    assert module is not None
    assert module.execution_mode == "read_only"
    assert module.status == "tagging"
    assert "/api/strategy/world-cup-tags" in module.api_paths
