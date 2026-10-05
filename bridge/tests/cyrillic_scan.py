"""Task english-release-17: find Cyrillic text in the tracked files of a tree."""

import ast
import io
import os
import re
import subprocess
import tokenize
from dataclasses import dataclass
from pathlib import Path

CYRILLIC = re.compile("[Ѐ-ԯ]")
CODE_SUFFIXES = (".py", ".js", ".mjs", ".cjs")
PYTHON_SUFFIX = ".py"
SNIPPET_WIDTH = 60


class GitUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Allowed:
    path: str
    reason: str

    def covers(self, tracked: str) -> bool:
        if self.path.endswith("/"):
            return tracked.startswith(self.path)
        return tracked == self.path


@dataclass(frozen=True)
class Policy:
    allowed: tuple[Allowed, ...]
    not_runtime: tuple[str, ...]

    def allows(self, tracked: str) -> bool:
        return any(entry.covers(tracked) for entry in self.allowed)

    def is_runtime_code(self, tracked: str) -> bool:
        return tracked.endswith(CODE_SUFFIXES) and not tracked.startswith(
            self.not_runtime
        )


def git_environment() -> dict[str, str]:
    return {
        name: value
        for name, value in os.environ.items()
        if name not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")
    }


def run_git(root: Path, *arguments: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            env=git_environment(),
            check=False,
        )
    except OSError as failure:
        raise GitUnavailable(f"git cannot be run: {failure}") from None
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", "replace").strip()
        raise GitUnavailable(f"git {' '.join(arguments)} failed: {detail}")
    return done.stdout.decode("utf-8")


def tracked_files(root: Path) -> list[str]:
    top = Path(run_git(root, "rev-parse", "--show-toplevel").strip())
    if top.resolve() != root.resolve():
        raise GitUnavailable(f"{root} is not the top of a git work tree")
    listed = [name for name in run_git(root, "ls-files", "-z").split("\0") if name]
    if not listed:
        raise GitUnavailable("git lists no tracked files")
    return sorted(listed)


def read_text(root: Path, tracked: str) -> str | None:
    path = root / tracked
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8-sig")


def snippet(text: str) -> str:
    return " ".join(text.split())[:SNIPPET_WIDTH]


class JavaScriptLexer:
    def __init__(self, source: str):
        self.source = source
        self.position = 0

    def current(self) -> str:
        return self.source[self.position : self.position + 1]

    def following(self) -> str:
        return self.source[self.position + 1 : self.position + 2]

    def take(self) -> str:
        taken = self.current()
        self.position += 1
        return taken

    def quoted(self) -> str:
        quote = self.take()
        text = quote
        while self.position < len(self.source) and self.current() != quote:
            if self.current() == "\\":
                text += self.take()
            text += self.take()
        return text + self.take()

    def regex(self) -> str:
        text = self.take()
        in_class = False
        while self.position < len(self.source) and (in_class or self.current() != "/"):
            if self.current() == "\\":
                text += self.take()
            elif self.current() == "[":
                in_class = True
            elif self.current() == "]":
                in_class = False
            text += self.take()
        return text + self.take()

    def template(self) -> str:
        text = self.take()
        while self.position < len(self.source) and self.current() != "`":
            if self.current() == "\\":
                text += self.take()
            elif self.current() == "$" and self.following() == "{":
                text += self.source[self.position : self.position + 2]
                self.position += 2
                text += self.code(inside_template=True) + "}"
                continue
            text += self.take()
        return text + self.take()

    def skip_line_comment(self) -> None:
        while self.position < len(self.source) and self.current() != "\n":
            self.position += 1

    def skip_block_comment(self) -> str:
        end = self.source.find("*/", self.position + 2)
        stop = len(self.source) if end < 0 else end + 2
        newlines = self.source[self.position : stop].count("\n")
        self.position = stop
        return "\n" * newlines

    def code(self, inside_template: bool = False) -> str:
        out = ""
        depth = 0
        previous = ";"
        while self.position < len(self.source):
            c = self.current()
            if c == "/" and self.following() == "/":
                self.skip_line_comment()
                continue
            if c == "/" and self.following() == "*":
                out += self.skip_block_comment()
                continue
            if inside_template and c == "}" and depth == 0:
                self.position += 1
                return out
            if c == "{":
                depth += 1
            if c == "}":
                depth -= 1
            if c in "\"'":
                out += self.quoted()
            elif c == "`":
                out += self.template()
            elif c == "/" and previous in "(,=:[!&|?{};":
                out += self.regex()
            else:
                out += self.take()
            if not c.isspace():
                previous = c
        return out


def javascript_without_comments(source: str) -> str:
    return JavaScriptLexer(source).code()


def javascript_findings(source: str) -> list[str]:
    return [
        f"line {number}: {snippet(line)}"
        for number, line in enumerate(
            javascript_without_comments(source).split("\n"), 1
        )
        if CYRILLIC.search(line)
    ]


def docstring_nodes(tree: ast.AST) -> set[int]:
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, owners) or not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            found.add(id(first.value))
    return found


def python_findings(source: str) -> list[str]:
    try:
        tree = ast.parse(source.lstrip("﻿"))
    except SyntaxError as failure:
        return [f"line {failure.lineno}: cannot be parsed ({failure.msg})"]
    docstrings = docstring_nodes(tree)
    found = [
        (node.lineno, f"string {snippet(node.value)}")
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and CYRILLIC.search(node.value)
    ]
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.NAME and CYRILLIC.search(token.string):
            found.append((token.start[0], f"identifier {token.string}"))
    return [f"line {number}: {what}" for number, what in sorted(found)]


def literal_problems(tracked: str, source: str) -> list[str]:
    found = (
        python_findings(source)
        if tracked.endswith(PYTHON_SUFFIX)
        else javascript_findings(source)
    )
    return [f"{tracked}: Cyrillic outside comments, {item}" for item in found]


def read_all(root: Path, files: list[str]) -> tuple[dict[str, str], list[str]]:
    texts: dict[str, str] = {}
    broken: list[str] = []
    for tracked in files:
        try:
            text = read_text(root, tracked)
        except UnicodeDecodeError:
            broken.append(f"{tracked}: not valid UTF-8")
            continue
        if text is not None:
            texts[tracked] = text
    return texts, broken


def unlisted_findings(root: Path, files: list[str], policy: Policy) -> list[str]:
    texts, broken = read_all(root, files)
    return broken + [
        f"{tracked}: Cyrillic in a file that is not allowlisted"
        for tracked, text in texts.items()
        if CYRILLIC.search(text) and not policy.allows(tracked)
    ]


def literal_findings(root: Path, files: list[str], policy: Policy) -> list[str]:
    texts, _ = read_all(root, files)
    return [
        problem
        for tracked, text in texts.items()
        if policy.is_runtime_code(tracked)
        for problem in literal_problems(tracked, text)
    ]


def findings(root: Path, files: list[str], policy: Policy) -> list[str]:
    return unlisted_findings(root, files, policy) + literal_findings(
        root, files, policy
    )


def allowlist_problems(root: Path, files: list[str], policy: Policy) -> list[str]:
    problems = []
    for entry in policy.allowed:
        if not entry.reason.strip():
            problems.append(f"{entry.path}: no reason")
        covered = [tracked for tracked in files if entry.covers(tracked)]
        if not covered:
            problems.append(f"{entry.path}: covers no tracked file")
        elif not entry.path.endswith("/") and not CYRILLIC.search(
            read_text(root, covered[0]) or ""
        ):
            problems.append(f"{entry.path}: holds no Cyrillic, drop the entry")
    return problems
