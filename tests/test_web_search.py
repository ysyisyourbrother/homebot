import json
import unittest
from unittest.mock import AsyncMock, patch

from homebot.agent.tools.web_search import WebSearchTool, create_web_search_provider
from homebot.cli.config import _configure_tools
from homebot.config.schema import Config


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
                    "content": "Open source home automation.",
                    "score": 0.98,
                }
            ],
        }

        result = json.loads(await WebSearchTool(provider).execute("Home Assistant"))

        provider.search.assert_awaited_once_with(
            "Home Assistant", max_results=5, search_depth="basic"
        )
        self.assertTrue(result["untrusted"])
        self.assertEqual(result["results"][0]["title"], "Home Assistant")

    def test_creates_tavily_provider(self) -> None:
        provider = create_web_search_provider("tavily", "test-key")

        self.assertEqual(provider.api_key, "test-key")


class WebSearchConfigCliTest(unittest.TestCase):
    def test_configures_tavily_search(self) -> None:
        config = Config()
        answers = iter(["", "yes", "tvly-test", "", "", "", "", ""])

        with patch("builtins.input", side_effect=lambda _prompt: next(answers)):
            _configure_tools(config)

        self.assertTrue(config.tools.web_search.enable)
        self.assertEqual(config.tools.web_search.provider, "tavily")
        self.assertEqual(config.tools.web_search.api_key, "tvly-test")


if __name__ == "__main__":
    unittest.main()
