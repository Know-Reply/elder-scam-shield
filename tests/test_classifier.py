"""Unit tests for Inbound Classifier agent tools and classification logic."""

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FakeDocRef, FakeDocSnapshot


# ---------------------------------------------------------------------------
# We patch Firestore at import time so the module-level `db = firestore.Client()`
# doesn't try to reach a real GCP project.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_firestore(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr("agents.inbound_classifier.db", mock_client)
    return mock_client


class TestReadContactList:
    """Tests for the read_contact_list tool."""

    def test_returns_contacts_for_known_user(self, sample_user_profile, _patch_firestore):
        from agents.inbound_classifier import read_contact_list

        doc_data = sample_user_profile
        _patch_firestore.collection.return_value.document.return_value.get.return_value = (
            FakeDocSnapshot(doc_data)
        )

        result = read_contact_list(user_id="user-001")

        assert len(result["contacts"]) == 3
        assert result["blocklist"] == ["spam@example.com"]

    def test_returns_empty_for_unknown_user(self, _patch_firestore):
        from agents.inbound_classifier import read_contact_list

        _patch_firestore.collection.return_value.document.return_value.get.return_value = (
            FakeDocSnapshot(None)
        )

        result = read_contact_list(user_id="unknown")
        assert result == {"contacts": [], "blocklist": []}


class TestWriteClassification:
    """Tests for the write_classification tool."""

    def test_writes_scam_classification(self, _patch_firestore):
        from agents.inbound_classifier import write_classification

        mock_set = MagicMock()
        (_patch_firestore.collection.return_value
         .document.return_value
         .collection.return_value
         .document.return_value
         .collection.return_value
         .document.return_value).set = mock_set

        result = write_classification(
            user_id="user-001",
            sender_id="scammer@example.com",
            message_id="msg-001",
            classification="scam",
            confidence=0.95,
            detected_signals=["PM-6", "PM-3"],
            extracted_facts={
                "claimed_name": None,
                "claimed_relationship": None,
                "claimed_location": None,
                "claimed_institution": "税務署",
                "financial_mention": {"amount": "300,000", "urgency": "high"},
                "other_facts": [],
            },
        )

        assert result["status"] == "written"
        assert result["message_id"] == "msg-001"

    def test_writes_safe_classification_with_facts(self, _patch_firestore):
        from agents.inbound_classifier import write_classification

        mock_set = MagicMock()
        (_patch_firestore.collection.return_value
         .document.return_value
         .collection.return_value
         .document.return_value
         .collection.return_value
         .document.return_value).set = mock_set

        result = write_classification(
            user_id="user-001",
            sender_id="kenji@example.com",
            message_id="msg-002",
            classification="safe",
            confidence=0.90,
            detected_signals=[],
            extracted_facts={
                "claimed_name": "健二",
                "claimed_relationship": "grandson",
                "claimed_location": "大阪",
                "claimed_institution": None,
                "financial_mention": None,
                "other_facts": ["says he started a new job"],
            },
        )

        assert result["status"] == "written"


class TestPublishClassifiedEvent:
    """Tests for the publish_classified_event tool."""

    def test_publishes_event_with_correct_structure(self, _patch_firestore):
        from agents.inbound_classifier import publish_classified_event

        result = publish_classified_event(
            sender_id="scammer@example.com",
            classification="scam",
            confidence=0.95,
            extracted_facts={"claimed_institution": "税務署"},
            detected_signals=["PM-6", "PM-3"],
        )

        assert result["event"] == "message.classified"
        assert result["classification"] == "scam"
        assert result["confidence"] == 0.95
        assert "PM-6" in result["detected_signals"]
        assert result["extracted_facts"]["claimed_institution"] == "税務署"

    def test_safe_message_publishes_extracted_facts(self, _patch_firestore):
        from agents.inbound_classifier import publish_classified_event

        facts = {"claimed_name": "Kenji", "claimed_location": "大阪"}
        result = publish_classified_event(
            sender_id="kenji@example.com",
            classification="safe",
            confidence=0.88,
            extracted_facts=facts,
            detected_signals=[],
        )

        assert result["classification"] == "safe"
        assert result["extracted_facts"]["claimed_name"] == "Kenji"
        assert result["extracted_facts"]["claimed_location"] == "大阪"


class TestIdentityClaimDetection:
    """Tests verifying PM-11 identity claim signal scenarios."""

    def test_identity_claim_in_detected_signals(self, _patch_firestore):
        from agents.inbound_classifier import publish_classified_event

        result = publish_classified_event(
            sender_id="unknown@example.com",
            classification="suspicious",
            confidence=0.60,
            extracted_facts={
                "claimed_name": "健二",
                "claimed_relationship": "grandson",
            },
            detected_signals=["PM-11"],
        )

        assert "PM-11" in result["detected_signals"]
        assert result["extracted_facts"]["claimed_relationship"] == "grandson"


class TestMultipleSignalDetection:
    """Scam messages typically trigger multiple signals at once."""

    def test_fictitious_billing_triggers_multiple_signals(self, _patch_firestore):
        """架空請求 pattern: legal threat + financial demand + urgency."""
        from agents.inbound_classifier import publish_classified_event

        signals = ["PM-1", "PM-3", "PM-6"]  # urgency + financial + legal threat
        result = publish_classified_event(
            sender_id="invoice-scam@example.com",
            classification="scam",
            confidence=0.97,
            extracted_facts={
                "claimed_institution": "法務省",
                "financial_mention": {"amount": "980,000", "urgency": "high"},
            },
            detected_signals=signals,
        )

        assert len(result["detected_signals"]) == 3
        assert result["classification"] == "scam"
        assert result["confidence"] > 0.9

    def test_ore_ore_sagi_pattern(self, _patch_firestore):
        """オレオレ詐欺 pattern: identity claim + emotional crisis + financial."""
        from agents.inbound_classifier import publish_classified_event

        signals = ["PM-10", "PM-11", "PM-3"]
        result = publish_classified_event(
            sender_id="impersonator@example.com",
            classification="scam",
            confidence=0.93,
            extracted_facts={
                "claimed_name": "健二",
                "claimed_relationship": "grandson",
                "financial_mention": {"amount": "500,000", "urgency": "high"},
            },
            detected_signals=signals,
        )

        assert set(result["detected_signals"]) == {"PM-10", "PM-11", "PM-3"}
