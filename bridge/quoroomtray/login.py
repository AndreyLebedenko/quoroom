from collections.abc import Callable

from .actions import ActionKind
from .observation import Observation
from .runner import ScriptRunner


def login_action(observation: Observation) -> ActionKind | None:
    if observation.stack_answers and not observation.broker_answers:
        return ActionKind.START
    return None


def apply_login_rule(
    observe: Callable[[], Observation], runner: ScriptRunner
) -> ActionKind | None:
    action = login_action(observe())
    if action is not None and runner.begin(action):
        return action
    return None
