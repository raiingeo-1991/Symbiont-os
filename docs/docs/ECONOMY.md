# Symbiont Economy

## Status

The current implementation provides a local wallet, daily food allocation,
Quest rewards, escrow and secure settlement.

The economic layer is implemented as a stateful component of Symbiont Core.
Quest settlement is connected to the security layer through `SecureSettlement`.

The broader economic model described in the Symbiont vision — including
reputation, witnesses and arbitration — remains a future extension and is
not represented as completed functionality here.

---

## Wallet

Each Symbiont has a local wallet containing:

- current balance;
- lifetime received amount;
- lifetime spent amount.

Wallet state is persisted in the Core state file.

Economic mutations are recorded in the EventJournal.

---

## Food Allocation

The Economy contains a daily food allocation mechanism.

The allocation is controlled by the configured food budget and is recorded
as an economic journal event.

The current implementation therefore contains the mechanism for a basic
daily threshold, while the broader economic policy remains part of the
project's conceptual model.

---

## Quest Economy

A Quest may contain a reward.

For delegated quests, the reward is reserved before the quest is sent to the
remote Symbiont.

The intended execution path is:

`Quest → SecureSettlement → Economy Escrow → P2P → Result → Settlement`

The Economy remains responsible for wallet state and escrow state.

---

## Escrow

Quest escrow currently supports four explicit states:

- `ESCROW`
- `RELEASED`
- `REFUNDED`
- `FROZEN`

### Reserve

`reserve_quest()` removes the reward from the available wallet balance and
creates an escrow record.

The escrow record stores information including:

- quest ID;
- creator node;
- worker node;
- creator type;
- worker type;
- reward;
- currency;
- creation time;
- expiration time;
- optional proof;
- escrow state.

### Release

`release_quest()` transfers a reserved reward back into the wallet as a
received amount and marks the escrow as `RELEASED`.

A frozen escrow may also be released.

### Refund

`refund_quest()` returns the reserved reward to the wallet and marks the
escrow as `REFUNDED`.

A frozen escrow may also be refunded.

### Freeze

`freeze_quest()` changes an active escrow from `ESCROW` to `FROZEN` and
records the reason.

Freezing prevents the reward from silently disappearing when settlement
cannot safely complete.

---

## Secure Settlement

Quest delegation does not directly manipulate Economy state when the
security settlement layer is available.

`SecureSettlement` provides the authorization boundary while Economy remains
the owner of balances and escrow state.

Conceptually:

`Permission / Security → SecureSettlement → Economy`

This separation keeps authorization and economic state as distinct
responsibilities.

---

## Quest Completion

The current delegated Quest flow is:

1. Check that the creator has enough balance.
2. Create the Quest.
3. Reserve the reward in escrow.
4. Send the Quest through P2P.
5. Receive the remote result.
6. Release the escrow when the Quest is reported as completed.
7. Freeze the escrow if completion is reported but settlement release fails.
8. Refund the escrow when the peer is unavailable or rejects the Quest.

The current incoming Quest handler can execute the requested cognitive
operation and return a `COMPLETED` result.

This is not yet equivalent to a general-purpose proof-verification system.

---

## Proof

The Economy escrow record already contains an optional `proof` field.

However, the current canonical implementation does not yet provide a complete
machine-verifiable proof pipeline that independently establishes whether a
Quest was objectively completed.

Therefore:

`proof field ≠ completed proof-verification system`

A future proof layer must be integrated only after its contract and existing
Quest flow have been audited.

---

## Reputation and Rank

The current Quest model contains:

`required_rank`

This allows a Quest to carry a required rank value.

However, the canonical implementation does not currently contain a complete
node reputation system that:

- calculates reputation from Quest history;
- derives rank from verified outcomes;
- automatically changes rank based on behavior;
- enforces rank requirements against incoming Quest execution.

Memory ranking functions are unrelated to social or node reputation and
should not be interpreted as a reputation system.

---

## Witnesses and Arbitration

The project vision describes witnesses and arbitration as mechanisms for
handling disputed Quest completion.

Those mechanisms are not currently implemented as a complete canonical
runtime subsystem.

They therefore remain part of the planned economic model rather than
completed functionality.

---

## Economic State Integrity

Economic transitions are recorded through the Core EventJournal.

Current escrow transitions produce events including:

- `economy.escrow_reserved`
- `economy.escrow_released`
- `economy.escrow_refunded`
- `economy.escrow_frozen`

When SCA-1 Shadow is enabled, these events can also be observed by the
continuity layer and represented in its independent continuity ledger.

---

## Current Implementation Boundary

Implemented:

- local wallet;
- wallet persistence;
- daily food allocation mechanism;
- Quest rewards;
- escrow reservation;
- escrow release;
- escrow refund;
- escrow freeze;
- secure settlement boundary;
- economic event journaling;
- SCA-1 observation of escrow events.

Not yet implemented as a complete runtime subsystem:

- reputation;
- automatic rank derivation;
- machine-verifiable Quest proof;
- witnesses;
- arbitration;
- distributed economic consensus.

The documentation intentionally distinguishes working mechanisms from the
long-term economic model.

---

## Principle

Economy should remain a state and settlement layer.

Quest logic defines what is being done.

Security defines whether the operation is authorized.

P2P defines how the request travels.

Economy owns balances and escrow.

Continuity records relevant economic transitions without replacing Economy
as the source of truth.
