import unittest
from sara_app.followups import plan_search

class SearchContinuityTests(unittest.TestCase):
    def test_current_query_wins_over_old_launch(self):
        plan = plan_search('ab search python', [{'question': 'open chrome'}])
        self.assertEqual(plan['action']['type'], 'open_browser_url')
        self.assertTrue(plan['action']['url'].endswith('q=python'))

    def test_hinglish_suffix(self):
        self.assertEqual(plan_search('python tutorials search karo')['search_query'], 'python tutorials')

    def test_reference_requires_search_context(self):
        self.assertNotIn('action', plan_search('search that', [{'question': 'open chrome'}]))
        self.assertEqual(plan_search('search that', [{'search_query': 'python tutorials'}])['search_query'], 'python tutorials')

    def test_no_execution_of_old_or_unrelated_text(self):
        self.assertIsNone(plan_search('open notepad', [{'question': 'delete file x'}]))
        self.assertIsNone(plan_search('yes'))
