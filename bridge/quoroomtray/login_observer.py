from collections.abc import Callable

from .actions import ActionKind
from .guard import FailureReport, guarded
from .login import LoginRule
from .observation import Observation
from .runner import ScriptRunner


class LoginRuleObserver:
    def __init__(
        self,
        observe: Callable[[], Observation],
        rule: LoginRule,
        runner: ScriptRunner,
        clock: Callable[[], float],
        report: FailureReport,
    ):
        self._observe = observe
        self._rule = rule
        self._runner = runner
        self._clock = clock
        self._apply = guarded(self._apply_rule, report)

    def __call__(self) -> Observation:
        observation = self._observe()
        self._apply(observation)
        return observation

    def _apply_rule(self, observation: Observation) -> None:
        if not self._rule.armed:
            return
        status = self._runner.status()
        action_seen = status.running is not None or status.last_result is not None
        if self._rule.should_start(observation, self._clock(), action_seen):
            self._runner.begin(ActionKind.START)
