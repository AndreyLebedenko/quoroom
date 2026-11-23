from dataclasses import dataclass


@dataclass(frozen=True)
class SessionLine:
    agent: str
    state: str
    line: str


@dataclass(frozen=True)
class Observation:
    stack_answers: bool
    sessions: tuple[SessionLine, ...] | None

    @property
    def broker_answers(self) -> bool:
        return self.sessions is not None
