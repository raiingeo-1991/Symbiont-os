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


class TestSCA1FullRollback(unittest.TestCase):

    def test_full_valid_rollback_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            path = root / "continuity" / "ledger.jsonl"

            ledger = ContinuityLedger(path)

            recovery = ContinuityRecovery(
                root / "continuity" / "state.json",
                ledger,
            )

            states = []
            previous = ContinuityState()

            # Создаём нормальную историю 1 -> 2 -> 3.
            for version in range(1, 4):
                state = previous.next(memory_version=version)
                states.append(state)

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

            current = states[2]
            target = states[1]

            print("state before rollback:", current.state_version)
            print("rollback target:", target.state_version)

            # Настоящий легитимный rollback.
            restored = recovery.rollback(
                current=current,
                target=target,
                reason="test legitimate rollback",
            )

            print("state after rollback:", restored.state_version)
            print("ledger events after rollback:", len(ledger.events()))

            # Важно: Ledger НЕ обрезался.
            self.assertEqual(len(ledger.events()), 4)

            # Rollback создал новую запись, поэтому sequence вырос.
            self.assertEqual(
                ledger.latest().event_sequence,
                4,
            )

            self.assertEqual(
                ledger.latest().event_type,
                "STATE_ROLLBACK",
            )

            # Состояние после rollback должно быть новым состоянием,
            # но с данными целевого состояния.
            self.assertEqual(
                restored.state_version,
                current.state_version + 1,
            )

            self.assertEqual(
                restored.memory_version,
                target.memory_version,
            )

            # Проверяем restart.
            shadow = ContinuityShadow(
                root,
                FakeIdentity(),
            )

            print(
                "state after restart:",
                shadow.state.state_version,
            )
            print(
                "ledger events after restart:",
                len(shadow.ledger.events()),
            )
            print(
                "ledger valid:",
                shadow.ledger.tamper_check(),
            )

            self.assertEqual(
                shadow.state.state_version,
                restored.state_version,
            )

            self.assertEqual(
                len(shadow.ledger.events()),
                4,
            )

            self.assertTrue(
                shadow.ledger.tamper_check()
            )


if __name__ == "__main__":
    unittest.main()
