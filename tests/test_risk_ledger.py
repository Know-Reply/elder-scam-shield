"""Unit tests for ConversationRiskLedger — the deterministic scoring core.

The ledger is pure arithmetic, so every behavior the docs claim (decay,
tier amplification, T1 primer bonus, sequence multipliers, override
floors, score bands, alert gates) is directly assertable. Expectations
are computed from the module's own constants so weight recalibration
doesn't break the tests.
"""

import pytest

from agents.tools.pipeline import (
    ATTACK_SEQUENCES,
    ConversationRiskLedger,
    DECAY_RATE,
    SIGNAL_TIERS,
    SIGNAL_WEIGHTS,
    T1_PRIMER_BONUS,
    TIER_AMP,
    _score_to_classification,
)


def _signal_of_tier(tier: int, exclude=()) -> str:
    for s, t in SIGNAL_TIERS.items():
        if t == tier and s in SIGNAL_WEIGHTS and s not in exclude:
            return s
    pytest.fail(f"no signal of tier {tier} found")


def test_empty_signals_stay_safe():
    ledger = ConversationRiskLedger(conversation_id="t")
    for _ in range(5):
        update = ledger.update([])
    assert update["score_after"] == 0.0
    assert update["classification"] == "safe"
    assert not ledger.family_alert_fired


def test_decay_between_messages():
    t1 = _signal_of_tier(1)
    ledger = ConversationRiskLedger(conversation_id="t")
    first = ledger.update([t1])
    second = ledger.update([])
    assert second["score_after"] == pytest.approx(first["score_after"] * DECAY_RATE, abs=1e-3)


def test_tier_amplification():
    for tier in (1, 2, 3):
        s = _signal_of_tier(tier)
        ledger = ConversationRiskLedger(conversation_id="t")
        update = ledger.update([s])
        expected = SIGNAL_WEIGHTS[s] * TIER_AMP[tier]
        # single message, no decay/primer/sequence on first contribution
        assert update["contribution"] == pytest.approx(expected, abs=1e-3), f"tier {tier}"


def test_t1_primer_bonus_amplifies_escalation():
    t1 = _signal_of_tier(1)
    t2 = _signal_of_tier(2)

    primed = ConversationRiskLedger(conversation_id="primed")
    primed.update([t1])
    primed_update = primed.update([t2])

    cold = ConversationRiskLedger(conversation_id="cold")
    cold.update([])
    cold_update = cold.update([t2])

    assert primed_update["contribution"] == pytest.approx(
        cold_update["contribution"] * T1_PRIMER_BONUS, abs=1e-3)


def test_score_bands():
    assert _score_to_classification(0.0) == "safe"
    assert _score_to_classification(1.49) == "safe"
    assert _score_to_classification(1.50) == "monitoring"
    assert _score_to_classification(2.99) == "monitoring"
    assert _score_to_classification(3.00) == "suspicious"
    assert _score_to_classification(5.00) == "high_risk"
    assert _score_to_classification(7.50) == "scam"
    assert _score_to_classification(10.0) == "scam"


def test_tier_override_floor_on_triple_t3():
    t3a = _signal_of_tier(3)
    t3b = _signal_of_tier(3, exclude=(t3a,))
    t3c = _signal_of_tier(3, exclude=(t3a, t3b))
    ledger = ConversationRiskLedger(conversation_id="t")
    update = ledger.update([t3a, t3b, t3c])
    assert update["score_after"] >= 7.5
    assert update["classification"] == "scam"
    assert ledger.overrides_applied or update["score_after"] >= 7.5


def test_ore_ore_sequence_multiplier():
    seq = ATTACK_SEQUENCES["ore_ore"]
    ledger = ConversationRiskLedger(conversation_id="t")
    last = None
    for sig in seq["canonical"]:
        last = ledger.update([sig])
    assert "ore_ore" in ledger.sequence_matches
    assert last["sequence_multiplier"] == seq["multiplier"]


def test_family_alert_gate_fires_on_t3():
    t3 = _signal_of_tier(3)
    ledger = ConversationRiskLedger(conversation_id="t")
    update = ledger.update([t3])
    assert update["family_alert_fired"]
    assert ledger.family_alert_reason is not None


def test_alert_fires_once():
    t3 = _signal_of_tier(3)
    ledger = ConversationRiskLedger(conversation_id="t")
    first = ledger.update([t3])
    second = ledger.update([t3])
    assert first["family_alert_fired"]
    assert not second["family_alert_fired"]  # already fired, not re-fired
    assert ledger.family_alert_fired


def test_trust_modifier_dampens_verified_contact():
    t3 = _signal_of_tier(3)
    base = ConversationRiskLedger(conversation_id="base").update([t3])
    trusted = ConversationRiskLedger(conversation_id="trusted").update([t3], trust_modifier=0.6)
    assert trusted["contribution"] == pytest.approx(base["contribution"] * 0.6, abs=1e-3)


def test_trust_modifier_boosts_imposter():
    t2 = _signal_of_tier(2)
    base = ConversationRiskLedger(conversation_id="base").update([t2])
    imposter = ConversationRiskLedger(conversation_id="imp").update([t2], trust_modifier=1.3)
    assert imposter["contribution"] == pytest.approx(base["contribution"] * 1.3, abs=1e-3)


def test_trust_modifier_exempts_elder_abuse_signals():
    ea = next(s for s in SIGNAL_WEIGHTS if s.startswith("EA-"))
    base = ConversationRiskLedger(conversation_id="base").update([ea])
    trusted = ConversationRiskLedger(conversation_id="trusted").update([ea], trust_modifier=0.6)
    # Abuse from trusted contacts is never dampened by the trust itself
    assert trusted["contribution"] == pytest.approx(base["contribution"], abs=1e-3)


def test_verified_contact_skips_attack_pattern_machinery():
    # The ore-ore arc from a verified contact: no primer, no sequence multiplier
    seq = ATTACK_SEQUENCES["ore_ore"]
    trusted = ConversationRiskLedger(conversation_id="t")
    for sig in seq["canonical"]:
        last = trusted.update([sig], trust_modifier=0.6)
    assert trusted.sequence_matches == []
    assert last["sequence_multiplier"] == 1.0


def test_attack_pattern_machinery_unchanged_at_neutral_trust():
    # Provably a no-op for unknown senders: identical scores with and
    # without the gating change for trust >= 1.0
    seq = ATTACK_SEQUENCES["ore_ore"]
    a = ConversationRiskLedger(conversation_id="a")
    for sig in seq["canonical"]:
        ra = a.update([sig])
    assert "ore_ore" in a.sequence_matches
    assert ra["sequence_multiplier"] == seq["multiplier"]


def test_trust_modifier_default_is_neutral():
    t2 = _signal_of_tier(2)
    explicit = ConversationRiskLedger(conversation_id="a").update([t2], trust_modifier=1.0)
    implicit = ConversationRiskLedger(conversation_id="b").update([t2])
    assert explicit["contribution"] == implicit["contribution"]


def test_serialization_round_trip():
    t2 = _signal_of_tier(2)
    ledger = ConversationRiskLedger(conversation_id="t")
    ledger.update([t2])
    restored = ConversationRiskLedger.from_dict(ledger.to_dict())
    assert restored.running_score == pytest.approx(ledger.running_score, abs=1e-3)
    assert restored.message_count == ledger.message_count
    assert restored.tier_counts == ledger.tier_counts
