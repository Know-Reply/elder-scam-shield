"""Unit tests for the Behavioral Analyzer — longitudinal profiling and risk scoring."""

from unittest.mock import MagicMock

import pytest

from tests.conftest import FakeDocSnapshot


@pytest.fixture(autouse=True)
def _patch_firestore(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr("agents.behavioral_analyzer.db", mock_client)
    monkeypatch.setattr("agents.behavioral_analyzer.PROFILES", mock_client.collection("sender_profiles"))
    monkeypatch.setattr("agents.behavioral_analyzer.CONTACTS", mock_client.collection("user_contacts"))
    monkeypatch.setattr("agents.behavioral_analyzer.RISK_EVENTS", mock_client.collection("risk_events"))
    return mock_client


class TestEmptyProfile:
    """New senders get a blank profile."""

    def test_empty_profile_has_zero_risk(self):
        from agents.behavioral_analyzer import _empty_profile

        profile = _empty_profile("new@example.com")

        assert profile["sender_email"] == "new@example.com"
        assert profile["message_count"] == 0
        assert profile["risk_score"] == 0.0
        assert profile["contradiction_count"] == 0
        assert profile["stated_facts"]["claimed_name"] == []
        assert profile["stated_facts"]["financial_mentions"] == []

    def test_empty_profile_has_no_contact_match(self):
        from agents.behavioral_analyzer import _empty_profile

        profile = _empty_profile("new@example.com")
        assert profile["verified_against_contacts"]["match"] is None


class TestComputeRiskScore:
    """Risk score computation with corpus-derived signal weights."""

    def test_single_signal_returns_its_weight(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score, SIGNAL_WEIGHTS

        result = compute_risk_score(detected_signals=["LG-1"])
        assert result["risk_score"] == pytest.approx(SIGNAL_WEIGHTS["LG-1"], abs=0.001)

    def test_contact_mismatch_returns_its_weight(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score, SIGNAL_WEIGHTS

        result = compute_risk_score(detected_signals=["LG-2"])
        assert result["risk_score"] == pytest.approx(SIGNAL_WEIGHTS["LG-2"], abs=0.001)

    def test_multiple_signals_sum_correctly(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score, SIGNAL_WEIGHTS

        signals = ["LG-1", "LG-2", "LG-5"]
        result = compute_risk_score(detected_signals=signals)
        expected = sum(SIGNAL_WEIGHTS[s] for s in signals)
        assert result["risk_score"] == pytest.approx(expected, abs=0.001)

    def test_many_signals_accumulate(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score

        signals = ["LG-1", "LG-2", "LG-3", "LG-4", "LG-5", "LG-8"]
        result = compute_risk_score(detected_signals=signals)
        assert result["risk_score"] > 0
        assert result["recommendation"] in ("safe", "monitor", "flag", "block")

    def test_empty_signals_zero_risk(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score

        result = compute_risk_score(detected_signals=[])
        assert result["risk_score"] == 0.0
        assert result["recommendation"] == "safe"

    def test_all_signals_capped_at_one(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score, SIGNAL_WEIGHTS

        all_signals = list(SIGNAL_WEIGHTS.keys())
        result = compute_risk_score(detected_signals=all_signals)
        assert result["risk_score"] <= 1.0

    def test_unknown_signal_ignored(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score

        result = compute_risk_score(detected_signals=["UNKNOWN-99"])
        assert result["risk_score"] == 0.0

    def test_evidence_chain_returned(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score

        result = compute_risk_score(detected_signals=["LG-1", "LG-5"])
        assert "evidence_chain" in result
        assert len(result["evidence_chain"]) >= 2
        assert all("signal" in e and "weight" in e for e in result["evidence_chain"])

    def test_evidence_chain_sorted_by_weight(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score

        result = compute_risk_score(detected_signals=["LG-1", "LG-2", "LG-5"])
        chain = result["evidence_chain"]
        weights = [abs(e["weight"]) for e in chain]
        assert weights == sorted(weights, reverse=True)


class TestContradictionDetection:
    """Location contradictions are a key scam indicator."""

    def test_location_change_visible_in_profile(self, sender_profile_high_risk):
        locations = sender_profile_high_risk["stated_facts"]["claimed_locations"]
        assert len(locations) == 2
        assert locations[0]["value"] == "大阪"
        assert locations[1]["value"] == "東京の病院"
        assert sender_profile_high_risk["contradiction_count"] == 2
        assert "location_contradiction" in sender_profile_high_risk["risk_factors"]

    def test_low_risk_profile_no_contradictions(self, sender_profile_low_risk):
        locations = sender_profile_low_risk["stated_facts"]["claimed_locations"]
        assert len(locations) == 1
        assert sender_profile_low_risk["contradiction_count"] == 0


class TestContactMismatch:
    """Cross-referencing claimed identity against known contacts."""

    def test_high_risk_profile_has_contact_mismatch(self, sender_profile_high_risk):
        verified = sender_profile_high_risk["verified_against_contacts"]
        assert verified["match"] is False
        assert verified["user_has_grandson_named"] == "Takeshi"
        assert "contact_mismatch" in sender_profile_high_risk["risk_factors"]

    def test_user_contacts_have_real_grandson(self, sample_user_profile):
        contacts = sample_user_profile["contacts"]
        grandson = next(c for c in contacts if c["relationship"] == "grandson")
        assert grandson["name"] == "Takeshi"


class TestLoadSenderProfile:
    """Tests for the load_sender_profile tool."""

    def test_returns_stored_profile(self, _patch_firestore, sender_profile_high_risk):
        from agents.behavioral_analyzer import load_sender_profile

        _patch_firestore.collection.return_value.document.return_value.get.return_value = (
            FakeDocSnapshot(sender_profile_high_risk)
        )

        result = load_sender_profile(sender_email="kenji_tanaka@gmail.com")
        assert result["risk_score"] == 0.94
        assert result["message_count"] == 7

    def test_returns_empty_profile_for_new_sender(self, _patch_firestore):
        from agents.behavioral_analyzer import load_sender_profile

        _patch_firestore.collection.return_value.document.return_value.get.return_value = (
            FakeDocSnapshot(None)
        )

        result = load_sender_profile(sender_email="brand-new@example.com")
        assert result["message_count"] == 0
        assert result["risk_score"] == 0.0
