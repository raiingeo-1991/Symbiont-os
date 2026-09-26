# SCP-1 — Symbiont Cryptographic Protocol

## Status

**Version:** SCP-1  
**Status:** Experimental / Reference Implementation

SCP-1 is the cryptographic communication protocol designed for Symbiont nodes.

It defines how a Symbiont node identifies itself, signs messages, protects message integrity, and prevents replay of previously accepted messages.

---

## Design Principle

SCP-1 does not replace established cryptographic primitives.

It combines established primitives into a protocol designed for the Symbiont architecture.

The current reference implementation uses:

- Ed25519 for digital signatures
- SHA-256 for identity derivation and fingerprints
- cryptographically random nonces
- timestamps for message freshness
- persistent replay protection
- canonical JSON serialization
- packet identifiers
- Zero-Trust node verification

---

## Node Identity

Each Symbiont node has an Ed25519 key pair.

The public key determines the node identity.

Conceptually:

`public key → SHA-256 → node_id`

The node ID is therefore cryptographically bound to the public key.

A node cannot legitimately claim another node's identity without its private signing key.

---

## SCP-1 Packet

A packet contains:

- `scp`
- `packet_id`
- `type`
- `node_id`
- `public_key`
- `timestamp`
- `nonce`
- `capability`
- `payload`
- `signature`

The complete unsigned packet is canonicalized before signing.

The resulting signature covers the packet contents.

Changing a protected field invalidates the signature.

---

## Packet Integrity

The following fields are protected by the Ed25519 signature:

- node identity
- public key
- packet ID
- timestamp
- nonce
- capability
- message type
- payload

A modified packet must therefore fail cryptographic verification.

---

## Freshness

SCP-1 uses timestamps to reject packets outside the permitted time window.

This limits the useful lifetime of captured packets.

---

## Replay Protection

Every packet contains a nonce.

Accepted nonces are persisted by the reference implementation.

A previously accepted `node_id + nonce` combination cannot be accepted again after a process restart.

This protects against replay attacks across restarts.

---

## Zero-Trust Verification

SCP-1 is integrated with the Symbiont Zero-Trust adapter through
`SCP1ZeroTrust`.

The verification sequence is:

1. Validate packet structure and SCP version.
2. Validate timestamp freshness.
3. Derive and verify node identity from the public key.
4. Verify the Ed25519 signature.
5. Verify that the node is explicitly trusted.
6. Check the persistent replay guard.
7. Accept the packet.

Failure at any stage results in rejection.

Trust is separate from discovery. Discovering a node does not automatically
make that node trusted.

---

## Security Properties

The current implementation has been tested against:

- payload modification
- capability modification
- node ID modification
- public key modification
- packet ID modification
- expired timestamps
- unknown nodes
- replayed packets
- corrupted signatures

The reference implementation has passed these current validation tests.

---

## Scope

SCP-1 currently defines authenticated and integrity-protected node messages
and an optional authenticated envelope for P2P transport.

It does **not** by itself provide:

- encrypted payload confidentiality
- key exchange
- forward secrecy
- production-grade key rotation
- distributed revocation
- consensus
- financial settlement guarantees

Those are separate protocol layers or future versions.

---

## Architecture

SCP-1 remains a separate security/protocol component rather than becoming
part of the Core's application logic.

The current optional P2P integration is:

`NodeIdentity → SCP-1 → SCP1ZeroTrust → P2P envelope → Core P2P handling`

When `SYMBIONT_SCP1_P2P` is enabled, SCP-1 becomes the authenticated
cryptographic envelope around the existing P2P packet.

The existing Core P2P identity verification remains in place after the
SCP-1 envelope is accepted. SCP-1 therefore strengthens the transport
boundary without replacing the existing Core P2P compatibility check.

When the feature flag is disabled, the existing P2P transport path remains
available without the SCP-1 envelope.

---

## Reference Implementation

The current reference implementation is located in:

`core/crypto_protocol.py`

The Zero-Trust adapter is located in:

`core/scp1_zerotrust.py`

Node identity is implemented in:

`core/node_identity.py`

---

## Versioning

The protocol version is currently:

**SCP-1**

Future incompatible protocol changes should use a new protocol version rather than silently changing SCP-1 behavior.

---

## Final Principle

SCP-1 is intended to provide a cryptographic foundation for communication between independent Symbiont nodes while keeping identity and trust separate from the Symbiont Core.
