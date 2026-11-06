import unittest

from sara_app.speech import PLAYBACK_MAX_CHARS, fallback_speech_text, prepare_speech


class SpeechPreparationTests(unittest.TestCase):
    def test_mixed_language_words_use_matching_voice_segments(self):
        result = prepare_speech("Mujhe aaj ka dashboard dikhao, please.")
        self.assertEqual(result["text"], "मुझे आज का dashboard दिखाओ, please.")
        self.assertEqual(result["segments"], [
            {"text": "मुझे आज का", "lang": "hi-IN"},
            {"text": "dashboard", "lang": "en-IN"},
            {"text": "दिखाओ,", "lang": "hi-IN"},
            {"text": "please.", "lang": "en-IN"},
        ])

    def test_mixed_sentence_uses_one_fluent_playback_voice(self):
        result = prepare_speech("SARA, mujhe aaj ka dashboard dikhao, please.")
        self.assertGreater(len(result["segments"]), 1)
        self.assertEqual(result["playback"], [{
            "text": "सारा, मुझे आज का डैशबोर्ड दिखाओ, प्लीज़.", "lang": "hi-IN",
        }])
        self.assertIn("dashboard", result["text"])

    def test_same_voice_sentences_merge_but_pure_english_stays_english(self):
        result = prepare_speech("Main SARA hoon. Aapka network ready hai. The application is working normally.")
        self.assertEqual(len(result["playback"]), 2)
        self.assertEqual(result["playback"][0], {"text": "मैं सारा हूँ. आपका नेटवर्क रेडी है.", "lang": "hi-IN"})
        self.assertEqual(result["playback"][1], {"text": "The application is working normally.", "lang": "en-IN"})

    def test_hindi_playback_known_technical_phrases_do_not_change_original_text(self):
        result = prepare_speech("Aapka UI aur API ready hai.")
        self.assertIn("user interface", result["text"])
        self.assertIn("application programming interface", result["text"])
        self.assertEqual(result["playback"], [{
            "text": "आपका यूज़र इंटरफ़ेस और एप्लिकेशन प्रोग्रामिंग इंटरफ़ेस रेडी है.", "lang": "hi-IN",
        }])

    def test_unknown_names_and_words_remain_intact_in_hindi_playback(self):
        result = prepare_speech("Mujhe Zephyr aur Kubernetes batao, Sarah.")
        spoken = " ".join(part["text"] for part in result["playback"])
        self.assertEqual(len(result["playback"]), 1)
        for word in ("Zephyr", "Kubernetes", "Sarah"):
            self.assertIn(word, spoken)

    def test_long_prose_is_bounded_without_losing_or_reordering_words(self):
        original = " ".join("This sentence retains every ordinary word and its punctuation." for _ in range(25))
        result = prepare_speech(original)
        self.assertGreater(len(result["playback"]), 1)
        self.assertTrue(all(len(part["text"]) <= PLAYBACK_MAX_CHARS for part in result["playback"]))
        self.assertEqual(" ".join(part["text"] for part in result["playback"]), original)
        self.assertTrue(all(part["text"].endswith(".") for part in result["playback"]))

    def test_long_unpunctuated_phrase_groups_words_instead_of_each_word(self):
        original = " ".join(f"word{index}" for index in range(150))
        result = prepare_speech(original)
        self.assertGreater(len(result["playback"]), 1)
        self.assertLess(len(result["playback"]), 10)
        self.assertTrue(all(len(part["text"]) <= PLAYBACK_MAX_CHARS for part in result["playback"]))
        self.assertEqual(" ".join(part["text"] for part in result["playback"]), original)

    def test_unknown_single_oversized_token_is_not_split_into_letters(self):
        word = "Zephyr" * 90
        result = prepare_speech(word)
        self.assertEqual(result["playback"], [{"text": word, "lang": "en-IN"}])

    def test_title_does_not_create_a_tiny_playback_utterance(self):
        result = prepare_speech("Dr. Zephyr is ready. Sarah is ready too.")
        self.assertEqual(result["playback"], [{"text": "Dr. Zephyr is ready. Sarah is ready too.", "lang": "en-IN"}])

    def test_sara_is_a_name_and_known_acronyms_are_spoken_phrases(self):
        result = prepare_speech("SARA: UI and API ready.")
        self.assertEqual(result["text"], "Sara: user interface and application programming interface ready.")
        self.assertEqual(len(result["segments"]), 1)
        self.assertEqual(result["segments"][0]["lang"], "en-IN")

    def test_only_known_sara_initials_are_joined_into_a_spoken_name(self):
        result = prepare_speech("S.A.R.A. is ready; S A R A will help Sarah.")
        self.assertEqual(result["text"], "Sara is ready; Sara will help Sarah.")
        self.assertEqual(len(result["segments"]), 1)

    def test_other_names_and_unknown_spaced_initials_remain_unchanged(self):
        original = "Sarah, S.A.R.A.H. and S A R A H meet N A S A."
        self.assertEqual(prepare_speech(original)["text"], original)

    def test_unknown_words_stay_intact_and_english(self):
        result = prepare_speech("Try Kubernetes and Zephyr, not K-u-b-e-r-n-e-t-e-s.")
        self.assertIn("Kubernetes and Zephyr", result["text"])
        self.assertNotIn("kay", result["text"])
        self.assertTrue(all(segment["lang"] == "en-IN" for segment in result["segments"]))

    def test_markdown_labels_remain_but_urls_and_code_blocks_are_skipped(self):
        result = prepare_speech("## Status\n- **Ready** for [voice test](https://example.com/test).\n```python\nprint('secret code')\n```\nUse `Settings` now.")
        self.assertEqual(result["text"], "Status Ready for voice test. Use Settings now.")
        self.assertNotIn("example", result["text"])
        self.assertNotIn("secret", result["text"])

    def test_math_comparisons_are_not_mistaken_for_html(self):
        original = "The comparison is 2 < 3 and 5 > 2; also 2 <= 3 and 5 >= 2."
        self.assertEqual(prepare_speech(original)["text"], original)

    def test_real_html_tags_are_removed_without_dropping_comparisons(self):
        result = prepare_speech('<p>Compare <b>2</b> &lt; 3 and 5 &gt; 2.</p><span title="x > y">Ready</span>')
        self.assertEqual(result["text"], "Compare 2 < 3 and 5 > 2. Ready")

    def test_existing_hindi_and_english_keep_their_scripts(self):
        result = prepare_speech("आपका network ready है।")
        self.assertEqual(result["text"], "आपका network ready है।")
        self.assertEqual([segment["lang"] for segment in result["segments"]], ["hi-IN", "en-IN", "hi-IN"])

    def test_common_hinglish_spellings_are_converted_without_network(self):
        spoken = fallback_speech_text("Haan, main samajh sakti hoon. Aap thoda jaldi bataiye.")
        self.assertEqual(spoken, "हाँ, मैं समझ सकती हूँ. आप थोड़ा जल्दी बताइए.")

    def test_english_main_and_the_are_not_transliterated(self):
        result = prepare_speech("The main window is ready for the user.")
        self.assertEqual(result["text"], "The main window is ready for the user.")
        self.assertEqual(result["segments"], [{"text": result["text"], "lang": "en-IN"}])

    def test_main_window_in_hinglish_keeps_english_adjective(self):
        self.assertEqual(prepare_speech("Mujhe main window dikhao")["text"], "मुझे main window दिखाओ")

    def test_ambiguous_english_words_are_not_hindi_without_context(self):
        result = prepare_speech("We hum while eating a banana.")
        self.assertEqual(result["text"], "We hum while eating a banana.")
        self.assertEqual(result["segments"], [{"text": result["text"], "lang": "en-IN"}])

    def test_unicode_name_is_not_dropped(self):
        self.assertEqual(prepare_speech("Renée shared her résumé.")["text"], "Renée shared her résumé.")

    def test_empty_display_only_content_produces_no_utterance(self):
        self.assertEqual(prepare_speech("```js\nconst x = 1;\n```"), {"text": "", "segments": [], "playback": []})


if __name__ == "__main__":
    unittest.main()
