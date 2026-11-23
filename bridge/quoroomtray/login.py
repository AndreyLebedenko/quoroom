from . import settings
from .observation import Observation


def is_half_state(observation: Observation) -> bool:
    return observation.stack_answers and not observation.broker_answers


def is_grey(observation: Observation) -> bool:
    return not observation.stack_answers and not observation.broker_answers


class LoginRule:
    def __init__(
        self,
        started_at: float,
        window: float = settings.LOGIN_RULE_WINDOW_SECONDS,
        confirming_polls: int = settings.LOGIN_RULE_CONFIRMING_POLLS,
    ):
        self._started_at = started_at
        self._window = window
        self._confirming_polls = confirming_polls
        self._armed = True
        self._half_states_in_a_row = 0

    @property
    def armed(self) -> bool:
        return self._armed

    def should_start(
        self, observation: Observation, now: float, action_seen: bool
    ) -> bool:
        if not self._armed:
            return False
        if action_seen or now - self._started_at >= self._window:
            self._armed = False
            return False
        if is_half_state(observation):
            self._half_states_in_a_row += 1
            if self._half_states_in_a_row >= self._confirming_polls:
                self._armed = False
                return True
            return False
        self._half_states_in_a_row = 0
        if not is_grey(observation):
            self._armed = False
        return False
