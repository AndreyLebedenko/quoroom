import urllib.parse

PLACEHOLDER = "<скрыто>"


class Secrets:
    def __init__(self) -> None:
        self.values: list[str] = []

    def register(self, value: str) -> str:
        if value and value not in self.values:
            self.values.append(value)
            for form in (repr(value)[1:-1], urllib.parse.quote(value, safe="")):
                if form and form not in self.values:
                    self.values.append(form)
        return value

    def scrub(self, text: str) -> str:
        for value in sorted(self.values, key=len, reverse=True):
            text = text.replace(value, PLACEHOLDER)
        return text
