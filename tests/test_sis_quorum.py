from dataclasses import replace

import pytest

from core.sss.sis_quorum import (
    Attestation,
    QuorumVerifier,
    Witness,
)
from core.sss.sis_witness import Anchor, WitnessError, ZERO_HASH


def make_system():
    original = Anchor(12, "a" * 64)
    forged = Anchor(12, "f" * 64)
    keys = {
        "sym-a": b"key-for-sym-a-0001",
        "sym-b": b"key-for-sym-b-0002",
        "sym-c": b"key-for-sym-c-0003",
        "sym-d": b"key-for-sym-d-0004",
    }
    witnesses = {
        name: Witness(name, key, original)
        for name, key in keys.items()
    }
    verifier = QuorumVerifier(keys, quorum=3)
    return original, forged, keys, witnesses, verifier


def test_three_registered_witnesses_reach_quorum():
    original, _, _, witnesses, verifier = make_system()
    votes = [
        witnesses[name].attest(original)
        for name in ("sym-a", "sym-b", "sym-c")
    ]

    result = verifier.verify(original, votes)
    assert result["accepted"] is True
    assert result["valid_count"] == 3
    assert result["valid_witnesses"] == ["sym-a", "sym-b", "sym-c"]


def test_honest_witnesses_do_not_attest_to_forged_anchor():
    _, forged, _, witnesses, verifier = make_system()
    votes = [
        witnesses[name].attest(forged)
        for name in witnesses
    ]

    result = verifier.verify(forged, [vote for vote in votes if vote])
    assert result["accepted"] is False
    assert result["valid_count"] == 0


def test_two_compromised_keys_do_not_reach_three_member_quorum():
    _, forged, keys, _, verifier = make_system()
    votes = [
        Witness(name, keys[name], forged).attest(forged)
        for name in ("sym-a", "sym-b")
    ]

    result = verifier.verify(forged, votes)
    assert result["accepted"] is False
    assert result["valid_count"] == 2


def test_unknown_witness_is_not_counted():
    original, _, _, witnesses, verifier = make_system()
    votes = [
        witnesses["sym-a"].attest(original),
        witnesses["sym-b"].attest(original),
        Witness(
            "unregistered-node", b"fake-key-12345678", original
        ).attest(original),
    ]

    result = verifier.verify(original, votes)
    assert result["accepted"] is False
    assert result["valid_count"] == 2


def test_duplicate_vote_counts_once():
    original, _, _, witnesses, verifier = make_system()
    vote = witnesses["sym-a"].attest(original)

    result = verifier.verify(original, [vote, vote, vote])
    assert result["accepted"] is False
    assert result["valid_count"] == 1


def test_modified_mac_is_rejected():
    original, _, _, witnesses, verifier = make_system()
    vote = witnesses["sym-a"].attest(original)
    modified = replace(vote, mac="0" * 64)

    result = verifier.verify(original, [modified])
    assert result["valid_count"] == 0


def test_old_attestation_cannot_confirm_different_anchor():
    original, forged, _, witnesses, verifier = make_system()
    vote = witnesses["sym-a"].attest(original)

    result = verifier.verify(forged, [vote])
    assert result["accepted"] is False
    assert result["valid_count"] == 0


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError):
        QuorumVerifier({}, quorum=1)

    with pytest.raises(ValueError):
        QuorumVerifier({"sym-a": b"short"}, quorum=1)

    with pytest.raises(ValueError):
        QuorumVerifier({"sym-a": b"key-for-sym-a-0001"}, quorum=0)

    with pytest.raises(ValueError):
        QuorumVerifier({"sym-a": b"key-for-sym-a-0001"}, quorum=True)


def test_invalid_candidate_anchor_is_rejected():
    _, _, _, _, verifier = make_system()

    with pytest.raises(WitnessError):
        verifier.verify(Anchor(0, "a" * 64), [])


def test_compromised_quorum_can_confirm_forgery_limitation():
    _, forged, keys, _, verifier = make_system()
    votes = [
        Witness(name, keys[name], forged).attest(forged)
        for name in ("sym-a", "sym-b", "sym-c")
    ]

    result = verifier.verify(forged, votes)
    assert result["accepted"] is True
    assert result["valid_count"] == 3


def test_malformed_attestation_is_ignored():
    original, _, _, witnesses, verifier = make_system()
    vote = witnesses["sym-a"].attest(original)
    malformed = Attestation("sym-b", original.sequence, original.last_hash, None)

    result = verifier.verify(original, [vote, malformed])
    assert result["valid_count"] == 1
    assert result["accepted"] is False
