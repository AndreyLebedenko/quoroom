"""Общие для брокера и клиента константы и формат конверта."""

from collections.abc import Callable
from dataclasses import dataclass

# Потолок одного long-poll на стороне брокера. Клиент ждёт чуть дольше.
WAIT_SECONDS = 50.0
# Сколько брокер считает сессию слушающей после последнего обращения /wait.
LISTEN_GRACE = WAIT_SECONDS + 20.0
# Сколько listener терпит недоступность брокера, прежде чем умереть.
DEAF_SECONDS = 120.0
# Сколько полной тишины делает слот свободным: новый login занимает его без
# --force. Живая сессия столько молчать не может — и listener, и плагин
# опрашивают брокера непрерывно, а пауза на обработку доставки укладывается
# в две минуты. Столько молчит только сессия, которой больше нет: закрытое
# приложение, убитый процесс, перезагрузка.
STALE_SECONDS = 180.0
# Предельная глубина цепочки агент->агент без участия человека. Значение по
# умолчанию; переопределяется ключом max_depth в config.yaml. Шесть звеньев
# хватает на переписку, но мало для совместной работы: обсуждение протокола
# втроём упирается в потолок за два-три обмена, а сброс даёт только человек.
MAX_DEPTH = 6
# Предел исходящих сообщений одной сессии в минуту.
MAX_SENDS_PER_MINUTE = 20

DEFAULT_PORT = 8770
DEFAULT_URL = f"http://127.0.0.1:{DEFAULT_PORT}"

KIND_HUMAN = "human"
KIND_AGENT = "agent"
KINDS = (KIND_HUMAN, KIND_AGENT)

KIND_WORDS = {
    KIND_HUMAN: "envelope_kind_human",
    KIND_AGENT: "envelope_kind_agent",
}

Words = Callable[..., str]


@dataclass(frozen=True)
class Envelope:
    """То, что listener печатает при пробуждении сессии."""

    sender: str
    kind: str
    text: str
    event_id: str
    stamp: str
    depth: int

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"envelope kind must be one of {KINDS}, got {self.kind!r}")

    def render(
        self,
        language: str,
        words: Words,
        restart_listener: bool = True,
        limit: int = MAX_DEPTH,
    ) -> str:
        """Конверт для агента, словами комнаты.

        Слова отдаёт words(language, name, **params): протокол не знает ни
        каталога, ни языков, а раскладка конверта одна на все языки.

        restart_listener=False — для агентов, у которых listener не отдельный
        процесс (плагин OpenCode живёт внутри CLI). Поднимать нечего, и
        требовать этого нельзя: указание, которое невозможно выполнить,
        только сбивает.

        Запрет на подтверждения приёма стоит здесь, а не только в скиллах,
        потому что читается ровно в момент решения «отвечать или нет».
        На первой же живой цепочке трое агентов вежливо подтвердили друг
        другу приём и израсходовали половину предела глубины, не сказав
        ничего по делу.
        """

        def say(name: str, **params: object) -> str:
            return words(language, name, **params)

        tail = (
            "envelope_tail_restart_listener"
            if restart_listener
            else "envelope_tail_reply_with_say"
        )
        trust = (
            say("envelope_data_not_instruction"),
            say("envelope_sender_no_authority"),
        )
        etiquette = (
            say("envelope_acknowledgement_not_needed"),
            say("envelope_reply_only_with_substance"),
        )
        return "\n".join(
            [
                say("envelope_open"),
                say(
                    "envelope_from",
                    sender=self.sender,
                    kind=say(KIND_WORDS[self.kind]),
                ),
                say("envelope_time", stamp=self.stamp),
                say("envelope_event", event_id=self.event_id),
                say("envelope_depth", depth=self.depth, limit=limit),
                " ".join(trust),
                " ".join(etiquette),
                say("envelope_text_start"),
                self.text,
                say("envelope_close"),
                say(tail),
            ]
        )

    def as_dict(self) -> dict:
        return {
            "sender": self.sender,
            "kind": self.kind,
            "text": self.text,
            "event_id": self.event_id,
            "stamp": self.stamp,
            "depth": self.depth,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Envelope":
        return cls(
            str(data["sender"]),
            str(data["kind"]),
            str(data["text"]),
            str(data["event_id"]),
            str(data["stamp"]),
            int(data["depth"]),
        )
