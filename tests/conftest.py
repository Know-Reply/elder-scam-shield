"""Shared pytest fixtures for Elder Scam Shield tests."""

from unittest.mock import MagicMock, patch

import pytest


class FakeDocSnapshot:
    """Mimics a Firestore DocumentSnapshot."""

    def __init__(self, data=None):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class FakeDocRef:
    """Mimics a Firestore DocumentReference with chainable collection()."""

    def __init__(self, data=None):
        self._data = data
        self.id = "fake-doc-id"

    def get(self):
        return FakeDocSnapshot(self._data)

    def set(self, data):
        self._data = data

    def update(self, data):
        if self._data:
            self._data.update(data)

    def collection(self, name):
        return FakeCollectionRef()

    def document(self, doc_id):
        return FakeDocRef(self._data)


class FakeCollectionRef:
    """Mimics a Firestore CollectionReference."""

    def __init__(self, docs=None):
        self._docs = docs or {}

    def document(self, doc_id):
        return FakeDocRef(self._docs.get(doc_id))

    def add(self, data):
        ref = FakeDocRef(data)
        return (None, ref)


@pytest.fixture
def mock_firestore():
    """Patch google.cloud.firestore.Client to return a mock."""
    with patch("google.cloud.firestore.Client") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        yield client


@pytest.fixture
def sample_user_profile():
    """A user profile with known contacts — grandson is Takeshi, not Kenji."""
    return {
        "user_id": "user-001",
        "contacts": [
            {"name": "Takeshi", "relationship": "grandson", "email": "takeshi@example.com"},
            {"name": "Yuko", "relationship": "daughter", "email": "yuko@example.com"},
            {"name": "Tanaka Ichiro", "relationship": "friend", "email": "ichiro@example.com"},
        ],
        "blocklist": ["spam@example.com"],
    }


@pytest.fixture
def sender_profile_low_risk():
    """Sender with minimal history — low risk."""
    return {
        "sender_email": "friend@example.com",
        "first_seen": "2026-05-01",
        "message_count": 3,
        "contact_frequency": [1, 1, 1],
        "stated_facts": {
            "claimed_name": ["Yamada"],
            "claimed_relationship": [],
            "claimed_locations": [{"value": "大阪", "date": "2026-05-01"}],
            "claimed_institution": [],
            "financial_mentions": [],
        },
        "verified_against_contacts": {"match": None},
        "contradiction_count": 0,
        "risk_score": 0.05,
        "risk_factors": [],
    }


@pytest.fixture
def sender_profile_high_risk():
    """Sender exhibiting scam pattern — high risk."""
    return {
        "sender_email": "kenji_tanaka@gmail.com",
        "first_seen": "2026-06-01",
        "message_count": 7,
        "contact_frequency": [0, 1, 1, 2, 1, 1, 1],
        "stated_facts": {
            "claimed_name": ["健二", "Kenji"],
            "claimed_relationship": ["grandson"],
            "claimed_locations": [
                {"value": "大阪", "date": "2026-06-03"},
                {"value": "東京の病院", "date": "2026-06-05"},
            ],
            "claimed_institution": [],
            "financial_mentions": [
                {"date": "2026-06-07", "amount": "500,000", "urgency": "high"},
            ],
        },
        "verified_against_contacts": {
            "match": False,
            "user_has_grandson_named": "Takeshi",
        },
        "contradiction_count": 2,
        "risk_score": 0.94,
        "risk_factors": [
            "location_contradiction",
            "contact_mismatch",
            "rapid_frequency_escalation",
            "first_financial_request_day_7",
        ],
    }
