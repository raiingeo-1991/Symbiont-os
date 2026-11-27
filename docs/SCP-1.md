# SCP-1 — Symbiont Cryptographic Protocol

## Status

**Version:** SCP-1
**Status:** Experimental / Reference Implementation

SCP-1 is the cryptographic communication protocol designed for Symbiont nodes.

It defines how a Symbiont node identifies itself, signs messages, protects message integrity, and prevents replay of previously accepted messages.

The current implementation includes an optional authenticated P2P integration with mutual TCP handshake and Core-to-Node trust binding.

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

The replay guard also protects against concurrent duplicate acceptance across guard instances. Failed persistence operations do not silently accept a nonce, and corrupted replay storage fails closed.

This protects against replay attacks across restarts and concurrent processing.

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

## P2P Integration — Stage 1B

The optional integration is enabled with:

`SYMBIONT_SCP1_P2P=1`

Stage 1B extends the authenticated SCP-1 envelope with a mutual TCP handshake and explicit binding between a Symbiont Core identity and a Node identity.

### Discovery

UDP Beacon announcements are authenticated and checked for:

- valid SCP-1 signature
- expected node identity
- packet freshness
- packet replay
- required discovery capability

Legacy or modified Beacon packets are rejected.

Discovery only identifies a communicating node. It does not grant trust or automatically register the node as trusted.

### Core-to-Node trust binding

The P2P trust integration uses the Trust Store Kernel (TSK) and PeerDirectory.

For TSK-derived trust, the implementation checks:

- an existing peer record
- matching Core identity and Core public-key fingerprint
- matching Node identity and Node public-key fingerprint
- an owner-confirmed `CoreNodeBinding`
- an active TSK trust record with the required trust level

A missing or mismatched binding is rejected.

TSK-derived trust is synchronized into the SCP-1 Zero-Trust adapter. Revoking TSK trust removes the derived trust during the next synchronization.

Explicit environment-configured trusted nodes remain a separate supported trust source. They must not be confused with owner-confirmed TSK bindings.

### Mutual TCP handshake

Before processing an SCP-1 P2P operation, both nodes complete a mutual handshake:

`HELLO → CHALLENGE → FINISH → ESTABLISHED`

The handshake correlates messages using a hello identifier and session identifier, checks the expected peer identity, validates the challenge and rejects invalid message order, replayed HELLO messages and substituted session identifiers.

The transport layer performs SCP-1 verification of incoming handshake packets before passing their payloads to the handshake state machine.

### Operation and response binding

After the handshake, the TCP operation is checked against:

- the expected peer Core identity
- the authenticated Node identity and fingerprint
- the owner-confirmed Core-to-Node binding
- the request sender identity
- the established session identifier
- the expected message type and capability

The response is also checked against the expected peer identity, binding and session identifier.

Legacy TCP operations are rejected when SCP-1 P2P mode is enabled.

### Implementation boundary

The handshake state machine does not independently perform Zero-Trust verification. Verification is performed by the surrounding transport integration.

The current handshake carries `core_id` and `core_signature` fields, but the implementation described here does not establish a separate verification of a Core signature. The authenticated SCP-1 packet signature is a Node identity signature.

A session identifier correlates messages within a handshake session. It is not a key exchange and does not provide encryption or forward secrecy.

---

## Security Properties

The current implementation has tests covering:

- payload and protected packet-field modification
- capability modification
- node ID and public-key mismatch
- packet ID modification
- expired timestamps
- unknown or untrusted nodes
- replayed packets
- corrupted signatures
- replay persistence and concurrent duplicate acceptance
- authenticated UDP Beacon validation and legacy Beacon rejection
- mutual TCP handshake and invalid handshake transitions
- owner-confirmed Core-to-Node binding and fingerprint mismatch
- TSK trust synchronization and revocation
- sender, response and session binding in P2P operations
- rejection of legacy TCP operations in SCP-1 P2P mode

These tests cover the reference implementation and its integration boundaries. They do not establish production-grade security certification.

---

## Scope and Limitations

SCP-1 currently provides authenticated and integrity-protected node messages and an optional authenticated P2P transport envelope.

It does **not** by itself provide:

- encrypted payload confidentiality
- key exchange
- forward secrecy
- production-grade key rotation
- distributed revocation
- consensus
- financial settlement guarantees
- a separately verified Core signature in the current handshake

Those are separate protocol layers or future work.

---

## Architecture

SCP-1 remains a separate security/protocol component rather than becoming
part of the Core's application logic.

The optional P2P integration is:

`NodeIdentity → SCP-1 → SCP1ZeroTrust → PeerSecurity / TSK binding → P2P transport`

When `SYMBIONT_SCP1_P2P` is enabled, SCP-1 provides the authenticated
cryptographic envelope around the existing P2P packet.

The integration adds mutual TCP handshake, peer and session checks, and
Core-to-Node trust binding without replacing the existing P2P transport.

When the feature flag is disabled, the existing P2P transport path remains
available without the SCP-1 envelope.

---

## Reference Implementation

The current reference implementation is located in:

- `core/crypto_protocol.py`
- `core/scp1_zerotrust.py`
- `core/node_handshake.py`
- `core/peer_security.py`
- `symbiont_core.py`

Node identity is implemented in:

`core/node_identity.py`

Relevant integration tests are located in `tests/`, including the SCP-1
handshake, trust synchronization, replay, Beacon and live TCP tests.

---

## Versioning

The protocol version is currently:

**SCP-1**

Future incompatible protocol changes should use a new protocol version rather than silently changing SCP-1 behavior.

---

## Final Principle

SCP-1 is intended to provide a cryptographic foundation for communication between independent Symbiont nodes while keeping identity and trust separate from the Symbiont Core.
