import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import httpx

from homebot.agent.loop import AgentLoop
from homebot.agent.tools.web_search import (
    DeepSeekSearchProvider,
    WebSearchTool,
    create_web_search_provider,
)
from homebot.bus.queue import MessageBus
from homebot.cli.config import _configure_tools
from homebot.config.loader import _migrate_config
from homebot.config.schema import (
    BrowserConfig,
    Config,
    ExecToolConfig,
    ToolsConfig,
    WebSearchConfig,
    WebToolsConfig,
)
from homebot.providers.openai_compat_provider import OpenAICompatProvider
from homebot.providers.registry import find_by_name


class WebSearchToolTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_normalized_untrusted_results(self) -> None:
        provider = AsyncMock()
        provider.search.return_value = {
            "query": "Home Assistant",
            "answer": None,
            "results": [
                {
                    "title": "Home Assistant",
                    "url": "https://www.home-assistant.io/",
                    "summary": "Open source home automation.",
                    "score": 2.4,
                }
            ],
        }

        result = json.loads(await WebSearchTool(provider).execute("Home Assistant"))

        provider.search.assert_awaited_once_with("Home Assistant", max_results=5)
        self.assertTrue(result["untrusted"])
        self.assertEqual(result["results"][0]["title"], "Home Assistant")

    def test_description_documents_when_the_model_should_search(self) -> None:
        tool = WebSearchTool(AsyncMock())

        self.assertIn("搜索", tool.description)
        self.assertIn("current, recent", tool.description)
        self.assertIn("web_fetch", tool.description)

    def test_creates_deepseek_provider(self) -> None:
        provider = create_web_search_provider(
            "deepseek",
            "test-key",
            api_base="https://api.deepseek.com/v1",
        )

        self.assertIsInstance(provider, DeepSeekSearchProvider)
        self.assertEqual(provider.api_key, "test-key")
        self.assertEqual(provider.endpoint, "https://api.deepseek.com/v1/tools/search")


class DeepSeekSearchProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_posts_search_payload_and_normalizes_results(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "rerank_score": 2.4,
                            "title": "DeepSeek Search",
                            "url": "https://api-docs.deepseek.com/zh-cn/guides/search",
                            "snippet": "Search API",
                            "summary": "DeepSeek provides Search and Fetch tools.",
                            "content": "",
                            "site_name": "DeepSeek",
                            "site_icon": "https://example.com/favicon.ico",
                            "date": "2026-06-01T00:00:00+00:00",
                            "authority": 4,
                        }
                    ]
                },
            )

        provider = DeepSeekSearchProvider(
            "test-key",
            api_base="https://api.deepseek.com/v1",
            transport=httpx.MockTransport(handler),
            min_interval_seconds=0,
        )
        result = await provider.search("DeepSeek Search", max_results=5)

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].headers["authorization"], "Bearer test-key")
        self.assertEqual(
            json.loads(requests[0].content),
            {"query": "DeepSeek Search", "count": 5, "need_content": False},
        )
        self.assertEqual(result["results"][0]["score"], 2.4)
        self.assertEqual(result["results"][0]["authority"], 4)
        self.assertEqual(result["results"][0]["site_name"], "DeepSeek")

    async def test_retries_rate_limit_then_returns_success(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(429, headers={"retry-after": "0"})
            return httpx.Response(200, json={"results": []})

        provider = DeepSeekSearchProvider(
            "test-key",
            transport=httpx.MockTransport(handler),
            max_retries=1,
            min_interval_seconds=0,
        )
        result = await provider.search("rate limit", max_results=1)

        self.assertEqual(calls, 2)
        self.assertEqual(result["results"], [])

    async def test_does_not_retry_non_retryable_client_error(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                402,
                json={
                    "error": {
                        "message": "Insufficient Balance",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_request_error",
                    }
                },
            )

        provider = DeepSeekSearchProvider(
            "test-key",
            transport=httpx.MockTransport(handler),
            max_retries=2,
            min_interval_seconds=0,
        )

        with self.assertRaisesRegex(RuntimeError, "Insufficient Balance"):
            await provider.search("balance", max_results=1)
        self.assertEqual(calls, 1)


class AgentLoopSearchRegistrationTest(unittest.TestCase):
    def test_reuses_the_active_deepseek_provider_credentials(self) -> None:
        tools = ToolsConfig(
            web=WebToolsConfig(enable=False),
            web_search=WebSearchConfig(enable=True),
            exec=ExecToolConfig(enable=False),
            browser=BrowserConfig(enable=False),
        )
        provider = OpenAICompatProvider(
            api_key="shared-key",
            api_base="https://api.deepseek.com/v1",
            default_model="deepseek-flash",
            spec=find_by_name("deepseek"),
        )

        with TemporaryDirectory() as directory:
            agent = AgentLoop(
                bus=MessageBus(),
                provider=provider,
                workspace=Path(directory),
                model="deepseek-flash",
                web_config=tools.web,
                web_search_config=tools.web_search,
                exec_config=tools.exec,
                browser_config=tools.browser,
                tools_config=tools,
            )
            search_tool = agent.tools.get("web_search")

        self.assertIsInstance(search_tool, WebSearchTool)
        self.assertEqual(search_tool.provider.api_key, "shared-key")
        self.assertEqual(
            search_tool.provider.endpoint,
            "https://api.deepseek.com/v1/tools/search",
        )


class WebSearchConfigTest(unittest.TestCase):
    def test_configures_deepseek_search_without_a_second_key(self) -> None:
        config = Config()
        answers = iter([
            "2",     # 工具菜单 -> Web Search
            "yes",   # Web Search enable
            "no",    # Do not include full page content
            "0",     # 返回上级菜单
        ])

        with patch("builtins.input", side_effect=lambda _prompt: next(answers)):
            _configure_tools(config)

        self.assertTrue(config.tools.web_search.enable)
        self.assertEqual(config.tools.web_search.provider, "deepseek")
        self.assertFalse(config.tools.web_search.need_content)
        self.assertFalse(hasattr(config.tools.web_search, "api_key"))

    def test_migrates_tavily_configuration_to_deepseek(self) -> None:
        data = {
            "tools": {
                "webSearch": {
                    "enable": True,
                    "provider": "tavily",
                    "apiKey": "tvly-old-key",
                }
            }
        }

        migrated = _migrate_config(data)
        search = migrated["tools"]["webSearch"]

        self.assertEqual(search["provider"], "deepseek")
        self.assertNotIn("apiKey", search)
        self.assertNotIn("api_key", search)

    def test_migrates_snake_case_tavily_configuration(self) -> None:
        data = {
            "tools": {
                "web_search": {
                    "enable": True,
                    "provider": "tavily",
                    "api_key": "tvly-old-key",
                }
            }
        }

        migrated = _migrate_config(data)
        search = migrated["tools"]["web_search"]

        self.assertEqual(search["provider"], "deepseek")
        self.assertNotIn("api_key", search)


if __name__ == "__main__":
    unittest.main()
