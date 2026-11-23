from sessionchat.i18n import Catalogue

TRAY_CATALOGUE = Catalogue("quoroomtray", "messages")


class TrayTexts:
    def __init__(self, language: str):
        self.language = language

    def text(self, key: str, **params: object) -> str:
        return TRAY_CATALOGUE.text(self.language, key, **params)
