"""Unit tests for the Behavioral Analyzer — longitudinal profiling and contradiction detection."""

from unittest.mock import MagicMock

import pytest

from tests.conftest import FakeDocSnapshot


@pytest.fixture(autouse=True)
def _patch_firestore(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(
        "google.cloud.firestore.Client", lambda *a, **kw: mock_client
    )
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
    """Risk score computation with known signal weights."""

    def test_single_contradiction_signal(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score, SIGNAL_WEIGHTS

        result = compute_risk_score(detected_signals=["LG-1"])
        assert result["risk_score"] == SIGNAL_WEIGHTS["LG-1"]
        assert result["recommendation"] == "monitor"

    def test_contact_mismatch_only(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score, SIGNAL_WEIGHTS

        result = compute_risk_score(detected_signals=["LG-2"])
        assert result["risk_score"] == SIGNAL_WEIGHTS["LG-2"]
        assert result["recommendation"] == "monitor"

    def test_multiple_signals_sum_correctly(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score, SIGNAL_WEIGHTS

        signals = ["LG-1", "LG-2", "LG-5"]
        result = compute_risk_score(detected_signals=signals)
        expected = round(sum(SIGNAL_WEIGHTS[s] for s in signals), 3)
        assert result["risk_score"] == expected
        assert result["recommendation"] == "flag"  # 0.15+0.15+0.12 = 0.42

    def test_many_signals_flag_for_block(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score

        signals = ["LG-1", "LG-2", "LG-3", "LG-4", "LG-5", "LG-8"]
        result = compute_risk_score(detected_signals=signals)
        assert result["risk_score"] >= 0.7
        assert result["recommendation"] == "block"

    def test_empty_signals_zero_risk(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score

        result = compute_risk_score(detected_signals=[])
        assert result["risk_score"] == 0.0
        assert result["recommendation"] == "monitor"

    def test_all_signals_capped_at_one(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score, SIGNAL_WEIGHTS

        all_signals = list(SIGNAL_WEIGHTS.keys())
        result = compute_risk_score(detected_signals=all_signals)
        assert result["risk_score"] <= 1.0
        assert result["recommendation"] == "block"

    def test_unknown_signal_ignored(self, _patch_firestore):
        from agents.behavioral_analyzer import compute_risk_score

        result = compute_risk_score(detected_signals=["UNKNOWN-99"])
        assert result["risk_score"] == 0.0


class TestContradictionDetection:
    """Location contradictions are a key scam indicator."""

    def test_location_change_visible_in_profile(self, sender_profile_high_risk):
        """Profile with Osaka then Tokyo hospital shows contradiction."""
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
        assert grandson["name"] == "Takeshi"  # Not Kenji


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
