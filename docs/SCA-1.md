# SCA-1 — Symbiont Continuity Architecture v0.1

## Purpose

SCA-1 defines continuity of the Symbiont independently from its physical
body.

The Core remains the persistent subject. A Body is a replaceable execution
interface connected through the Bridge.

```text
Symbiont Core
    |
    +-- Identity
    +-- Memory
    +-- Knowledge
    +-- Cognition
    +-- Economy
    +-- Quests
    +-- P2P
    +-- Continuity
    |
  Bridge
    |
  Body A / Body B / Body C
```

SCA-1 does not replace MemoryVault, Memory V2, Economy, Quest, P2P, Body or
Bridge.

## Components

### ContinuityIdentity

Identifies the Symbiont rather than a physical device.

`ContinuityIdentity` can accept an existing node identity when supplied.

The current Core Shadow integration initializes it from the active Core
identity (`id()` and `public_key()`). The standalone `NodeIdentity` Ed25519
adapter remains supported by the continuity component, but is not currently
passed directly by `ContinuityShadow`.

### ContinuityState

A compact description of the current Core state.

It stores versions and hashes, not a duplicate copy of MemoryVault or other
Core databases.

### ContinuityEvent

Represents a significant state transition such as:

- `BODY_REGISTERED`
- `BODY_ATTACHED`
- `BODY_DETACHED`
- `BODY_HANDOFF`
- `BODY_REVOKED`
- `STATE_ROLLBACK`
- future memory/economy/quest/knowledge events

### ContinuityLedger

An append-only event chain.

Each event contains the hash of the previous event. The ledger supports an
optional signer and signature verification. The current Core Shadow
integration uses the hash-linked ledger without passing an external signer.

The ledger is never rewritten during rollback.

### BodyIdentity

Represents a physical body independently from Symbiont identity.

A body can be:

- `DETACHED`
- `ATTACHED`
- `ACTIVE`
- `REVOKED`

### Body Handoff

Transfers the active role from one registered body to another.

The old body becomes detached and the target becomes active. The Core
identity does not change.

### Recovery / Rollback

Rollback creates a new state and a `STATE_ROLLBACK` ledger event. Previous
ledger entries remain intact.

## Safety model

SCA-1 is integrated with Symbiont Core as an optional Shadow contour.

The integration is enabled explicitly through:

`SYMBIONT_SCA1_SHADOW=1`

When enabled, `ContinuityShadow` observes the Core `EventJournal` and
mirrors selected Core events into an independent SCA-1 continuity state and
ledger.

SCA-1 does not replace the Core and does not become the source of truth for
Core data.

The integration invariant is:

`core_mutation = false`

The Shadow observes and records continuity information without mutating
Core state. When the feature flag is disabled, the Core can operate without
the SCA-1 Shadow.

## Initial acceptance tests

- identity creation and validation;
- state version chain;
- persistent signed ledger;
- tamper detection;
- Body A → Body B handoff;
- old Body authorization rejection after handoff;
- revoked Body rejection;
- restart persistence;
- rollback;
- ledger verification after rollback.

## Current implementation status

SCA-1 v0.1 is implemented and integrated with Symbiont Core as an optional
Shadow contour.

Current Shadow version:

`SCA-1-SHADOW/1`

The Shadow observes selected Core events through `EventJournal` and
maintains an independent continuity state and ledger.

Current state categories include:

- `memory_version`
- `knowledge_version`
- `economy_version`
- `quest_version`
- `p2p_version`

Selected Core events are mapped into SCA-1 continuity events, including
memory, learning, economy escrow, quest completion and synchronization
events.

The integrated implementation preserves the original SCA-1 principle:
continuity belongs to the Symbiont, not to a particular physical Body.
