import unittest
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor
from unittest.mock import MagicMock, patch

from sara_app import browser_control
from sara_app.browser_control import click_text, fill_text, open_page, whatsapp_send


class BrowserSafetyTests(unittest.TestCase):
    def test_open_requires_confirmation(self):
        result = open_page("https://example.com")
        self.assertTrue(result["requires_confirmation"])

    def test_click_requires_confirmation(self):
        result = click_text("https://example.com", "More information")
        self.assertTrue(result["requires_confirmation"])

    def test_fill_requires_confirmation(self):
        result = fill_text("https://example.com", "Email", "user@example.com")
        self.assertTrue(result["requires_confirmation"])

    def test_non_https_is_rejected(self):
        with self.assertRaises(ValueError):
            open_page("http://example.com")

    def test_whatsapp_send_requires_confirmation(self):
        result = whatsapp_send("919876543210", "hello")
        self.assertTrue(result["requires_confirmation"])

    def test_unconfirmed_actions_do_not_submit_browser_work(self):
        with patch.object(browser_control._worker._executor, "submit") as submit:
            open_page("https://example.com")
            click_text("https://example.com", "More information")
            fill_text("https://example.com", "Email", "user@example.com")
            whatsapp_send("919876543210", "hello")
        submit.assert_not_called()


class BrowserWorkerTests(unittest.TestCase):
    def setUp(self):
        self.worker = browser_control._BrowserWorker()
        worker_patch = patch.object(browser_control, "_worker", self.worker)
        worker_patch.start()
        self.addCleanup(worker_patch.stop)
        self.addCleanup(self.worker.shutdown, lambda: None)
        self.page = MagicMock()
        self.page.url = "https://example.com/page"
        self.page.is_closed.return_value = False
        self.context = MagicMock()
        self.context.pages = [self.page]
        self.context_patch = patch.object(browser_control, "_context_for_browser", return_value=self.context)
        self.context_mock = self.context_patch.start()
        self.addCleanup(self.context_patch.stop)
        self.log_patch = patch.object(browser_control, "log")
        self.log_mock = self.log_patch.start()
        self.addCleanup(self.log_patch.stop)

    def test_request_threads_share_one_browser_owner(self):
        browser_threads = set()
        request_threads = set()
        callers_ready = threading.Barrier(3)

        def context_on_worker():
            browser_threads.add(threading.get_ident())
            return self.context

        def navigate_on_worker(*args, **kwargs):
            browser_threads.add(threading.get_ident())

        def request(index):
            request_threads.add(threading.get_ident())
            callers_ready.wait(timeout=5)
            return open_page(f"https://example.com/page?request={index}", confirmed=True)

        self.context_mock.side_effect = context_on_worker
        self.page.goto.side_effect = navigate_on_worker
        with ThreadPoolExecutor(max_workers=3) as requests:
            results = list(requests.map(request, range(3)))

        self.assertTrue(all(result["ok"] for result in results))
        self.assertEqual(len(request_threads), 3)
        self.assertEqual(len(browser_threads), 1)
        self.assertTrue(browser_threads.isdisjoint(request_threads))

    def test_loaded_click_and_fill_do_not_reload_the_page(self):
        click_text(self.page.url, "Continue", confirmed=True)
        fill_text(self.page.url, "Email", "user@example.com", confirmed=True)

        self.page.goto.assert_not_called()
        self.assertEqual(self.page.wait_for_load_state.call_count, 2)
        self.page.wait_for_load_state.assert_called_with("domcontentloaded", timeout=15000)
        self.page.get_by_text.assert_called_once_with("Continue", exact=True)
        self.page.get_by_text.return_value.first.click.assert_called_once_with(timeout=8000)
        self.page.get_by_label.return_value.fill.assert_called_once_with("user@example.com", timeout=8000)

    def test_different_target_still_navigates(self):
        target = "https://example.com/other"
        click_text(target, "Continue", confirmed=True)
        self.page.goto.assert_called_once_with(target, wait_until="domcontentloaded", timeout=15000)
        self.page.wait_for_load_state.assert_not_called()

    def test_explicit_open_still_navigates_matching_page(self):
        open_page(self.page.url, confirmed=True)
        self.page.goto.assert_called_once_with(self.page.url, wait_until="domcontentloaded", timeout=15000)

    def test_closed_pages_are_not_reused(self):
        self.page.is_closed.return_value = True
        fresh = MagicMock()
        fresh.url = "about:blank"
        self.context.new_page.return_value = fresh
        open_page("https://example.com/fresh", confirmed=True)
        self.page.goto.assert_not_called()
        self.context.new_page.assert_called_once()
        fresh.goto.assert_called_once_with("https://example.com/fresh", wait_until="domcontentloaded", timeout=15000)

    def test_browser_failure_propagates_without_success_log(self):
        self.page.get_by_text.return_value.first.click.side_effect = RuntimeError("element unavailable")
        with self.assertRaisesRegex(RuntimeError, "element unavailable"):
            click_text(self.page.url, "Continue", confirmed=True)
        self.log_mock.assert_not_called()

    def test_whatsapp_preserves_navigation_and_send_fallback(self):
        self.page.get_by_role.return_value.click.side_effect = RuntimeError("role locator unavailable")
        result = whatsapp_send("919876543210", "hello", confirmed=True)
        self.assertTrue(result["ok"])
        self.page.goto.assert_called_once_with(
            "https://web.whatsapp.com/send?phone=919876543210&text=hello",
            wait_until="domcontentloaded", timeout=20000,
        )
        self.page.get_by_role.assert_called_once_with("button", name="Send")
        self.page.get_by_role.return_value.click.assert_called_once_with(timeout=15000)
        self.page.locator.assert_called_once_with("span[data-icon='send']")
        self.page.locator.return_value.last.click.assert_called_once_with(timeout=8000)


class BrowserLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.worker = browser_control._BrowserWorker()
        self.context = MagicMock()
        self.playwright = MagicMock()
        for name, value in (("_worker", self.worker), ("_context", self.context), ("_playwright", self.playwright)):
            patcher = patch.object(browser_control, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.log_patch = patch.object(browser_control, "log")
        self.log_mock = self.log_patch.start()
        self.addCleanup(self.log_patch.stop)
        self.addCleanup(browser_control.shutdown_browser)

    def test_unused_shutdown_does_not_submit_cleanup_or_start_thread(self):
        with patch.object(self.worker._executor, "submit") as submit:
            shutdown_result = browser_control.shutdown_browser()
        self.assertIsNone(shutdown_result)
        submit.assert_not_called()
        self.context.close.assert_not_called()
        self.playwright.stop.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "shutting down"):
            browser_control._run_browser(lambda: None)

    def test_shutdown_cancels_queued_actions_and_cleans_up_after_active_work(self):
        active_started = threading.Event()
        release_active = threading.Event()
        queued_submitted = threading.Event()
        events = []
        owner_threads = set()

        def active():
            owner_threads.add(threading.get_ident())
            events.append("active started")
            active_started.set()
            if not release_active.wait(timeout=5):
                raise AssertionError("active browser operation was not released")
            events.append("active ended")

        def queued():
            events.append("queued action ran")

        def closed():
            owner_threads.add(threading.get_ident())
            events.append("context closed")

        def stopped():
            owner_threads.add(threading.get_ident())
            events.append("driver stopped")

        original_submit = self.worker._executor.submit

        def track_submission(*args, **kwargs):
            future = original_submit(*args, **kwargs)
            if len(args) > 1 and args[1] is queued:
                queued_submitted.set()
            return future

        self.context.close.side_effect = closed
        self.playwright.stop.side_effect = stopped
        with patch.object(self.worker._executor, "submit", side_effect=track_submission):
            with ThreadPoolExecutor(max_workers=3) as callers:
                active_call = callers.submit(browser_control._run_browser, active)
                try:
                    self.assertTrue(active_started.wait(timeout=2))
                    queued_call = callers.submit(browser_control._run_browser, queued)
                    self.assertTrue(queued_submitted.wait(timeout=2))
                    shutdown_call = callers.submit(browser_control.shutdown_browser)
                    with self.assertRaises(CancelledError):
                        queued_call.result(timeout=2)
                    with self.assertRaisesRegex(RuntimeError, "shutting down"):
                        browser_control._run_browser(lambda: None)
                    self.assertFalse(shutdown_call.done())
                    self.context.close.assert_not_called()
                finally:
                    release_active.set()
                active_call.result(timeout=2)
                shutdown_call.result(timeout=2)
        self.assertEqual(events, ["active started", "active ended", "context closed", "driver stopped"])
        self.assertEqual(len(owner_threads), 1)
        self.assertIsNone(browser_control._context)
        self.assertIsNone(browser_control._playwright)
        browser_control.shutdown_browser()
        self.context.close.assert_called_once()
        self.playwright.stop.assert_called_once()

    def test_manually_closed_context_reopens_with_existing_driver(self):
        browser_control._context = None
        first, second = MagicMock(), MagicMock()
        self.playwright.chromium.launch_persistent_context.side_effect = [first, second]
        with patch("playwright.sync_api.sync_playwright") as new_driver, patch("pathlib.Path.mkdir"):
            self.assertTrue(browser_control._run_browser(lambda: browser_control._context_for_browser() is first))
            first.on.assert_called_once()
            event, closed = first.on.call_args.args
            self.assertEqual(event, "close")
            browser_control._run_browser(closed, first)
            self.assertIsNone(browser_control._context)
            self.assertTrue(browser_control._run_browser(lambda: browser_control._context_for_browser() is second))
            new_driver.assert_not_called()
        self.assertEqual(self.playwright.chromium.launch_persistent_context.call_count, 2)
        self.playwright.stop.assert_not_called()

    def test_shutdown_stops_driver_even_when_context_is_already_closed(self):
        browser_control._run_browser(lambda: None)
        self.context.close.side_effect = RuntimeError("context already closed")
        browser_control.shutdown_browser()
        self.playwright.stop.assert_called_once()
        self.log_mock.assert_called_once_with("browser_shutdown_error", {"operation": "close", "error": "context already closed"})


if __name__ == "__main__":
    unittest.main()
