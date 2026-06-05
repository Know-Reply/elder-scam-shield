"""Unit tests for the Outbound Interceptor — catches sensitive data leaving the user."""

import hashlib
from unittest.mock import MagicMock

import pytest

from tests.conftest import FakeDocRef, FakeDocSnapshot


@pytest.fixture(autouse=True)
def _patch_firestore(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(
        "google.cloud.firestore.Client", lambda *a, **kw: mock_client
    )
    return mock_client


class TestContentHashing:
    """Never store raw content — only SHA-256 hashes for audit."""

    def test_content_hash_is_sha256(self):
        from agents.outbound_interceptor import _content_hash

        content = "口座番号: 1234567890"
        result = _content_hash(content)
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert result == expected

    def test_different_content_different_hash(self):
        from agents.outbound_interceptor import _content_hash

        h1 = _content_hash("message A")
        h2 = _content_hash("message B")
        assert h1 != h2

    def test_hash_is_deterministic(self):
        from agents.outbound_interceptor import _content_hash

        content = "振込先: みずほ銀行"
        assert _content_hash(content) == _content_hash(content)


class TestCompoundRisk:
    """Compound risk combines signal weights with sender risk."""

    def test_bank_details_high_sender_triggers_max_risk(self):
        from agents.outbound_interceptor import _compound_risk

        # OB-2 (bank details) weight=0.7, sender_risk=0.9
        risk = _compound_risk(["OB-2"], sender_risk=0.9)
        # (0.7 / 2.0) * max(0.9, 0.5) = 0.35 * 0.9 = 0.315
        assert 0.3 < risk < 0.4

    def test_transfer_instruction_high_risk(self):
        from agents.outbound_interceptor import _compound_risk

        # OB-3 (transfer) weight=0.8
        risk = _compound_risk(["OB-3"], sender_risk=0.8)
        # (0.8 / 2.0) * 0.8 = 0.32
        assert risk > 0.3

    def test_cm4_urgency_compound_near_max(self):
        from agents.outbound_interceptor import _compound_risk

        # CM-4 weight=0.9
        risk = _compound_risk(["CM-4"], sender_risk=0.95)
        # (0.9 / 2.0) * 0.95 = 0.4275
        assert risk > 0.4

    def test_multiple_signals_accumulate(self):
        from agents.outbound_interceptor import _compound_risk

        single = _compound_risk(["OB-1"], sender_risk=0.5)
        double = _compound_risk(["OB-1", "OB-2"], sender_risk=0.5)
        assert double > single

    def test_low_sender_risk_floors_at_half(self):
        from agents.outbound_interceptor import _compound_risk

        # Even with sender_risk=0.0, max(0.0, 0.5) = 0.5 is used
        risk = _compound_risk(["OB-2"], sender_risk=0.0)
        expected = min(min(0.7 / 2.0, 1.0) * 0.5, 1.0)
        assert risk == pytest.approx(expected)

    def test_no_signals_zero_risk(self):
        from agents.outbound_interceptor import _compound_risk

        risk = _compound_risk([], sender_risk=0.9)
        assert risk == 0.0

    def test_compound_risk_capped_at_one(self):
        from agents.outbound_interceptor import _compound_risk, SIGNAL_WEIGHTS

        all_signals = list(SIGNAL_WEIGHTS.keys())
        risk = _compound_risk(all_signals, sender_risk=1.0)
        assert risk <= 1.0


class TestHoldOutbound:
    """Tests for the hold_outbound tool."""

    def test_bank_details_triggers_hold(self, _patch_firestore):
        from agents.outbound_interceptor import hold_outbound

        mock_add = MagicMock(return_value=(None, FakeDocRef()))
        _patch_firestore.collection.return_value.add = mock_add

        result = hold_outbound(
            user_id="user-001",
            held_action="email_reply",
            recipient_id="scammer@example.com",
            content="口座番号は1234567890です。みずほ銀行新宿支店。",
            signals=["OB-2"],
            sender_risk=0.8,
            reason="Bank account details detected in reply to high-risk sender",
        )

        assert result["a2a_publish"]["event"] == "outbound.held"
        assert "held_content_hash" in result["a2a_publish"]
        # Content must NOT appear in the record or event
        assert "口座番号" not in str(result["hold"])
        assert "1234567890" not in str(result["hold"])

    def test_hold_record_never_contains_raw_content(self, _patch_firestore):
        from agents.outbound_interceptor import hold_outbound

        _patch_firestore.collection.return_value.add = MagicMock(
            return_value=(None, FakeDocRef())
        )

        content = "マイナンバー: 123456789012"
        result = hold_outbound(
            user_id="user-001",
            held_action="email_reply",
            recipient_id="unknown@example.com",
            content=content,
            signals=["OB-1"],
            sender_risk=0.5,
            reason="PII detected",
        )

        hold_str = str(result["hold"])
        assert "123456789012" not in hold_str
        assert "マイナンバー" not in hold_str
        # But the hash IS present
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert result["hold"]["held_content_hash"] == expected_hash


class TestCheckSenderRisk:
    """Tests for the check_sender_risk tool."""

    def test_returns_risk_for_known_sender(self, _patch_firestore, sender_profile_high_risk):
        from agents.outbound_interceptor import check_sender_risk

        _patch_firestore.collection.return_value.document.return_value.get.return_value = (
            FakeDocSnapshot(sender_profile_high_risk)
        )

        result = check_sender_risk(sender_id="kenji_tanaka@gmail.com")
        assert result["risk_score"] == 0.94
        assert "location_contradiction" in result["risk_factors"]

    def test_returns_zero_for_unknown_sender(self, _patch_firestore):
        from agents.outbound_interceptor import check_sender_risk

        _patch_firestore.collection.return_value.document.return_value.get.return_value = (
            FakeDocSnapshot(None)
        )

        result = check_sender_risk(sender_id="unknown@example.com")
        assert result["risk_score"] == 0.0
        assert result["risk_factors"] == []


class TestLowRiskSenderPiiWarn:
    """Low-risk sender + PII only should result in lower compound risk (warn territory)."""

    def test_pii_only_low_sender_low_compound(self):
        from agents.outbound_interceptor import _compound_risk

        # OB-1 (PII) weight=0.3, sender_risk=0.1 -> floors at 0.5
        risk = _compound_risk(["OB-1"], sender_risk=0.1)
        # (0.3 / 2.0) * 0.5 = 0.075
        assert risk < 0.1
        # This is in warn territory per the agent's decision logic
