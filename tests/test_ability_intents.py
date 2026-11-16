"""Routine grammar turns explicit bounded commands into reviewable data only."""
import unittest
from unittest.mock import patch

from sara_app import ability_intents


class AbilityIntentTests(unittest.TestCase):
    def test_supported_semicolon_steps_preserve_names_and_order(self):
        result = ability_intents.plan_ability_command('create routine "work mode": open notepad; volume 30 percent karo; search web for Python docs')
        self.assertTrue(result["requires_confirmation"])
        action = result["action"]
        self.assertEqual(action["type"], "save_routine")
        self.assertEqual(action["name"], "work mode")
        self.assertEqual(action["steps"], [{"type": "open_app", "app": "notepad"}, {"type": "media_control", "command": "set_volume", "level": 30}, {"type": "open_browser_url", "url": "https://www.google.com/search?q=Python+docs"}])

    def test_any_unsupported_step_rejects_whole_draft_and_never_returns_action(self):
        for suffix in ("delete a file", "type password", "open https://bank.example/send?to=someone", "", "open notepad;" ):
            with self.subTest(suffix=suffix):
                result = ability_intents.plan_ability_command("save routine office: open calculator; " + suffix)
                self.assertNotIn("action", result)
                self.assertEqual(result["clarification"]["kind"], "routine")

    def test_list_and_run_are_explicit_and_saved_snapshot_is_preserved(self):
        record = {"name": "work mode", "steps": [{"type": "open_app", "app": "notepad"}]}
        action = {"type": "run_routine", "name": "work mode", "id": "a" * 32, "revision": "b" * 64, "steps": record["steps"]}
        with patch.object(ability_intents, "list_routines", return_value=[record]), patch.object(ability_intents, "routine_action_for_name", return_value=action) as lookup:
            self.assertIn("work mode", ability_intents.plan_ability_command("meri routines dikhao")["reply"])
            self.assertEqual(ability_intents.plan_ability_command("run routine work mode")["action"], action)
            self.assertEqual(ability_intents.plan_ability_command("work mode chalao")["action"], action)
            self.assertEqual(lookup.call_count, 2)
            self.assertIsNone(ability_intents.plan_ability_command("unregistered thing chalao"))

    def test_missing_saved_name_is_a_clarification_not_a_fabricated_action(self):
        with patch.object(ability_intents, "routine_action_for_name", side_effect=ValueError("No saved routine was found")):
            result = ability_intents.plan_ability_command("run routine missing")
        self.assertNotIn("action", result)
        self.assertIn("No saved routine", result["reply"])

    def test_unrelated_or_negated_prose_is_not_an_executable_routine(self):
        for message in ("explain how to create routine work mode: open notepad", "do not run routine work mode", "write a story about routines", "how do I mute audio", "don't mute"):
            with self.subTest(message=message): self.assertIsNone(ability_intents.plan_ability_command(message))

    def test_media_and_readonly_audio_status_are_distinct(self):
        for message in ("volume status", "audio status", "volume kitna hai", "Sara, speaker status?"):
            with self.subTest(message=message):
                self.assertTrue(ability_intents.is_audio_status_question(message))
                self.assertIsNone(ability_intents.plan_ability_command(message))
        command = ability_intents.plan_ability_command("volume 30 percent karo")
        self.assertEqual(command["action"]["type"], "media_control")
        self.assertFalse(ability_intents.is_audio_status_question("volume 30 percent karo"))


if __name__ == "__main__":
    unittest.main()
