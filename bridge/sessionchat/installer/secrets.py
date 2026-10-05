import urllib.parse

from .catalogue import text


class Secrets:
    def __init__(self, lang: str) -> None:
        self.lang = lang
        self.values: list[str] = []

    def register(self, value: str) -> str:
        if value and value not in self.values:
            self.values.append(value)
            for form in (repr(value)[1:-1], urllib.parse.quote(value, safe="")):
                if form and form not in self.values:
                    self.values.append(form)
        return value

    def scrub(self, line: str) -> str:
        placeholder = text(self.lang, "secrets.hidden")
        for value in sorted(self.values, key=len, reverse=True):
            line = line.replace(value, placeholder)
        return line
