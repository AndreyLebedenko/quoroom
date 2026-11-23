from collections.abc import Callable

from quoroomtray.entries import TrayEntry, TraySnapshot


class FlagEvent:
    def __init__(self):
        self.flag = False
        self.waits: list[tuple[float | None, bool]] = []
        self.on_wait: Callable[[], None] | None = None
        self.on_clear: Callable[[], None] | None = None

    def set(self) -> None:
        self.flag = True

    def clear(self) -> None:
        self.flag = False
        if self.on_clear is not None:
            self.on_clear()

    def wait(self, timeout: float | None = None) -> bool:
        self.waits.append((timeout, self.flag))
        if self.on_wait is not None:
            self.on_wait()
        return self.flag


class FakeView:
    def __init__(self, while_running: Callable[["FakeView"], None] | None = None):
        self.while_running = while_running
        self.first: TraySnapshot | None = None
        self.shown: list[TraySnapshot] = []
        self.notifications: list[str] = []
        self.stopped = False
        self.show_failure: Exception | None = None

    def run(self, first: TraySnapshot, on_ready: Callable[[], None]) -> None:
        self.first = first
        on_ready()
        if self.while_running is not None:
            self.while_running(self)

    def show(self, snapshot: TraySnapshot) -> None:
        if self.show_failure is not None:
            failure, self.show_failure = self.show_failure, None
            raise failure
        self.shown.append(snapshot)

    def notify(self, text: str) -> None:
        self.notifications.append(text)

    def stop(self) -> None:
        self.stopped = True


class FakeClaim:
    def __init__(self):
        self.closed = False

    def close(self) -> None:
        self.closed = True


def default_entry(snapshot: TraySnapshot) -> TrayEntry:
    return next(entry for entry in snapshot.entries if entry.default)


def visible_entries(snapshot: TraySnapshot) -> list[TrayEntry]:
    return [entry for entry in snapshot.entries if entry.visible]


def entry_with_text(snapshot: TraySnapshot, text: str) -> TrayEntry:
    return next(entry for entry in snapshot.entries if entry.text == text)
