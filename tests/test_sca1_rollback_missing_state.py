import tempfile
import unittest
from pathlib import Path

from core.continuity.state import ContinuityState
from core.continuity.ledger import ContinuityLedger
from core.continuity.recovery import ContinuityRecovery
from core.continuity.shadow import ContinuityShadow


class FakeIdentity:
    def id(self):
        return "TEST-SYMBIONT"

    def public_key(self):
        return "TEST-PUBLIC-KEY"


class TestSCA1RollbackMissingState(unittest.TestCase):

    def test_rollback_survives_missing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            ledger = ContinuityLedger(
                root / "continuity" / "ledger.jsonl"
            )

            recovery = ContinuityRecovery(
                root / "continuity" / "state.json",
                ledger,
            )

            previous = ContinuityState()

            for version in range(1, 4):
                state = previous.next(memory_version=version)

                ledger.append(
                    "MEMORY_CREATED",
                    state.state_version,
                    {
                        "version": version,
                        "state_snapshot": state.as_dict(),
                    },
                    state_hash=state.content_hash(),
                )

                recovery.save(state)
                previous = state

            current = previous

            target = ContinuityState(
                state_version=2,
                memory_version=2,
                knowledge_version=0,
                economy_version=0,
                quest_version=0,
                p2p_version=0,
                active_body=None,
                previous_state_hash=None,
                created_at=current.created_at,
            )

            restored = recovery.rollback(
                current=current,
                target=target,
                reason="rollback missing-state test",
            )

            self.assertEqual(restored.state_version, 4)
            self.assertEqual(restored.memory_version, 2)

            state_file = root / "continuity" / "state.json"
            self.assertTrue(state_file.exists())

            # Удаляем materialized state.
            state_file.unlink()

            # Restart должен восстановить состояние
            # непосредственно из последнего Ledger snapshot.
            shadow = ContinuityShadow(root, FakeIdentity())

            print(
                "recovered state version:",
                shadow.state.state_version,
            )
            print(
                "recovered memory version:",
                shadow.state.memory_version,
            )
            print(
                "ledger state version:",
                shadow.ledger.latest().state_version,
            )
            print(
                "state file restored:",
                state_file.exists(),
            )

            self.assertEqual(
                shadow.state.state_version,
                restored.state_version,
            )

            self.assertEqual(
                shadow.state.memory_version,
                restored.memory_version,
            )

            self.assertEqual(
                shadow.state.content_hash(),
                restored.content_hash(),
            )

            self.assertTrue(state_file.exists())

            self.assertTrue(
                shadow.ledger.tamper_check()
            )


if __name__ == "__main__":
    unittest.main()
