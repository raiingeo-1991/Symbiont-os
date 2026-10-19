from datetime import datetime, timezone

from symbiont_core import NightWorker


class FakeMemory:
    def __init__(self):
        self.saved_report = None
        self.saved_open_loops = []

    def night_report_for_date(self, date):
        return None

    def memories_today(self):
        return [
            type("Memory", (), {
                "text": "Сегодня работал над Symbiont.",
                "kind": "general",
            })()
        ]

    def principles(self, limit):
        return []

    def open_loops(self, limit):
        return []

    def save_night_report(self, date, text):
        self.saved_report = (date, text)

    def remember(self, text, kind="general", importance=5,
                 source="core", tags=None):
        self.saved_open_loops.append({
            "text": text,
            "kind": kind,
            "importance": importance,
            "source": source,
            "tags": tags,
        })


class FakeMind:
    llm = None

    def notice_words(self, limit=30, min_count=2):
        return []

    def notice_emotions(self, limit=30):
        return []


class FakeJournal:
    def append(self, *args, **kwargs):
        pass


def test_night_worker_creates_daily_report():
    memory = FakeMemory()
    worker = NightWorker(
        memory=memory,
        mind=FakeMind(),
        journal=FakeJournal(),
    )

    result = worker.run()

    assert result
    assert "Разбор дня" in result
    assert "Сегодня работал над Symbiont." in result
    assert memory.saved_report is not None
    assert memory.saved_report[1] == result


def test_night_worker_reuses_existing_daily_report():
    class ExistingReportMemory(FakeMemory):
        def night_report_for_date(self, date):
            return {"text": "УЖЕ СОХРАНЁННЫЙ ОТЧЁТ"}

        def save_night_report(self, date, text):
            raise AssertionError("NightWorker должен переиспользовать существующий отчёт")

    memory = ExistingReportMemory()

    worker = NightWorker(
        memory=memory,
        mind=FakeMind(),
        journal=FakeJournal(),
    )

    result = worker.run()

    assert result == "УЖЕ СОХРАНЁННЫЙ ОТЧЁТ"
    assert memory.saved_report is None


def test_night_worker_turns_goal_into_open_loop():
    class GoalMemory(FakeMemory):
        def memories_today(self):
            return [
                type("Memory", (), {
                    "text": "Нужно завтра продолжить проверку NightWorker.",
                    "kind": "general",
                })()
            ]

    memory = GoalMemory()

    worker = NightWorker(
        memory=memory,
        mind=FakeMind(),
        journal=FakeJournal(),
    )

    result = worker.run()

    assert result
    assert len(memory.saved_open_loops) == 1

    loop = memory.saved_open_loops[0]
    assert loop["text"] == "Нужно завтра продолжить проверку NightWorker."
    assert loop["kind"] == "open_loop"
    assert loop["importance"] == 7
    assert loop["source"] == "night_worker"
    assert "night" in loop["tags"]
    assert "open_loop" in loop["tags"]


def test_night_worker_empty_day_returns_nothing_to_report():
    class EmptyMemory(FakeMemory):
        def memories_today(self):
            return []

    memory = EmptyMemory()

    worker = NightWorker(
        memory=memory,
        mind=FakeMind(),
        journal=FakeJournal(),
    )

    result = worker.run()

    assert result == "Сегодня я ничего не запомнил."
    assert memory.saved_report is None


def test_night_worker_without_llm_still_saves_report():
    memory = FakeMemory()

    worker = NightWorker(
        memory=memory,
        mind=FakeMind(),
        journal=FakeJournal(),
    )

    result = worker.run()

    assert result
    assert memory.saved_report is not None
    assert memory.saved_report[1] == result


def test_night_worker_uses_memory_v2_in_candidate_mode():
    class FakeReflectionResult:
        candidates = [
            type(
                "Candidate",
                (),
                {
                    "content": "Похоже, сегодня основной фокус был на Symbiont.",
                    "confidence": 0.91,
                    "metadata": {"method": "test_reflection"},
                },
            )()
        ]


    class FakeConsolidationResult:
        accepted = [
            type(
                "Accepted",
                (),
                {
                    "content": "Фокус на Symbiont",
                },
            )()
        ]


    class FakeMemoryV2:
        enabled = True

        def __init__(self):
            self.reflect_calls = []
            self.consolidate_calls = []

        def reflect(self, experiences):
            self.reflect_calls.append(experiences)
            return FakeReflectionResult()

        def consolidate(self, reflection_result):
            self.consolidate_calls.append(reflection_result)
            return FakeConsolidationResult()


    memory = FakeMemory()
    memory_v2 = FakeMemoryV2()

    worker = NightWorker(
        memory=memory,
        mind=FakeMind(),
        journal=FakeJournal(),
        memory_v2=memory_v2,
    )

    result = worker.run()

    assert len(memory_v2.reflect_calls) == 1
    assert memory_v2.reflect_calls[0] == [
        "Сегодня работал над Symbiont."
    ]

    assert len(memory_v2.consolidate_calls) == 1
    assert memory_v2.consolidate_calls[0].candidates

    assert "Reflection V2 — кандидаты понимания:" in result
    assert "Похоже, сегодня основной фокус был на Symbiont." in result
    assert "Knowledge V2 — принято кандидатов: 1" in result


def test_night_worker_does_not_call_memory_v2_when_disabled():
    class DisabledMemoryV2:
        enabled = False

        def reflect(self, experiences):
            raise AssertionError("Reflection V2 не должен вызываться при enabled=False")

        def consolidate(self, reflection_result):
            raise AssertionError("Consolidation V2 не должен вызываться при enabled=False")


    memory = FakeMemory()
    memory_v2 = DisabledMemoryV2()

    worker = NightWorker(
        memory=memory,
        mind=FakeMind(),
        journal=FakeJournal(),
        memory_v2=memory_v2,
    )

    result = worker.run()

    assert result
    assert "Reflection V2" not in result
    assert "Knowledge V2" not in result
    assert memory.saved_report is not None


def test_night_worker_second_run_reuses_report_without_rebuilding():
    memory = FakeMemory()

    worker = NightWorker(
        memory=memory,
        mind=FakeMind(),
        journal=FakeJournal(),
    )

    first = worker.run()
    first_saved = memory.saved_report

    class ReusedReportMemory(FakeMemory):
        def __init__(self, saved_report):
            super().__init__()
            self.saved_report = saved_report

        def night_report_for_date(self, date):
            return {
                "text": self.saved_report[1],
            }

        def save_night_report(self, date, text):
            raise AssertionError(
                "Второй запуск не должен пересохранять ночной отчёт"
            )

        def remember(self, *args, **kwargs):
            raise AssertionError(
                "Второй запуск не должен создавать повторный open_loop"
            )

    memory2 = ReusedReportMemory(first_saved)

    worker2 = NightWorker(
        memory=memory2,
        mind=FakeMind(),
        journal=FakeJournal(),
    )

    second = worker2.run()

    assert second == first


def test_night_worker_builds_memory_v2_experiences_from_text_memories():
    class MixedMemory(FakeMemory):
        def memories_today(self):
            return [
                type("Memory", (), {
                    "text": "Работал над Symbiont ночью.",
                    "kind": "dialog",
                })(),
                type("Memory", (), {
                    "text": "Завершил тест NightWorker.",
                    "kind": "experience",
                })(),
                type("Memory", (), {
                    "text": "",
                    "kind": "general",
                })(),
                type("Memory", (), {
                    "text": None,
                    "kind": "general",
                })(),
            ]


    class FakeMemoryV2:
        enabled = True

        def __init__(self):
            self.experiences = None

        def reflect(self, experiences):
            self.experiences = experiences

            class ReflectionResult:
                candidates = []

            return ReflectionResult()

        def consolidate(self, reflection_result):
            class ConsolidationResult:
                accepted = []

            return ConsolidationResult()


    memory = MixedMemory()
    memory_v2 = FakeMemoryV2()

    worker = NightWorker(
        memory=memory,
        mind=FakeMind(),
        journal=FakeJournal(),
        memory_v2=memory_v2,
    )

    worker.run()

    assert memory_v2.experiences == [
        "Работал над Symbiont ночью.",
        "Завершил тест NightWorker.",
    ]
