# Design sketch: task local-installers-02, shared setup core

For review before implementation. Nothing below is written yet.

## Package

`bridge/sessionchat/installer/`, run as `python -m sessionchat.installer` with
`bridge/` on `sys.path`. Standard library only.

## Modules and what each one owns

| Module | Responsibility |
| --- | --- |
| `__main__.py` | assemble the real boundaries, call `main`, exit with its code |
| `options.py` | parse argv, resolve the role list, usage errors, role option hook |
| `boundaries.py` | the only place that touches the outside world: roots, env, streams, subprocess, probe, platform |
| `steps.py` | `Step`, `HumanStep`, `Run`, `execute`, `Outcome`, `Failure` |
| `roles.py` | `Role`, the registry, install/removal order, the extension point |
| `ownership.py` | `Ownership`: what a role created, JSON at a path the role injects |
| `secrets.py` | `Secrets`: register a value, scrub any text |
| `confirmation.py` | `Confirmation`: list targets, require a typed word |

## Types

```python
class State(Enum):
    DONE = "готово"
    TODO = "не сделано"

class Step(Protocol):
    name: str
    def check(self, run: Run) -> State: ...
    def apply(self, run: Run) -> None: ...

class HumanStep:
    name: str
    instruction: str          # Russian, platform-specific, printed verbatim
    def check(self, run: Run) -> State: ...
    def apply(self, run: Run) -> None: ...   # never called; raises

@dataclass(frozen=True)
class Plan:
    roles: tuple[str, ...]    # resolved and ordered by phase
    remove: bool
    purge: bool
    answers: dict[str, str]   # role-specific values, keys from Role.add_options

@dataclass(frozen=True)
class Boundaries:
    repo: Path                # resolved from the entry point, not the cwd
    home: Path                # tests point it at a temporary directory
    env: Mapping[str, str]
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO
    run: Callable[[Sequence[str]], CompletedProcess]   # subprocess
    probe: Callable[[str], bool]                        # answers at this URL
    platform: str             # "windows" | "linux"

class Run:
    boundaries: Boundaries
    plan: Plan
    ownership: Ownership
    secrets: Secrets
    confirm: Confirmation
    completed: list[str]      # steps this run changed
    def say(self, text: str) -> None: ...   # stdout, scrubbed
    def warn(self, text: str) -> None: ...  # stderr, scrubbed

class Outcome(Enum):
    DONE = "выполнено"
    HUMAN = "нужен человек"
    FAILED = "сбой"
    CANCELLED = "отменено"

@dataclass(frozen=True)
class Failure:
    step: str
    completed: list[str]
    def render(self) -> str: ...   # failed step, changes made, how to resume

def execute(steps: Sequence[Step], run: Run) -> Outcome: ...
```

`execute` is the whole step model: `check` each step, `apply` only `TODO` ones,
`check` again, and stop at the first step whose second check is still `TODO`
(that is a failure), or whose check is `TODO` and is a `HumanStep` (that is
`HUMAN`). No progress file: state comes from the checks, so an interrupted run
is validated on the next run.

```python
@dataclass
class Ownership:
    path: Path
    entries: list[Entry]      # Entry(kind: str, path: str)
    @classmethod
    def load(cls, path: Path) -> "Ownership": ...
    def record(self, kind: str, path: Path) -> None: ...
    def of_kind(self, kind: str) -> list[Path]: ...
    def owns(self, path: Path) -> bool: ...
    def save(self) -> None: ...

class Secrets:
    def register(self, value: str) -> str: ...   # returns a placeholder
    def scrub(self, text: str) -> str: ...

class Confirmation:
    def ask(self, consequence: str, resources: Sequence[Path]) -> bool: ...
```

Gate item 4 is enforced by `of_kind` being the only source of paths to delete:
a step may delete only what `owns` says, and an existing resource without an
entry is reported as a conflict and kept. `record` is called by a step that has
just created the resource, so a pre-existing one is never adopted.

`Confirmation.ask` prints every exact resource and the data-loss consequence,
then reads one line and compares it to the word it printed. No flag bypasses it.
With a non-interactive stdin it returns False, the run reports the list and ends
`CANCELLED` - so a non-interactive run cannot purge. That follows from "no flag
skips confirmation"; say so if you want another way out.

## Roles, the extension point

```python
@dataclass(frozen=True)
class Role:
    name: str
    install: tuple[Step, ...]
    remove: tuple[Step, ...]
    purge: tuple[Step, ...]
    def add_options(self, parser: ArgumentParser) -> None: ...

REGISTRY: dict[str, Role] = {}          # empty in this task
INSTALL_ORDER = ("server", "participant")
REMOVE_ORDER = ("participant", "server")
```

`options.parse` builds the parser from `REGISTRY`: each role contributes its own
flags, and nothing central lists them. `Plan.roles` comes out already ordered
by phase, which is where the `--role both` rule lives. Steps get `run` in
`check`/`apply`, so a role is module-level data and roles register without
touching `__main__.py` or `options.py`.

## Injecting the system boundaries

`Boundaries` is the only constructor argument the core takes; `__main__.py`
builds it from `Boundaries.real()`, tests build it with a temporary `home` and
`repo`, `io.StringIO` streams, a `dict` env, a fake `run`/`probe` and an explicit
`platform`. Consequences: no module-level state, no `os.environ`, `subprocess`,
`socket` or `input()` anywhere outside `boundaries.py`, and no real home
directory, trust store, hosts file or Docker call in tests.

File IO itself is not abstracted: roots are injected, so tests write into a
temporary directory and use the real `pathlib`.

## Exit codes

Proposed: 0 done, 1 failed, 2 usage error, 3 a human step is pending, 4
cancelled. `install.ps1` and `install.sh` only propagate the code.

## Open questions

1. Distinct exit codes as above, or one nonzero for everything but usage?
2. Confirmation word: a fixed word per action (`PURGE`), or the human retyping
   the resource list? Fixed word is simpler and is what the card describes.
3. `Ownership` format: JSON, like `kit.json`, with `kind` + `path` entries, and
   one record per role at `<role-chosen-path>`. Roles 05-07 choose their path.