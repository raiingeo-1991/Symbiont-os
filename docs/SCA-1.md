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

The first implementation can derive this identity from the existing
`NodeIdentity` Ed25519 identity.

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

Each event contains the hash of the previous event. When an existing
`NodeIdentity` signer is supplied, events are signed with the existing
Ed25519 implementation.

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

SCA-1 is currently standalone.

It does not modify `symbiont_core.py` and does not automatically change
existing Core behavior.

Integration should happen later through a feature flag and Shadow Mode,
after the standalone tests and failure scenarios are accepted.

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

SCA-1 v0.1 standalone implementation is complete for the initial model.

The next integration stage is deliberately separate: connect SCA-1 to the
real Core state and Bridge only after the standalone contract is stable.
