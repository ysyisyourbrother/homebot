"""State-driven local Google Chrome automation powered by Playwright."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:
    PlaywrightTimeoutError = TimeoutError
    async_playwright = None

from homebot.agent.tools.base import Tool, tool_parameters
from homebot.agent.tools.schema import NumberSchema, StringSchema, tool_parameters_schema
from homebot.config.paths import get_browser_data_dir

_DEFAULT_EXECUTABLE_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
_ACTIONS = ("open", "wait", "inspect", "click")
_STATES = ("attached", "visible", "hidden", "enabled", "playing")


class BrowserActionError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


def _normal_url(url: str) -> str:
    return urldefrag(url).url.rstrip("/")


@tool_parameters(
    tool_parameters_schema(
        action=StringSchema("Browser action to perform", enum=_ACTIONS),
        url=StringSchema("URL to open. Required for action=open."),
        page_id=StringSchema("Homebot page ID returned by action=open."),
        selector=StringSchema("Unique CSS selector for wait, inspect, or click."),
        state=StringSchema("Target state for wait or post-click confirmation.", enum=_STATES),
        result_selector=StringSchema("Optional selector to verify after clicking."),
        result_state=StringSchema("State expected for result_selector after clicking.", enum=_STATES),
        timeout_seconds=NumberSchema(description="Operation timeout in seconds.", minimum=1, maximum=60),
        required=["action"],
    )
)
class BrowserTool(Tool):
    """Control a Homebot-owned, visible Google Chrome profile."""

    name = "browser"
    description = (
        "Control Homebot's visible Google Chrome window using a persistent, separate browser profile. "
        "Use action=open to navigate and receive a page_id; action=wait to wait for an element or media state; "
        "action=inspect to read page or element state; and action=click to click one unique CSS selector. "
        "Use returned page_id for later actions. It reports confirmed page state, not merely dispatched actions. "
        "Do not use it to bypass login, payment, copyright, or access controls."
    )

    def __init__(
        self,
        executable_path: str = _DEFAULT_EXECUTABLE_PATH,
        user_data_dir: str = "",
        profile: str = "Homebot",
        timeout_seconds: int = 15,
        poll_interval_seconds: float = 0.25,
    ):
        self._executable_path = Path(executable_path).expanduser()
        self._user_data_dir = get_browser_data_dir(user_data_dir or None)
        self._profile = profile
        self._timeout_seconds = timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._playwright: Any = None
        self._context: Any = None
        self._pages: dict[str, Any] = {}
        self._next_page_id = 1
        self._lock = asyncio.Lock()

    @property
    def read_only(self) -> bool:
        return False

    @property
    def exclusive(self) -> bool:
        return True

    async def execute(
        self,
        action: str,
        url: str = "",
        page_id: str = "",
        selector: str = "",
        state: str = "visible",
        result_selector: str = "",
        result_state: str = "visible",
        timeout_seconds: float | None = None,
        **kwargs: object,
    ) -> str:
        if action not in _ACTIONS:
            return self._error("INVALID_ACTION", f"action must be one of {_ACTIONS}")
        if state not in _STATES or result_state not in _STATES:
            return self._error("INVALID_STATE", f"state must be one of {_STATES}")
        if action == "open" and not url:
            return self._error("MISSING_URL", "url is required for action=open")
        if action in {"wait", "inspect", "click"} and not page_id:
            return self._error("MISSING_PAGE_ID", f"page_id is required for action={action}")
        if action in {"wait", "click"} and not selector:
            return self._error("MISSING_SELECTOR", f"selector is required for action={action}")

        timeout = timeout_seconds or self._timeout_seconds
        async with self._lock:
            try:
                async with asyncio.timeout(timeout):
                    await self._ensure_context()
                    if action == "open":
                        return await self._open(url, timeout)

                    page = self._get_page(page_id)
                    if page is None:
                        return self._error("PAGE_NOT_FOUND", f"No open Homebot page has ID {page_id}")
                    if action == "wait":
                        observed = await self._wait_for(page, selector, state, timeout)
                        return await self._success(action, page_id, page, observed)
                    if action == "inspect":
                        observed = await self._inspect(page, selector)
                        return await self._success(action, page_id, page, observed)

                    await page.bring_to_front()
                    await self._click(page, selector, timeout)
                    observed: dict[str, Any] = {"clicked": selector}
                    if result_selector:
                        observed["result"] = await self._wait_for(page, result_selector, result_state, timeout)
                    return await self._success(action, page_id, page, observed)
            except asyncio.TimeoutError:
                return self._error("TIMEOUT", f"{action} did not complete within {timeout} seconds")
            except BrowserActionError as exc:
                return self._error(exc.code, str(exc))
            except PlaywrightTimeoutError:
                return self._error("TIMEOUT", f"{action} did not reach the requested state within {timeout} seconds")
            except FileNotFoundError as exc:
                return self._error("CHROME_NOT_FOUND", str(exc))
            except RuntimeError as exc:
                return self._error("BROWSER_UNAVAILABLE", str(exc))
            except Exception as exc:
                return self._error("BROWSER_ACTION_FAILED", str(exc))

    async def refresh_sessions(self, urls: list[str]) -> None:
        """Refresh website sessions in temporary pages using the persistent profile."""
        failures: list[str] = []
        async with self._lock:
            await self._ensure_context()
            for url in urls:
                page = None
                try:
                    page = await self._context.new_page()
                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self._milliseconds(self._timeout_seconds),
                    )
                except Exception as exc:
                    failures.append(f"{url}: {exc}")
                finally:
                    if page is not None:
                        try:
                            await page.close()
                        except Exception as exc:
                            failures.append(f"{url}: failed to close temporary page: {exc}")

            # Close any lingering blank pages so the browser window doesn't
            # stay open with an orphaned about:blank tab after refresh.
            for page in self._context.pages:
                if not page.is_closed() and page.url in ("about:blank", ""):
                    try:
                        await page.close()
                    except Exception:
                        pass

        if failures:
            raise RuntimeError("; ".join(failures))

    async def close(self) -> None:
        """Close the persistent browser context and Playwright runtime."""
        async with self._lock:
            if self._context is not None:
                await self._context.close()
                self._context = None
                self._pages.clear()
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None

    async def _ensure_context(self) -> None:
        if self._context is not None and await self._is_context_alive():
            return
        if self._context is not None:
            await self._teardown_context()
        if async_playwright is None:
            raise RuntimeError("Playwright is not installed. Run ./install_env.sh to install the Python dependency.")
        if not self._executable_path.is_file():
            raise FileNotFoundError(f"Google Chrome not found at {self._executable_path}")
        self._playwright = await async_playwright().start()
        try:
            self._context = await self._playwright.chromium.launch_persistent_context(
                str(self._user_data_dir),
                executable_path=str(self._executable_path),
                headless=False,
                args=[
                    f"--profile-directory={self._profile}",
                    "--autoplay-policy=no-user-gesture-required",
                ],
                ignore_default_args=[
                    "--disable-component-update",
                    "--disable-extensions",
                    "--password-store=basic",
                    "--use-mock-keychain",
                ],
            )
        except Exception:
            await self._playwright.stop()
            self._playwright = None
            raise RuntimeError(
                f"Could not start Homebot Google Chrome profile at {self._user_data_dir}. "
                "Close any other Homebot instance using this profile and try again."
            ) from None
        for page in self._context.pages:
            self._page_id(page)

    async def _is_context_alive(self) -> bool:
        """Check whether the persistent browser context is still responsive."""
        try:
            # Accessing .pages on a closed browser raises TargetClosedError
            _ = self._context.pages
            return True
        except Exception:
            return False

    async def _teardown_context(self) -> None:
        """Clean up a dead browser context and its Playwright runtime."""
        try:
            if self._context is not None:
                await self._context.close()
        except Exception:
            pass
        self._context = None
        self._pages.clear()
        try:
            if self._playwright is not None:
                await self._playwright.stop()
        except Exception:
            pass
        self._playwright = None

    async def _open(self, url: str, timeout: float) -> str:
        target = _normal_url(url)
        matches = [page for page in self._context.pages if not page.is_closed() and _normal_url(page.url) == target]
        if len(matches) > 1:
            raise BrowserActionError("PAGE_AMBIGUOUS", f"Multiple Homebot pages already match {url}")
        if matches:
            page = matches[0]
        else:
            page = self._find_blank_page() or await self._context.new_page()
        page_id = self._page_id(page)
        await page.bring_to_front()
        if not matches:
            try:
                await page.goto(url, wait_until="commit", timeout=self._milliseconds(timeout))
            except BaseException:
                self._pages.pop(page_id, None)
                await page.close()
                raise
        return await self._success("open", page_id, page, {"ready_state": await page.evaluate("document.readyState")})

    def _get_page(self, page_id: str) -> Any | None:
        page = self._pages.get(page_id)
        return page if page is not None and not page.is_closed() else None

    def _find_blank_page(self) -> Any | None:
        """Return a reusable blank page (about:blank) or None."""
        for page in self._context.pages:
            if not page.is_closed() and page.url in ("about:blank", ""):
                return page
        return None

    def _page_id(self, page: Any) -> str:
        for page_id, known in self._pages.items():
            if known is page:
                return page_id
        page_id = f"page-{self._next_page_id}"
        self._next_page_id += 1
        self._pages[page_id] = page
        return page_id

    async def _wait_for(self, page: Any, selector: str, state: str, timeout: float) -> dict[str, Any]:
        if state == "hidden":
            locator = page.locator(selector)
            count = await locator.count()
            if count == 0:
                return {"hidden": True}
            if count != 1:
                raise BrowserActionError("SELECTOR_NOT_UNIQUE", f"{selector} matched {count} elements")
            await locator.wait_for(state="hidden", timeout=self._milliseconds(timeout))
            return {"hidden": True}

        locator = await self._wait_for_unique_locator(page, selector, timeout)
        if state == "playing":
            return await self._wait_for_playing(locator, timeout)
        if state in {"attached", "visible"}:
            await locator.wait_for(state=state, timeout=self._milliseconds(timeout))
        elif state == "enabled":
            await self._wait_for_enabled(locator, timeout)
        return await self._inspect_locator(locator)

    async def _wait_for_unique_locator(self, page: Any, selector: str, timeout: float) -> Any:
        locator = page.locator(selector)
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            count = await locator.count()
            if count == 1:
                return locator
            if asyncio.get_running_loop().time() >= deadline:
                reason = "did not match any elements" if count == 0 else f"matched {count} elements"
                raise BrowserActionError("SELECTOR_NOT_UNIQUE", f"{selector} {reason}")
            await asyncio.sleep(self._poll_interval_seconds)

    async def _wait_for_enabled(self, locator: Any, timeout: float) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            if await locator.is_visible() and await locator.is_enabled():
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise PlaywrightTimeoutError("Element did not become enabled")
            await asyncio.sleep(self._poll_interval_seconds)

    async def _wait_for_playing(self, locator: Any, timeout: float) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            before = await self._media_state(locator)
            if not before["paused"]:
                await asyncio.sleep(self._poll_interval_seconds)
                after = await self._media_state(locator)
                if not after["paused"] and after["current_time"] > before["current_time"]:
                    return after
            if asyncio.get_running_loop().time() >= deadline:
                raise PlaywrightTimeoutError("Media did not start playing")
            await asyncio.sleep(self._poll_interval_seconds)

    async def _inspect(self, page: Any, selector: str) -> dict[str, Any]:
        if not selector:
            return {"ready_state": await page.evaluate("document.readyState")}
        locator = await self._wait_for_unique_locator(page, selector, self._timeout_seconds)
        return await self._inspect_locator(locator)

    async def _click(self, page: Any, selector: str, timeout: float) -> None:
        locator = await self._wait_for_unique_locator(page, selector, timeout)
        await locator.click(timeout=self._milliseconds(timeout))

    async def _inspect_locator(self, locator: Any) -> dict[str, Any]:
        if await locator.count() != 1:
            raise BrowserActionError("SELECTOR_NOT_UNIQUE", "selector must match exactly one element")
        data = await locator.evaluate(
            """element => ({
                tag_name: element.tagName.toLowerCase(),
                text: (element.innerText || '').slice(0, 500),
                class_name: element.className || '',
                aria_label: element.getAttribute('aria-label'),
                disabled: Boolean(element.disabled) || element.getAttribute('aria-disabled') === 'true'
            })"""
        )
        data["visible"] = await locator.is_visible()
        data["enabled"] = await locator.is_enabled()
        if data["tag_name"] in {"audio", "video"}:
            data.update(await self._media_state(locator))
        return data

    async def _media_state(self, locator: Any) -> dict[str, Any]:
        return await locator.evaluate(
            "element => ({paused: element.paused, current_time: element.currentTime, ended: element.ended})"
        )

    @staticmethod
    def _milliseconds(seconds: float) -> int:
        return int(seconds * 1000)

    @staticmethod
    async def _success(action: str, page_id: str, page: Any, observed: dict[str, Any]) -> str:
        return json.dumps(
            {
                "ok": True,
                "action": action,
                "page_id": page_id,
                "url": page.url,
                "title": await page.title(),
                "observed": observed,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _error(code: str, detail: str) -> str:
        return "Error: " + json.dumps({"ok": False, "code": code, "detail": detail}, ensure_ascii=False)
