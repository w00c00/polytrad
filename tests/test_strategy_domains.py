from dataclasses import asdict

from app.services.strategy_domains import list_domain_candidates


def test_list_domain_candidates_ranks_pilot_domains_first():
    candidates = list_domain_candidates()

    assert candidates[0].fit.score >= candidates[-1].fit.score
    assert candidates[0].recommendation == "pilot"
    assert candidates[0].domain_id in {"election_live_count", "award_show_results"}


def test_domain_candidates_include_rejected_subjective_markets():
    candidates = {candidate.domain_id: candidate for candidate in list_domain_candidates()}
    rumor = candidates["celebrity_rumor"]

    assert rumor.fit.applicable is False
    assert rumor.recommendation == "reject"
    assert "resolution is subjective or ambiguous" in rumor.fit.blocking_risks


def test_domain_candidate_payload_is_json_ready():
    candidate = list_domain_candidates()[0]
    payload = asdict(candidate)

    assert "fit" in payload
    assert "score" in payload["fit"]
    assert isinstance(payload["catalyst_examples"], tuple)
