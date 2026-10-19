from pathlib import Path

from symbiont_core import NightWorker, MemoryVault


class FakeMind:
    llm = None

    def notice_words(self, limit=30, min_count=2):
        return []

    def notice_emotions(self, limit=30):
        return []


class FakeJournal:
    def append(self, *args, **kwargs):
        pass


def test_night_worker_real_memoryvault_roundtrip(tmp_path):
    journal = FakeJournal()
    memory = MemoryVault(tmp_path / "memory.sqlite3", journal)

    memory.remember(
        "Нужно завтра продолжить проверку NightWorker.",
        kind="general",
        importance=7,
        source="test",
        tags=["test"],
    )

    worker = NightWorker(
        memory=memory,
        mind=FakeMind(),
        journal=FakeJournal(),
    )

    first = worker.run()

    assert first
    assert "Разбор дня" in first

    reports = memory.night_report_for_date(
        __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).date().isoformat()
    )

    assert reports
    assert reports["text"] == first

    loops = memory.open_loops(20)

    assert any(
        "Нужно завтра продолжить проверку NightWorker."
        in m.text
        for m in loops
    )

    second = NightWorker(
        memory=memory,
        mind=FakeMind(),
        journal=FakeJournal(),
    ).run()

    assert second == first


def test_night_worker_real_memoryvault_with_memory_v2_candidate_mode(tmp_path):
    journal = FakeJournal()
    memory = MemoryVault(tmp_path / "memory.sqlite3", journal)

    memory.remember(
        "Сегодня продолжил работу над Symbiont.",
        kind="general",
        importance=6,
        source="test",
        tags=["test"],
    )

    class FakeMemoryV2:
        enabled = True

        def __init__(self):
            self.experiences = None
            self.consolidated = False

        def reflect(self, experiences):
            self.experiences = experiences

            class Candidate:
                content = "Сегодня основной фокус — Symbiont."
                confidence = 0.9
                metadata = {"method": "test"}

            class Result:
                candidates = [Candidate()]

            return Result()

        def consolidate(self, reflection_result):
            self.consolidated = True

            class Result:
                accepted = []

            return Result()

    memory_v2 = FakeMemoryV2()

    worker = NightWorker(
        memory=memory,
        mind=FakeMind(),
        journal=journal,
        memory_v2=memory_v2,
    )

    result = worker.run()

    assert memory_v2.experiences == [
        "Сегодня продолжил работу над Symbiont."
    ]
    assert memory_v2.consolidated is True
    assert "Reflection V2 — кандидаты понимания:" in result
    assert "Сегодня основной фокус — Symbiont." in result

    today = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).date().isoformat()

    saved = memory.night_report_for_date(today)

    assert saved["text"] == result
