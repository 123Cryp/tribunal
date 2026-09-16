"""
Offline tests for the Tribunal contracts, using genlayer-test's Direct Mode
(in-process GenVM, no Studio/Docker needed).

IMPORTANT: the exact signature of the mock_web / mock_llm cheatcodes has NOT
been live-verified against the installed genlayer-test version in this
environment (only direct_vm, direct_deploy, and the sender-related fixtures
were confirmed from public examples). Before relying on these tests, run
them once and adjust the mock_web(...)/mock_llm(...) calls to match whatever
error message pytest reports for the actual installed version -- this
mirrors the project's own rule of never trusting unverified SDK surface.

Run with:
    pip install genlayer-test
    pytest tests/ -v
"""

import json
import pytest


PRECEDENT_REGISTRY_PATH = "contracts/precedent_registry.py"
FIRST_INSTANCE_COURT_PATH = "contracts/first_instance_court.py"
APPEALS_COURT_PATH = "contracts/appeals_court.py"


# ---------------------------------------------------------------------------
# PrecedentRegistry
# ---------------------------------------------------------------------------

def test_registry_starts_empty(direct_deploy):
    registry = direct_deploy(PRECEDENT_REGISTRY_PATH)
    assert registry.get_entry_count() == 0


def test_registry_records_and_reads_back(direct_deploy):
    registry = direct_deploy(PRECEDENT_REGISTRY_PATH)
    registry.record_verdict(0, "Vendor failed to deliver goods", "BREACH", "low")
    assert registry.get_entry_count() == 1
    entry = json.loads(registry.get_entry(0))
    assert entry["case_id"] == 0
    assert entry["verdict"] == "BREACH"
    assert entry["tier"] == "low"


def test_registry_search_finds_shared_words(direct_deploy):
    registry = direct_deploy(PRECEDENT_REGISTRY_PATH)
    registry.record_verdict(0, "Vendor failed to deliver goods on time", "BREACH", "low")
    registry.record_verdict(1, "Completely unrelated dispute about a lease", "NO_BREACH", "low")

    matches = json.loads(registry.search_precedents("Vendor failed to deliver equipment", 3))
    descriptions = [m["description"] for m in matches]
    assert "Vendor failed to deliver goods on time" in descriptions
    assert "Completely unrelated dispute about a lease" not in descriptions


def test_registry_search_respects_max_results(direct_deploy):
    registry = direct_deploy(PRECEDENT_REGISTRY_PATH)
    for i in range(5):
        registry.record_verdict(i, "Vendor failed to deliver goods on time", "BREACH", "low")
    matches = json.loads(registry.search_precedents("Vendor failed to deliver goods", 2))
    assert len(matches) == 2


# ---------------------------------------------------------------------------
# FirstInstanceCourt (low tier only -- deterministic, no LLM needed)
# ---------------------------------------------------------------------------

def test_low_tier_breach_when_fact_matches(direct_deploy, mock_web):
    registry = direct_deploy(PRECEDENT_REGISTRY_PATH)
    court = direct_deploy(
        FIRST_INSTANCE_COURT_PATH,
        registry.address,
        100,
        1000,
    )

    # TODO: verify exact mock_web signature against installed genlayer-test.
    mock_web.set_page("https://example.test/evidence", "the shipment never arrived")

    case_id = court.file_case(
        court.address,
        "Vendor failed to deliver goods as agreed",
        50,  # below low_threshold=100 -> low tier
        "shipment never arrived",
        "https://example.test/evidence",
    )
    assert case_id == 0

    case = json.loads(court.get_case(0))
    assert case["tier"] == "low"
    assert case["verdict"] == "BREACH"


def test_low_tier_no_breach_when_fact_does_not_match(direct_deploy, mock_web):
    registry = direct_deploy(PRECEDENT_REGISTRY_PATH)
    court = direct_deploy(
        FIRST_INSTANCE_COURT_PATH,
        registry.address,
        100,
        1000,
    )

    mock_web.set_page("https://example.test/evidence", "the shipment arrived on schedule")

    case_id = court.file_case(
        court.address,
        "Vendor failed to deliver goods as agreed",
        50,
        "shipment never arrived",
        "https://example.test/evidence",
    )

    case = json.loads(court.get_case(case_id))
    assert case["verdict"] == "NO_BREACH"


def test_tier_selection_by_claimed_amount(direct_deploy, mock_web, mock_llm):
    registry = direct_deploy(PRECEDENT_REGISTRY_PATH)
    court = direct_deploy(
        FIRST_INSTANCE_COURT_PATH,
        registry.address,
        100,
        1000,
    )

    mock_web.set_page("https://example.test/evidence", "irrelevant page content")

    # TODO: verify exact mock_llm signature; this assumes it can return a
    # fixed JSON string for any exec_prompt call during the test.
    mock_llm.set_response(
        json.dumps({
            "literal_reading": "BREACH",
            "spirit_reading": "BREACH",
            "final_verdict": "BREACH",
        })
    )

    medium_case_id = court.file_case(
        court.address,
        "A medium-value dispute",
        500,  # between low_threshold=100 and high_threshold=1000 -> medium tier
        "some fact",
        "https://example.test/evidence",
    )
    case = json.loads(court.get_case(medium_case_id))
    assert case["tier"] == "medium"


def test_set_appeals_court_only_once(direct_deploy):
    registry = direct_deploy(PRECEDENT_REGISTRY_PATH)
    court = direct_deploy(
        FIRST_INSTANCE_COURT_PATH,
        registry.address,
        100,
        1000,
    )
    appeals = direct_deploy(APPEALS_COURT_PATH, registry.address)

    court.set_appeals_court(appeals.address)
    with pytest.raises(Exception):
        court.set_appeals_court(appeals.address)


def test_set_appeals_court_only_owner(direct_deploy, direct_accounts):
    registry = direct_deploy(PRECEDENT_REGISTRY_PATH)
    court = direct_deploy(
        FIRST_INSTANCE_COURT_PATH,
        registry.address,
        100,
        1000,
    )
    appeals = direct_deploy(APPEALS_COURT_PATH, registry.address)

    not_owner = direct_accounts[1]
    with pytest.raises(Exception):
        court.set_appeals_court(appeals.address, sender=not_owner)


# ---------------------------------------------------------------------------
# AppealsCourt
# ---------------------------------------------------------------------------

def test_appeal_overturns_and_records_final_verdict(direct_deploy, mock_llm):
    registry = direct_deploy(PRECEDENT_REGISTRY_PATH)
    appeals = direct_deploy(APPEALS_COURT_PATH, registry.address)

    case_json = json.dumps({
        "case_id": 0,
        "claimant": "0x" + "11" * 20,
        "description": "Vendor failed to deliver goods",
        "verdict": "NO_BREACH",
    })

    mock_llm.set_response(
        json.dumps({
            "framing_a": "BREACH",
            "framing_b": "BREACH",
            "framing_c": "BREACH",
            "final_verdict": "BREACH",
        })
    )

    appeals.file_appeal(0, case_json)

    appeal = json.loads(appeals.get_appeal(0))
    assert appeal["overturned"] is True
    assert appeal["final_verdict"] == "BREACH"
    assert appeal["appellant"] == "0x" + "11" * 20

    # The appeal's final verdict must also land in PrecedentRegistry.
    assert registry.get_entry_count() == 1
    entry = json.loads(registry.get_entry(0))
    assert entry["verdict"] == "BREACH"
    assert entry["tier"] == "appeal"


def test_appeal_confirms_when_verdict_unchanged(direct_deploy, mock_llm):
    registry = direct_deploy(PRECEDENT_REGISTRY_PATH)
    appeals = direct_deploy(APPEALS_COURT_PATH, registry.address)

    case_json = json.dumps({
        "case_id": 1,
        "claimant": "0x" + "22" * 20,
        "description": "A dispute that should be confirmed",
        "verdict": "BREACH",
    })

    mock_llm.set_response(
        json.dumps({
            "framing_a": "BREACH",
            "framing_b": "BREACH",
            "framing_c": "BREACH",
            "final_verdict": "BREACH",
        })
    )

    appeals.file_appeal(1, case_json)

    appeal = json.loads(appeals.get_appeal(0))
    assert appeal["overturned"] is False
