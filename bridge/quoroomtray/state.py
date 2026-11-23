from dataclasses import dataclass
from enum import Enum

from .actions import ActionKind, ActionResult, ActionStatus
from .observation import Observation


class Colour(Enum):
    GREY = "grey"
    YELLOW = "yellow"
    GREEN = "green"
    RED = "red"


class RedReason(Enum):
    ONLY_STACK_ANSWERS = "only_stack_answers"
    ONLY_BROKER_ANSWERS = "only_broker_answers"
    ACTION_FAILED = "action_failed"


@dataclass(frozen=True)
class StandState:
    colour: Colour
    reason: RedReason | None = None
    running: ActionKind | None = None
    failure: ActionResult | None = None


def probed_state(observation: Observation) -> StandState:
    if observation.stack_answers and observation.broker_answers:
        return StandState(Colour.GREEN)
    if not observation.stack_answers and not observation.broker_answers:
        return StandState(Colour.GREY)
    if observation.stack_answers:
        return StandState(Colour.RED, RedReason.ONLY_STACK_ANSWERS)
    return StandState(Colour.RED, RedReason.ONLY_BROKER_ANSWERS)


AIMED_AT = {ActionKind.START: Colour.GREEN, ActionKind.STOP: Colour.GREY}


def stand_state(observation: Observation, actions: ActionStatus) -> StandState:
    if actions.running is not None:
        return StandState(Colour.YELLOW, running=actions.running)
    probed = probed_state(observation)
    failed = actions.last_result
    if failed is None or failed.succeeded or probed.colour is AIMED_AT[failed.kind]:
        return probed
    return StandState(Colour.RED, RedReason.ACTION_FAILED, failure=failed)
