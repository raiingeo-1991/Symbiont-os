import symbiont_core as core


class FakeStopper:
    def __init__(self, results=None):
        self.results = list(results or [True])
        self.calls = 0

    def stop(self):
        self.calls += 1
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


class FakeJournal:
    def __init__(self):
        self.events = []

    def append(self, event, data):
        self.events.append((event, data))


class FakeIdentity:
    def id(self):
        return "shutdown-test-id"


class FakeResource:
    def __init__(self, fail_first=False):
        self.calls = 0
        self.fail_first = fail_first

    def close(self):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("simulated close failure")


def make_core():
    obj = object.__new__(core.Symbiont)
    obj._shutdown_lock = core.threading.RLock()
    obj._shutdown_complete = False
    obj._shutdown_event_written = False
    obj._shutdown_closed_components = set()

    obj.listener = FakeStopper()
    obj.p2p = FakeStopper()
    obj.journal = FakeJournal()
    obj.identity = FakeIdentity()

    obj.sis_integrity = FakeResource()
    obj.immune_memory = FakeResource()
    obj.memory = FakeResource()
    return obj


def test_close_is_idempotent():
    obj = make_core()

    assert obj.close() is True
    assert obj.close() is True

    assert obj.listener.calls == 1
    assert obj.p2p.calls == 1
    assert len(obj.journal.events) == 1
    assert obj.memory.calls == 1
    assert obj.immune_memory.calls == 1
    assert obj.sis_integrity.calls == 1


def test_storage_is_not_closed_when_p2p_did_not_stop():
    obj = make_core()
    obj.p2p = FakeStopper([False, True])

    assert obj.close() is False
    assert obj.memory.calls == 0
    assert obj.immune_memory.calls == 0
    assert obj.sis_integrity.calls == 0

    assert obj.close() is True
    assert obj.memory.calls == 1
    assert obj._shutdown_complete is True
    assert len(obj.journal.events) == 1


def test_close_retries_only_failed_resource():
    obj = make_core()
    obj.immune_memory = FakeResource(fail_first=True)

    assert obj.close() is False
    assert obj.sis_integrity.calls == 1
    assert obj.immune_memory.calls == 1
    assert obj.memory.calls == 1

    assert obj.close() is True
    assert obj.sis_integrity.calls == 1
    assert obj.immune_memory.calls == 2
    assert obj.memory.calls == 1
    assert len(obj.journal.events) == 1


def test_shell_run_closes_core_when_banner_raises():
    class FakeSym:
        def __init__(self):
            self.closed = 0

        def close(self):
            self.closed += 1
            return True

    sym = FakeSym()
    shell = core.Shell(sym)

    def broken_banner():
        raise RuntimeError("simulated shell startup failure")

    shell.banner = broken_banner

    try:
        shell.run()
    except RuntimeError as exc:
        assert str(exc) == "simulated shell startup failure"
    else:
        raise AssertionError("Expected startup exception")

    assert sym.closed == 1
