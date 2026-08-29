from __future__ import print_function

import importlib.util
import os
import unittest


MODULE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto.py")
SPEC = importlib.util.spec_from_file_location("scene_issue_auto_submit_activity", MODULE_PATH)
auto = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auto)


class SubmittedMessageActivityTests(unittest.TestCase):
    def test_confirmed_prompt_records_submission_for_owner_tab(self):
        registry = {"tasks": {"capture": {
            "status": "in_progress",
            "owner": "agent-2",
            "prompt_count": 0,
        }}}

        auto.mark_prompted("capture", registry, now=1234)

        self.assertEqual(1234, registry["tabs"]["2"]["last_submit"])
        self.assertEqual(1234, registry["tasks"]["capture"]["last_prompted"])

    def test_refresh_has_its_own_cooldown_and_does_not_change_last_submit(self):
        registry = {"tasks": {}, "tabs": {"3": {"last_submit": 100}}}

        auto.mark_tab_refresh(3, registry, now=2000)

        self.assertEqual(100, registry["tabs"]["3"]["last_submit"])
        self.assertEqual(2000, registry["tabs"]["3"]["last_refresh"])
        self.assertFalse(auto.tab_needs_refresh(3, registry, now=2001))
        self.assertTrue(auto.tab_needs_refresh(
            3, registry, now=2000 + auto.TAB_REFRESH_AFTER_SECONDS))

    def test_typing_resets_the_inactive_tab_clock_even_if_submission_fails(self):
        registry = {"tasks": {}, "tabs": {"3": {"last_submit": 100}}}
        replacements = {
            "replace_composer_text": lambda text: True,
            "submit_current_message": lambda: False,
        }
        missing = object()
        previous = {name: getattr(auto, name, missing) for name in replacements}
        for name, value in replacements.items():
            setattr(auto, name, value)

        def restore():
            for name, value in previous.items():
                if value is missing:
                    delattr(auto, name)
                else:
                    setattr(auto, name, value)

        self.addCleanup(restore)

        self.assertFalse(auto.send_tab_message(3, registry, "draft"))
        self.assertGreater(registry["tabs"]["3"]["last_typed"], 100)

    def test_newly_observed_running_tab_counts_as_activity(self):
        registry = {
            "version": 1,
            "tasks": {},
            "tabs": {"4": {"last_submit": 1}},
        }
        events = []
        replacements = {
            "switch_to_tab": lambda number: events.append(("tab", number)),
            "recover_long_conversation": lambda name, unused_registry: False,
            "image_exists": lambda filename, timeout: filename == auto.RUNNING_IMAGE,
            "refresh_tab_page": lambda: events.append(("refresh",)),
        }
        missing = object()
        previous = {name: getattr(auto, name, missing) for name in replacements}
        for name, value in replacements.items():
            setattr(auto, name, value)

        def restore():
            for name, value in previous.items():
                if value is missing:
                    delattr(auto, name)
                else:
                    setattr(auto, name, value)

        self.addCleanup(restore)

        auto.handle_tab(4, registry, [])

        self.assertEqual([("tab", 4)], events)
        self.assertEqual(1, registry["tabs"]["4"]["last_submit"])
        self.assertGreater(registry["tabs"]["4"]["busy_since"], 1)

    def test_continuously_running_tab_is_refreshed_after_twenty_minutes(self):
        registry = {"tasks": {}, "tabs": {"4": {"last_submit": 1}}}

        self.assertFalse(auto.tab_needs_refresh(4, registry, now=100, busy=True))
        self.assertFalse(auto.tab_needs_refresh(
            4, registry, now=100 + auto.TAB_REFRESH_AFTER_SECONDS - 1, busy=True))
        self.assertTrue(auto.tab_needs_refresh(
            4, registry, now=100 + auto.TAB_REFRESH_AFTER_SECONDS, busy=True))

    def test_idle_tab_uses_latest_typing_or_submission(self):
        registry = {"tasks": {}, "tabs": {
            "5": {"last_submit": 100, "last_typed": 500},
        }}

        self.assertFalse(auto.tab_needs_refresh(
            5, registry, now=500 + auto.TAB_REFRESH_AFTER_SECONDS - 1))
        self.assertTrue(auto.tab_needs_refresh(
            5, registry, now=500 + auto.TAB_REFRESH_AFTER_SECONDS))


if __name__ == "__main__":
    unittest.main()
