# SCA-1 Local Witness Integration (Stage 11)

## Purpose

Stage 11 connects the existing SIS-006 `PersistentWitness` state machine to the
SCA-1 `ContinuityLedger`. When enabled, each SCA-1 ledger append uses the
witness's two-phase `prepare -> durable ledger write -> commit` sequence.

The witness and the SCA-1 ledger must agree on the exact `(sequence, last_hash)`
head. Startup fails closed on a mismatch. A pending transition is recovered
only when the verified ledger proves whether the append reached durable storage:

- If the ledger head equals the pending candidate, the witness commit is
  completed.
- If the ledger head still equals the pending expected head, the pending
  operation is aborted.
- Any other state is rejected.

## Explicit provisioning

The witness database is never created automatically by normal Core startup.
Provision it once, deliberately, before enabling the feature:

```python
from core.sss.sis_witness import PersistentWitness

witness = PersistentWitness.initialize("symbiont_data/sca1_witness.sqlite3")
witness.close()
```

`initialize()` refuses to overwrite an existing path. Preserve this database
when moving the device or restoring only part of the SCA-1 state.

Enable the integration with:

```bash
export SYMBIONT_SCA1_WITNESS=1
```

This flag also enables SCA-1 Shadow mode. If the witness database is missing,
corrupt, or disagrees with the ledger, Shadow initialization fails closed and
Core reports the error; it does not silently create a new trusted zero-state.

## Security boundary and limitations

This is a **local persistent witness**, not an independent remote witness.
It detects rollback or replacement of the `continuity/` directory while
`sca1_witness.sqlite3` remains intact. It does not protect against an attacker
who can restore or replace the entire Core data directory, including both the
ledger and witness database, or compromise the device and its files.

SIS-007 `QuorumVerifier` remains an experimental HMAC attestation verifier.
It is not a network protocol, distributed consensus system, or remote witness
service. No remote node is contacted by this stage.

Therefore Stage 11 provides defense in depth against partial local rollback;
it does **not** establish device-independent continuity. That requires a
separately provisioned remote witness with independently protected identity
keys, authenticated transport, replay protection, monotonic state, and an
explicit recovery/revocation policy.
