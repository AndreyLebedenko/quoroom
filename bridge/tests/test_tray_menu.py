"""Task tray-02: the menu model, the wording of states and the left click."""

import unittest

from quoroomtray import settings
from quoroomtray.actions import ActionKind
from quoroomtray.click import OpenElement, ShowNotification, left_click
from quoroomtray.menu import MenuRole, build_menu, offered_action
from quoroomtray.observation import Observation, SessionLine
from quoroomtray.state import stand_state
from quoroomtray.texts import TrayTexts
from quoroomtray.wording import menu_item_text, status_text, tooltip_text
from tests.tray_fakes import (
    GREEN_PROBES,
    GREY_PROBES,
    NO_ACTION,
    ONLY_BROKER_PROBES,
    ONLY_STACK_PROBES,
    OTHER_SESSION,
    SESSION,
    finished,
    running,
)

ENGLISH = TrayTexts("en")
RUSSIAN = TrayTexts("ru")


def menu_for(observation, actions, texts=ENGLISH):
    return build_menu(stand_state(observation, actions), observation, texts)


def roles(menu):
    return [item.role for item in menu]


def toggle_of(menu):
    return next(item for item in menu if item.role is MenuRole.TOGGLE)


class MenuShapeTests(unittest.TestCase):
    def test_a_grey_menu_lists_status_start_log_and_exit_in_that_order(self):
        menu = menu_for(GREY_PROBES, NO_ACTION)

        self.assertEqual(
            [
                MenuRole.STATUS,
                MenuRole.TOGGLE,
                MenuRole.OPEN_LOG,
                MenuRole.EXIT,
            ],
            roles(menu),
        )

    def test_session_lines_sit_between_the_status_and_the_toggle(self):
        observation = Observation(True, (SESSION, OTHER_SESSION))

        menu = menu_for(observation, NO_ACTION)

        self.assertEqual(
            [
                MenuRole.STATUS,
                MenuRole.SESSION,
                MenuRole.SESSION,
                MenuRole.TOGGLE,
                MenuRole.OPEN_LOG,
                MenuRole.EXIT,
            ],
            roles(menu),
        )

    def test_the_menu_shows_the_compacted_text_of_each_session_line(self):
        padded = SessionLine("claude", "online", "claude     online      12:01:07  3s")
        observation = Observation(True, (padded,))

        menu = menu_for(observation, NO_ACTION)

        self.assertEqual(
            ["claude online 12:01:07 3s"],
            [item.text for item in menu if item.role is MenuRole.SESSION],
        )

    def test_a_long_failure_line_gives_a_status_item_cut_to_the_menu_limit(self):
        actions = finished(ActionKind.START, 1, "ERROR: " + "x" * 300)

        status = menu_for(GREY_PROBES, actions)[0]

        self.assertIs(MenuRole.STATUS, status.role)
        self.assertEqual(settings.MENU_ITEM_LIMIT, len(status.text))
        self.assertTrue(status.text.endswith("..."))

    def test_padded_whitespace_in_a_failure_line_is_collapsed_in_the_status_item(self):
        actions = finished(ActionKind.START, 1, "ERROR:    docker		is   missing")

        status = menu_for(GREY_PROBES, actions)[0]

        self.assertEqual(
            "The stand is broken: Start failed: ERROR: docker is missing",
            status.text,
        )

    def test_a_short_failure_keeps_its_status_item_text(self):
        actions = finished(ActionKind.START, 1, "ERROR: docker is missing")

        status = menu_for(GREY_PROBES, actions)[0]

        self.assertEqual(
            "The stand is broken: Start failed: ERROR: docker is missing",
            status.text,
        )

    def test_the_tooltip_keeps_the_long_failure_line_up_to_its_own_limit(self):
        actions = finished(ActionKind.START, 1, "ERROR: " + "x" * 300)
        state = stand_state(GREY_PROBES, actions)

        self.assertEqual(settings.TOOLTIP_LIMIT, len(tooltip_text(state, ENGLISH)))

    def test_there_are_no_session_lines_while_the_broker_is_silent(self):
        menu = menu_for(ONLY_STACK_PROBES, NO_ACTION)

        self.assertNotIn(MenuRole.SESSION, roles(menu))

    def test_status_and_session_lines_are_not_clickable(self):
        menu = menu_for(GREEN_PROBES, NO_ACTION)

        informational = [
            item for item in menu if item.role in (MenuRole.STATUS, MenuRole.SESSION)
        ]
        self.assertTrue(informational)
        self.assertFalse(any(item.enabled for item in informational))

    def test_open_log_and_exit_are_always_enabled(self):
        for name, observation, actions in (
            ("grey", GREY_PROBES, NO_ACTION),
            ("green", GREEN_PROBES, NO_ACTION),
            ("red", ONLY_STACK_PROBES, NO_ACTION),
            ("yellow", GREY_PROBES, running(ActionKind.START)),
        ):
            with self.subTest(state=name):
                menu = menu_for(observation, actions)

                for item in menu:
                    if item.role in (MenuRole.OPEN_LOG, MenuRole.EXIT):
                        self.assertTrue(item.enabled)

    def test_the_menu_texts_are_english(self):
        menu = menu_for(GREY_PROBES, NO_ACTION)

        self.assertEqual(
            ["The stand is stopped", "Start", "Open log", "Exit"],
            [item.text for item in menu],
        )

    def test_the_menu_texts_are_russian_when_the_language_is_russian(self):
        menu = menu_for(GREY_PROBES, NO_ACTION, RUSSIAN)

        self.assertEqual(
            ["Стенд остановлен"],
            [menu[0].text],
        )


class ToggleItemTests(unittest.TestCase):
    def test_grey_offers_an_enabled_start(self):
        item = toggle_of(menu_for(GREY_PROBES, NO_ACTION))

        self.assertEqual(
            ("Start", True, ActionKind.START), (item.text, item.enabled, item.action)
        )

    def test_green_offers_an_enabled_stop(self):
        item = toggle_of(menu_for(GREEN_PROBES, NO_ACTION))

        self.assertEqual(
            ("Stop", True, ActionKind.STOP), (item.text, item.enabled, item.action)
        )

    def test_yellow_while_starting_shows_a_disabled_starting_item(self):
        item = toggle_of(menu_for(GREY_PROBES, running(ActionKind.START)))

        self.assertEqual(
            ("Starting...", False, ActionKind.START),
            (item.text, item.enabled, item.action),
        )

    def test_yellow_while_stopping_shows_a_disabled_stopping_item(self):
        item = toggle_of(menu_for(GREEN_PROBES, running(ActionKind.STOP)))

        self.assertEqual(
            ("Stopping...", False, ActionKind.STOP),
            (item.text, item.enabled, item.action),
        )

    def test_red_from_a_half_state_offers_start_to_repair_it(self):
        for name, observation in (
            ("stack only", ONLY_STACK_PROBES),
            ("broker only", ONLY_BROKER_PROBES),
        ):
            with self.subTest(probes=name):
                item = toggle_of(menu_for(observation, NO_ACTION))

                self.assertEqual(("Start", True), (item.text, item.enabled))

    def test_red_after_a_failed_start_offers_start_again(self):
        item = toggle_of(menu_for(GREY_PROBES, finished(ActionKind.START, 1, "x")))

        self.assertEqual(
            ("Start", True, ActionKind.START), (item.text, item.enabled, item.action)
        )

    def test_red_after_a_failed_stop_offers_stop_again(self):
        item = toggle_of(menu_for(GREEN_PROBES, finished(ActionKind.STOP, 1, "x")))

        self.assertEqual(
            ("Stop", True, ActionKind.STOP), (item.text, item.enabled, item.action)
        )

    def test_the_offered_action_follows_the_state(self):
        self.assertEqual(
            ActionKind.START, offered_action(stand_state(GREY_PROBES, NO_ACTION))
        )
        self.assertEqual(
            ActionKind.STOP, offered_action(stand_state(GREEN_PROBES, NO_ACTION))
        )


class FixedStatusWordingFitsTheMenuTests(unittest.TestCase):
    FIXED_STATES = {
        "grey": (GREY_PROBES, NO_ACTION),
        "green": (GREEN_PROBES, NO_ACTION),
        "starting": (GREY_PROBES, running(ActionKind.START)),
        "stopping": (GREEN_PROBES, running(ActionKind.STOP)),
        "only the stack answers": (ONLY_STACK_PROBES, NO_ACTION),
        "only the broker answers": (ONLY_BROKER_PROBES, NO_ACTION),
        "start failed without output": (GREY_PROBES, finished(ActionKind.START, 127)),
        "stop failed without output": (GREEN_PROBES, finished(ActionKind.STOP, 127)),
    }

    def test_every_fixed_status_text_fits_the_menu_limit_in_every_language(self):
        for language in ("en", "ru"):
            for name, (observation, actions) in self.FIXED_STATES.items():
                with self.subTest(language=language, state=name):
                    text = status_text(
                        stand_state(observation, actions), TrayTexts(language)
                    )

                    self.assertLessEqual(len(text), settings.MENU_ITEM_LIMIT)


class StatusWordingTests(unittest.TestCase):
    def status(self, observation, actions, texts=ENGLISH):
        return status_text(stand_state(observation, actions), texts)

    def test_grey_says_the_stand_is_stopped(self):
        self.assertEqual("The stand is stopped", self.status(GREY_PROBES, NO_ACTION))

    def test_green_says_the_stand_is_running(self):
        self.assertEqual("The stand is running", self.status(GREEN_PROBES, NO_ACTION))

    def test_yellow_says_what_is_being_done(self):
        self.assertEqual(
            "Starting the stand...",
            self.status(GREY_PROBES, running(ActionKind.START)),
        )
        self.assertEqual(
            "Stopping the stand...",
            self.status(GREEN_PROBES, running(ActionKind.STOP)),
        )

    def test_red_with_only_the_stack_names_the_silent_broker(self):
        self.assertEqual(
            "The stand is broken: port 443 answers but the broker does not",
            self.status(ONLY_STACK_PROBES, NO_ACTION),
        )

    def test_red_with_only_the_broker_names_the_silent_port(self):
        self.assertEqual(
            "The stand is broken: the broker answers but port 443 does not",
            self.status(ONLY_BROKER_PROBES, NO_ACTION),
        )

    def test_red_after_a_failed_start_quotes_the_last_output_line(self):
        actions = finished(ActionKind.START, 1, "ERROR: docker is missing")

        self.assertEqual(
            "The stand is broken: Start failed: ERROR: docker is missing",
            self.status(GREY_PROBES, actions),
        )

    def test_red_after_a_failed_stop_quotes_the_last_output_line(self):
        actions = finished(ActionKind.STOP, 1, "ERROR: compose down failed")

        self.assertEqual(
            "The stand is broken: Stop failed: ERROR: compose down failed",
            self.status(GREEN_PROBES, actions),
        )

    def test_a_failure_without_any_output_falls_back_to_the_exit_code(self):
        actions = finished(ActionKind.START, 3, "")

        self.assertEqual(
            "The stand is broken: Start failed: exit code 3",
            self.status(GREY_PROBES, actions),
        )

    def test_the_russian_reasons_are_russian(self):
        text = self.status(ONLY_STACK_PROBES, NO_ACTION, RUSSIAN)

        self.assertEqual(
            "Стенд неисправен: порт 443 отвечает, а брокер нет",
            text,
        )


class TooltipTests(unittest.TestCase):
    def test_the_tooltip_names_the_app_and_the_state(self):
        state = stand_state(GREEN_PROBES, NO_ACTION)

        self.assertEqual("Quoroom: The stand is running", tooltip_text(state, ENGLISH))

    def test_a_red_tooltip_carries_the_reason(self):
        state = stand_state(ONLY_STACK_PROBES, NO_ACTION)

        self.assertIn("the broker does not", tooltip_text(state, ENGLISH))

    def test_a_long_reason_is_cut_to_the_windows_tooltip_limit(self):
        actions = finished(ActionKind.START, 1, "ERROR: " + "x" * 300)
        state = stand_state(GREY_PROBES, actions)

        tooltip = tooltip_text(state, ENGLISH)

        self.assertEqual(settings.TOOLTIP_LIMIT, len(tooltip))
        self.assertTrue(tooltip.endswith("..."))

    def test_a_short_tooltip_is_not_cut(self):
        state = stand_state(GREY_PROBES, NO_ACTION)

        self.assertFalse(tooltip_text(state, ENGLISH).endswith("..."))


class MenuItemTextTests(unittest.TestCase):
    def test_runs_of_whitespace_become_a_single_space(self):
        self.assertEqual(
            "claude online 12:01:07 3s",
            menu_item_text("  claude     online\t\t12:01:07   3s  "),
        )

    def test_a_line_of_exactly_the_limit_is_kept_whole(self):
        line = "a" * settings.MENU_ITEM_LIMIT

        self.assertEqual(line, menu_item_text(line))

    def test_a_line_one_over_the_limit_is_cut_to_the_limit_with_an_ellipsis(self):
        line = "a" * (settings.MENU_ITEM_LIMIT + 1)

        text = menu_item_text(line)

        self.assertEqual(settings.MENU_ITEM_LIMIT, len(text))
        self.assertEqual("a" * (settings.MENU_ITEM_LIMIT - 3) + "...", text)

    def test_the_limit_applies_after_the_whitespace_is_collapsed(self):
        head = "a" * 10
        tail = "b" * (settings.MENU_ITEM_LIMIT - len(head) - 1)

        text = menu_item_text(head + " " * 100 + tail)

        self.assertEqual(head + " " + tail, text)
        self.assertEqual(settings.MENU_ITEM_LIMIT, len(text))

    def test_cyrillic_text_is_counted_in_characters_not_bytes(self):
        ya = "\u044f"
        fits = ya * settings.MENU_ITEM_LIMIT
        over = ya * (settings.MENU_ITEM_LIMIT + 1)

        self.assertEqual(fits, menu_item_text(fits))
        self.assertEqual(
            ya * (settings.MENU_ITEM_LIMIT - 3) + "...",
            menu_item_text(over),
        )

    def test_backslash_sequences_are_shown_as_the_broker_reports_them(self):
        text = r"a\nb\u0436"

        self.assertEqual(text, menu_item_text(text))


class LeftClickTests(unittest.TestCase):
    def decide(self, observation, actions):
        return left_click(stand_state(observation, actions), ENGLISH)

    def test_green_opens_element_in_the_browser(self):
        self.assertEqual(
            OpenElement("https://agentschat.local/"),
            self.decide(GREEN_PROBES, NO_ACTION),
        )

    def test_every_other_state_notifies_and_opens_nothing(self):
        for name, observation, actions in (
            ("grey", GREY_PROBES, NO_ACTION),
            ("yellow", GREY_PROBES, running(ActionKind.START)),
            ("red from the stack only", ONLY_STACK_PROBES, NO_ACTION),
            ("red from the broker only", ONLY_BROKER_PROBES, NO_ACTION),
            ("red from a failure", GREEN_PROBES, finished(ActionKind.STOP, 1, "x")),
        ):
            with self.subTest(state=name):
                self.assertEqual(
                    ShowNotification("The stand is not running."),
                    self.decide(observation, actions),
                )

    def test_the_notification_is_russian_when_the_language_is_russian(self):
        decision = left_click(stand_state(GREY_PROBES, NO_ACTION), RUSSIAN)

        self.assertEqual(
            ShowNotification("Стенд не запущен."),
            decision,
        )


if __name__ == "__main__":
    unittest.main()
