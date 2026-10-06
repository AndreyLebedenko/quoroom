# Report: task-local-installers-02-setup-core

**Branch:** `task/local-installers-02-setup-core` (from `feat/local-installers`)
**Base commit:** 12129d0
**Status:** third pass after review round 2, implemented and verified
automatically, not committed, no live check.

## Review round 2, item by item

1. **The default deleter crashed on every call.** `unlink` now takes
   `(run, id)` like every deleter. `test_the_default_deleter_removes_the_file`
   runs `OwnedStep` without a deleter over a real temporary file, and
   `test_the_default_deleter_tolerates_a_missing_file` covers the absent one.
2. **Purge no longer deletes what appeared after the question.** `Run.confirmed`
   holds the confirmed `PurgeTarget`s; under `--purge` `approved()` is the only
   path to a deletion, in both `OwnedStep` and `FoundStep`, and whatever is not
   in the set is reported as kept.
   `test_a_file_that_appeared_after_the_question_survives` creates a file in a
   remove step that runs after the question and asserts it survives, is
   reported, and that the already-confirmed token is gone.
3. **Ownership records are protected in the core.** `main` computes
   `frozenset(role.record_path(boundaries) for role in roles)` for every role it
   was given, selected or not, and keeps it on `Run.records`. `FoundStep.targets`
   drops those paths from its targets and `FoundStep.check` reports each as kept.
   `RecordProtectionTests` runs a participant purge whose search covers the
   records directory and asserts `server.json` and `participant.json` both
   survive, are not even asked about, and are named in the report.
4. **A purge step that does not declare its targets is refused.**
   `Role.__post_init__` raises `TypeError`; plain remove steps stay allowed.
5. **The four tests that passed with the bug restored.**
   - `MainOrderTests` gives the server a remove step, asserts both full logs, and
     adds `test_the_order_comes_from_the_plan_not_from_the_argument_order`, which
     passes the roles participant-first.
   - The percent-encoded test builds the expectation with
     `urllib.parse.quote("токен", safe="")` instead of a hand-typed literal.
   - The report test captures the `run` the report receives and asserts on its
     `completed`, instead of asserting on a different `Run`.
   - The default deleter tests above replace the lambda that hid the bug.
6. **`Role.report` cannot crash the run.** The reports run in their own guarded
   block: a failure prints the scrubbed report with the changes of the run and
   exits 1. Four tests, including one that registers a secret inside the report
   and asserts it stays out of stderr, and one that asserts no traceback.
7. **`RoleOptions`.** No `default` is injected any more, so a value option
   defaults to `None` and `store_true` to `False`
   (`test_a_flag_default_is_none_not_false`). A caller-supplied `dest` raises
   `TypeError`: it is a defect in role code, not a usage error.
   Identical flag strings in two roles still raise `argparse.ArgumentError`, which
   is a code defect too; tasks 05 and 06 add a parser test over
   `built_in_roles()` as agreed.
8. **The confirmation is not a change of the run.** `ConfirmPurge` is gone as a
   step: `main` asks directly, so the question never reaches `run.completed`. A
   refusal raises `Cancelled` and exits 4.

## Mutation checks

Every fix was verified by putting the bug back and watching a test fail.

| Bug put back | Tests that failed |
| --- | --- |
| `unlink(id)` | 2 in `test_installer_steps` |
| `approved()` returns everything | 2 across steps and ownership |
| records computed for selected roles only | 2 in `RecordProtectionTests` |
| `Role.__post_init__` removed | `test_a_purge_step_that_does_not_declare_its_targets_is_refused` |
| `role.report` unguarded | 5 in `RoleReportTests` |
| `TypeError` on `dest=` weakened to `ValueError` | 1 in `RoleOptionTests` |
| `selected` from the `roles` argument again | `test_the_order_comes_from_the_plan_not_from_the_argument_order` |
| `run.confirmed` never filled | 6 across steps and ownership |
| percent-encoded expectation hand-typed again | the secret test |

## Module map

| Module | Responsibility |
| --- | --- |
| `boundaries.py` | `Boundaries`, `Probe`, `answers`, `describe`, `run_command`, the repository root from `__file__` |
| `errors.py` | `UsageError`, `HelpRequested` |
| `secrets.py` | `Secrets.register` / `scrub` |
| `ownership.py` | `Entry(kind, id)`, `PurgeTarget(role, kind, id)`, `Ownership` |
| `confirmation.py` | `Confirmation.ask`, the word `PURGE` |
| `steps.py` | `State`, `Outcome`, `Step`, `Destructive`, `OwnedStep`, `FoundStep`, `HumanStep`, `Plan`, `Run`, `Failure`, `NeedsHuman`, `Cancelled`, `execute`, `approved`, `unapproved`, `unlink`, `report_kept` |
| `roles.py` | `RoleOptions`, `Role`, `built_in_roles`, `order`, `consequence_of` |
| `options.py` | `Parser`, `parser_for`, `parse`, the interactive role question |
| `main.py` | `main(argv, boundaries, roles)`, exit codes, the confirmation gate, the guarded report |
| `__main__.py` | the real boundaries and the real role set |

## Answers to the reviewer's questions

- **`_print_message` stays**, as decided.
- Q1, Q2, Q3, Q4 were answered in round 2 and are unchanged: no
  `SESSION_BRIDGE.md` section, `ARCHITECTURE.md` by task 08; English argparse
  messages accepted; `RoleOptions` enforces the dest by construction with answers
  nested per role; `Probe(status, error)` with `ProxyHandler({})` and roles
  deciding what counts as an answer.

## Findings for tasks 05-07

- **The purge authorization is a set, not a phase.** A resource discovered after
  the question is kept and reported, not deleted. Task 05 purges the token files
  it finds under `~/.agentschat/`, so the set must be computed at question time,
  which is what `main` does.
- **Ownership records are excluded from `FoundStep` searches by the core**, so a
  role may put its record next to what it discovers, but it will be reported as
  kept on every purge. That report line is expected, not a defect.
- **`Probe` deliberately answers nothing about the broker yet.** Task 05 decides
  what "reachable" means: a 404 from a wrong path is still an answer here.

## Coverage of the acceptance criteria

| Criterion | Where |
| --- | --- |
| every argument rule, including invalid combinations | `RoleSelectionTests`, `FlagCombinationTests`, `RoleOptionTests` |
| completed step is not applied again | `test_a_completed_step_is_not_applied`, `test_a_second_run_over_a_finished_installation_applies_nothing` |
| an interrupted run resumes from checks | `InterruptedRunTests.test_a_step_that_failed_is_the_only_one_the_next_run_applies` |
| a failed step yields the report and a nonzero exit | `FailureReportTests`, `test_a_step_that_stays_unfinished_fails_the_run`, exit 1 |
| a human step stops with its instruction | `HumanStepTests`, `test_an_ordinary_step_can_stop_the_run_for_a_human`, `test_a_run_that_needs_a_human_exits_three`, exit 3 |
| a registered secret is absent from stdout, stderr and exception text | `SecretTests` including the escaped and percent-encoded forms, and the broken-report test |
| confirmation cancel leaves state unchanged | `test_a_refused_purge_changes_nothing`, `test_an_empty_answer_cancels`, `test_a_cancelled_purge_leaves_the_record_byte_identical`, exit 4 |
| an unrecorded resource is reported, not deleted | `test_a_resource_without_a_record_is_never_a_target`, `RecordProtectionTests` |
| only the standard library | `test_importing_the_installer_pulls_in_only_the_standard_library`, `test_every_installer_import_is_relative_or_standard_library` |
| runs as a module from another directory | `test_the_installer_runs_as_a_module_with_bridge_on_the_path` |

## Verification, run from `bridge/` in order

- `.venv/Scripts/python.exe -m unittest discover -s tests -t .` - Ran 302 tests,
  OK. 119 of them are new in this task.
- `node --test tests/plugin/agentschat.test.mjs` - tests 4, pass 4, fail 0.
- `.venv/Scripts/ruff.exe check` - All checks passed.
- `.venv/Scripts/ruff.exe format --check` - 34 files already formatted.

`ruff` is not on PATH here, so it ran from the project virtualenv, version 0.16.6.

Manual smoke check, not a test: `python -S -m sessionchat.installer --role both`
prints the no-roles notice and exits 2; `--help` prints usage and exits 0 even in
a build without roles.

## Defects the round-2 tests found

- `_confirmed` accepted a refusal and fell through into the run, so a purge with
  no targets and a refused purge both ended 0. Found by
  `test_a_cancelled_purge_leaves_the_record_byte_identical` after the gate stopped
  being a step.
- `RoleOptions` rejected a caller `dest` as a user error, which would have sent a
  role-code defect out as exit 2.

## Not done, by design

- No role, no step of a role, no entry point script, no documentation change.
- No change to `client.py`, `kit.py`, the broker or `pyproject.toml`.
- No commit, per instruction. The task card status is untouched for the review.