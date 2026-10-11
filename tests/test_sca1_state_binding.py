import tempfile
import unittest
from pathlib import Path

from core.continuity.state import ContinuityState
from core.continuity.ledger import ContinuityLedger
from core.continuity.recovery import ContinuityRecovery
from core.continuity.shadow import ContinuityShadow
from core.continuity.ledger import ContinuityVerificationError


class FakeIdentity:
    def id(self):
        return "TEST-SYMBIONT"

    def public_key(self):
        return "TEST-PUBLIC-KEY"


class TestSCA1StateBinding(unittest.TestCase):

    def test_startup_rejects_state_diverging_from_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            ledger = ContinuityLedger(
                root / "continuity" / "ledger.jsonl"
            )

            recovery = ContinuityRecovery(
                root / "continuity" / "state.json",
                ledger,
            )

            # Каноническое состояние
            state = ContinuityState().next(memory_version=1)

            ledger.append(
                "MEMORY_CREATED",
                state.state_version,
                {"test": "binding"},
                state_hash=state.content_hash(),
            )

            recovery.save(state)

            # Проверяем нормальный запуск
            shadow = ContinuityShadow(root, FakeIdentity())

            self.assertEqual(
                shadow.state.content_hash(),
                ledger.latest().state_hash,
            )

            # Подменяем materialized state
            forged = state.next(memory_version=999)
            recovery.save(forged)

            # Проверяем, что файлы действительно существуют
            self.assertTrue(
                (root / "continuity" / "state.json").exists()
            )
            self.assertTrue(
                (root / "continuity" / "ledger.jsonl").exists()
            )

            # Новый процесс / restart.
            # Расходящийся state.json должен быть отвергнут.
            with self.assertRaises(ContinuityVerificationError):
                ContinuityShadow(root, FakeIdentity())


if __name__ == "__main__":
    unittest.main()
