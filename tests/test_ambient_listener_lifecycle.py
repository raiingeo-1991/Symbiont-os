import symbiont_core as core


class FakeJournal:
    def __init__(self):
        self.events = []

    def append(self, event, data):
        self.events.append((event, data))


class FakeMemory:
    def __init__(self):
        self.logged = []
        self.saved = []

    def log_ambient(self, text):
        self.logged.append(text)

    def remember(self, text, **kwargs):
        self.saved.append((text, kwargs))
        return "memory-test-id"


class FakeMind:
    def __init__(self):
        self.links = []

    def build_links(self, memory_id, text):
        self.links.append((memory_id, text))


def make_listener():
    journal = FakeJournal()
    memory = FakeMemory()
    mind = FakeMind()
    listener = core.AmbientListener(mind, memory, journal)
    return listener, mind, memory, journal


def test_start_is_idempotent_and_stop_joins_worker():
    listener, _, _, _ = make_listener()

    assert listener.start() is True
    first_thread = listener._thread

    assert listener.start() is False
    assert listener._thread is first_thread

    assert listener.stop() is True
    assert listener.is_active() is False
    assert not first_thread.is_alive()


def test_listener_can_restart_after_stop():
    listener, _, _, _ = make_listener()

    assert listener.start() is True
    first_thread = listener._thread
    assert listener.stop() is True

    assert listener.start() is True
    second_thread = listener._thread

    assert second_thread is not first_thread
    assert second_thread.is_alive()
    assert listener.stop() is True
    assert not second_thread.is_alive()


def test_stop_clears_pending_queue_and_rejects_new_input():
    listener, _, _, _ = make_listener()

    assert listener.start() is True
    assert listener.feed("надо проверить очередь") is True
    assert listener.stop() is True

    assert listener.queue == []
    assert listener.feed("новое сообщение") is False


def test_repeated_stop_is_safe():
    listener, _, _, _ = make_listener()

    assert listener.stop() is True
    assert listener.stop() is True
    assert listener.is_active() is False
