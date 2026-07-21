import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from homebot.agent.tools.browser import BrowserActionError, BrowserTool


class BrowserToolTest(unittest.IsolatedAsyncioTestCase):
    def make_tool(self) -> BrowserTool:
        return BrowserTool(user_data_dir="/tmp/homebot-browser-test", poll_interval_seconds=0)

    async def test_launches_chrome_with_persistent_cookie_and_autoplay_settings(self) -> None:
        tool = self.make_tool()
        context = MagicMock()
        context.pages = []
        playwright = MagicMock()
        playwright.chromium.launch_persistent_context = AsyncMock(return_value=context)
        manager = MagicMock()
        manager.start = AsyncMock(return_value=playwright)

        with (
            patch("homebot.agent.tools.browser.async_playwright", return_value=manager),
            patch.object(Path, "is_file", return_value=True),
        ):
            await tool._ensure_context()

        playwright.chromium.launch_persistent_context.assert_awaited_once_with(
            "/tmp/homebot-browser-test",
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            headless=False,
            args=["--profile-directory=Homebot", "--autoplay-policy=no-user-gesture-required"],
            ignore_default_args=[
                "--disable-component-update",
                "--disable-extensions",
                "--password-store=basic",
                "--use-mock-keychain",
            ],
        )

    async def test_rejects_missing_open_url(self) -> None:
        result = await self.make_tool().execute(action="open")

        self.assertEqual(json.loads(result.removeprefix("Error: "))["code"], "MISSING_URL")

    async def test_rejects_missing_page_id(self) -> None:
        result = await self.make_tool().execute(action="inspect")

        self.assertEqual(json.loads(result.removeprefix("Error: "))["code"], "MISSING_PAGE_ID")

    async def test_open_times_out_when_context_startup_hangs(self) -> None:
        tool = self.make_tool()

        async def wait_forever() -> None:
            await asyncio.Event().wait()

        tool._ensure_context = wait_forever

        result = await tool.execute(action="open", url="https://example.test", timeout_seconds=0.01)

        self.assertEqual(json.loads(result.removeprefix("Error: "))["code"], "TIMEOUT")

    async def test_open_closes_page_when_navigation_fails(self) -> None:
        tool = self.make_tool()
        page = MagicMock()
        page.url = "about:blank"
        page.is_closed.return_value = False
        page.bring_to_front = AsyncMock()
        page.goto = AsyncMock(side_effect=RuntimeError("offline"))
        page.close = AsyncMock()
        context = MagicMock()
        context.pages = [page]
        tool._context = context

        result = await tool.execute(action="open", url="https://example.test")

        self.assertEqual(json.loads(result.removeprefix("Error: "))["code"], "BROWSER_UNAVAILABLE")
        page.close.assert_awaited_once()
        self.assertEqual(tool._pages, {})

    async def test_click_requires_unique_selector(self) -> None:
        tool = self.make_tool()
        page = MagicMock()
        page.is_closed.return_value = False
        locator = MagicMock()
        locator.count = AsyncMock(return_value=2)
        tool._wait_for_unique_locator = AsyncMock(
            side_effect=BrowserActionError("SELECTOR_NOT_UNIQUE", ".play matched 2 elements")
        )

        with self.assertRaises(BrowserActionError):
            await tool._click(page, ".play", 1)

    async def test_playing_requires_progress(self) -> None:
        tool = self.make_tool()
        page = MagicMock()
        locator = MagicMock()
        locator.evaluate = AsyncMock(
            side_effect=[
                {"paused": False, "current_time": 1, "ended": False},
                {"paused": False, "current_time": 1, "ended": False},
                {"paused": False, "current_time": 2, "ended": False},
                {"paused": False, "current_time": 2.5, "ended": False},
            ]
        )
        page.locator.return_value = locator

        observed = await tool._wait_for_playing(locator, 1)

        self.assertEqual(observed["current_time"], 2.5)

    async def test_closed_page_is_not_reused(self) -> None:
        tool = self.make_tool()
        page = MagicMock()
        page.is_closed.return_value = True
        tool._pages["page-1"] = page

        self.assertIsNone(tool._get_page("page-1"))

    async def test_refresh_sessions_uses_and_closes_temporary_pages(self) -> None:
        tool = self.make_tool()
        first_page = MagicMock()
        first_page.goto = AsyncMock()
        first_page.close = AsyncMock()
        second_page = MagicMock()
        second_page.goto = AsyncMock()
        second_page.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(side_effect=[first_page, second_page])
        tool._context = context

        await tool.refresh_sessions(["https://first.test", "https://second.test"])

        first_page.goto.assert_awaited_once_with(
            "https://first.test", wait_until="domcontentloaded", timeout=15000
        )
        second_page.goto.assert_awaited_once_with(
            "https://second.test", wait_until="domcontentloaded", timeout=15000
        )
        first_page.close.assert_awaited_once()
        second_page.close.assert_awaited_once()
        self.assertEqual(tool._pages, {})

    async def test_refresh_sessions_continues_after_failure(self) -> None:
        tool = self.make_tool()
        failed_page = MagicMock()
        failed_page.goto = AsyncMock(side_effect=RuntimeError("offline"))
        failed_page.close = AsyncMock()
        successful_page = MagicMock()
        successful_page.goto = AsyncMock()
        successful_page.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(side_effect=[failed_page, successful_page])
        tool._context = context

        with self.assertRaisesRegex(RuntimeError, "https://failed.test: offline"):
            await tool.refresh_sessions(["https://failed.test", "https://successful.test"])

        successful_page.goto.assert_awaited_once()
        failed_page.close.assert_awaited_once()
        successful_page.close.assert_awaited_once()

    async def test_close_stops_persistent_browser(self) -> None:
        tool = self.make_tool()
        context = MagicMock()
        context.close = AsyncMock()
        playwright = MagicMock()
        playwright.stop = AsyncMock()
        tool._context = context
        tool._playwright = playwright
        tool._pages["page-1"] = MagicMock()

        await tool.close()

        context.close.assert_awaited_once()
        playwright.stop.assert_awaited_once()
        self.assertIsNone(tool._context)
        self.assertIsNone(tool._playwright)
        self.assertEqual(tool._pages, {})

    async def test_is_context_alive_returns_false_when_pages_throws(self) -> None:
        tool = self.make_tool()
        dead_context = MagicMock()
        type(dead_context).pages = property(lambda _: (_ for _ in ()).throw(RuntimeError("Target closed")))
        tool._context = dead_context

        self.assertFalse(await tool._is_context_alive())

    async def test_ensure_context_tears_down_dead_context(self) -> None:
        tool = self.make_tool()
        dead_context = MagicMock()
        dead_context.close = AsyncMock()
        type(dead_context).pages = property(lambda _: (_ for _ in ()).throw(RuntimeError("Target closed")))
        dead_playwright = MagicMock()
        dead_playwright.stop = AsyncMock()
        tool._context = dead_context
        tool._playwright = dead_playwright
        tool._pages["page-1"] = MagicMock()

        fresh_context = MagicMock()
        fresh_context.pages = []
        fresh_playwright = MagicMock()
        fresh_playwright.chromium.launch_persistent_context = AsyncMock(return_value=fresh_context)
        manager = MagicMock()
        manager.start = AsyncMock(return_value=fresh_playwright)

        with (
            patch("homebot.agent.tools.browser.async_playwright", return_value=manager),
            patch.object(Path, "is_file", return_value=True),
        ):
            await tool._ensure_context()

        dead_context.close.assert_awaited_once()
        dead_playwright.stop.assert_awaited_once()
        self.assertEqual(tool._pages, {})
        self.assertIs(tool._context, fresh_context)

    async def test_ensure_context_reuses_live_context(self) -> None:
        tool = self.make_tool()
        live_context = MagicMock()
        live_context.pages = []
        tool._context = live_context

        with patch.object(Path, "is_file", return_value=True):
            await tool._ensure_context()

        self.assertIs(tool._context, live_context)

    async def test_success_result_contains_page_state(self) -> None:
        page = MagicMock()
        page.url = "https://example.test"
        page.title = AsyncMock(return_value="Example")

        result = json.loads(await BrowserTool._success("inspect", "page-1", page, {"ready_state": "complete"}))

        self.assertTrue(result["ok"])
        self.assertEqual(result["page_id"], "page-1")
        self.assertEqual(result["title"], "Example")


if __name__ == "__main__":
    unittest.main()
