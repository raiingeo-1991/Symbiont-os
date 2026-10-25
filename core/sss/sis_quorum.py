"""SIS-007: experimental collective witness verification.

HMAC is used for a standard-library-only model. This is not a distributed
consensus protocol, and configured witness keys must be trusted independently.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Iterable, Mapping

from core.sss.sis_witness import Anchor, WitnessError


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


@dataclass(frozen=True)
class Attestation:
    witness_id: str
    sequence: int
    last_hash: str
    mac: str


def _validate_anchor(anchor: Anchor) -> None:
    if not isinstance(anchor, Anchor):
        raise WitnessError("Expected an Anchor")
    if (
        not isinstance(anchor.sequence, int)
        or isinstance(anchor.sequence, bool)
        or anchor.sequence < 0
    ):
        raise WitnessError("Invalid anchor sequence")
    if (
        not isinstance(anchor.last_hash, str)
        or len(anchor.last_hash) != 64
        or any(c not in "0123456789abcdef" for c in anchor.last_hash)
    ):
        raise WitnessError("Invalid anchor hash")
    if anchor.sequence == 0 and anchor.last_hash != "0" * 64:
        raise WitnessError("Sequence zero must use ZERO_HASH")
    if anchor.sequence > 0 and anchor.last_hash == "0" * 64:
        raise WitnessError("Nonzero sequence cannot use ZERO_HASH")


class Witness:
    """Test-model witness that attests only to its pre-trusted anchor."""

    def __init__(self, witness_id: str, key: bytes, trusted_anchor: Anchor):
        if not isinstance(witness_id, str) or not witness_id.strip():
            raise ValueError("witness_id is required")
        if not isinstance(key, bytes) or len(key) < 16:
            raise ValueError("witness key must be at least 16 bytes")
        _validate_anchor(trusted_anchor)

        self.witness_id = witness_id
        self._key = key
        self.trusted_anchor = trusted_anchor

    @staticmethod
    def _payload(witness_id: str, anchor: Anchor) -> dict:
        return {
            "witness_id": witness_id,
            "sequence": anchor.sequence,
            "last_hash": anchor.last_hash,
        }

    def attest(self, anchor: Anchor) -> Attestation | None:
        _validate_anchor(anchor)
        if anchor != self.trusted_anchor:
            return None

        mac = hmac.new(
            self._key,
            canonical(self._payload(self.witness_id, anchor)),
            hashlib.sha256,
        ).hexdigest()
        return Attestation(
            self.witness_id, anchor.sequence, anchor.last_hash, mac
        )


class QuorumVerifier:
    """Verify distinct registered HMAC attestations for one exact anchor."""

    def __init__(
        self, registered_keys: Mapping[str, bytes], quorum: int
    ):
        keys = dict(registered_keys)
        if not keys:
            raise ValueError("at least one registered witness is required")
        if any(
            not isinstance(witness_id, str) or not witness_id.strip()
            for witness_id in keys
        ):
            raise ValueError("witness IDs must be non-empty strings")
        if any(not isinstance(key, bytes) or len(key) < 16 for key in keys.values()):
            raise ValueError("each witness key must be at least 16 bytes")
        if (
            not isinstance(quorum, int)
            or isinstance(quorum, bool)
            or not 1 <= quorum <= len(keys)
        ):
            raise ValueError("invalid quorum")

        self._keys = keys
        self.quorum = quorum

    def verify(
        self, candidate: Anchor, attestations: Iterable[Attestation]
    ) -> dict:
        _validate_anchor(candidate)
        accepted = set()

        for item in attestations:
            if not isinstance(item, Attestation):
                continue
            witness_id = item.witness_id
            if not isinstance(witness_id, str) or witness_id not in self._keys:
                continue
            if witness_id in accepted:
                continue
            if (
                item.sequence != candidate.sequence
                or item.last_hash != candidate.last_hash
                or not isinstance(item.mac, str)
            ):
                continue

            payload = Witness._payload(witness_id, candidate)
            expected = hmac.new(
                self._keys[witness_id], canonical(payload), hashlib.sha256
            ).hexdigest()
            if hmac.compare_digest(expected, item.mac):
                accepted.add(witness_id)

        valid_witnesses = sorted(accepted)
        return {
            "accepted": len(accepted) >= self.quorum,
            "valid_witnesses": valid_witnesses,
            "valid_count": len(accepted),
            "required_quorum": self.quorum,
        }
