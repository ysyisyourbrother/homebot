import unittest

from homebot.providers.openai_compat_provider import OpenAICompatProvider
from homebot.providers.registry import ProviderSpec


class OpenAICompatProviderResponseFormatTest(unittest.TestCase):
    def setUp(self) -> None:
        self.messages = [{"role": "user", "content": "你好"}]
        self.response_format = {"type": "json_object"}

    def test_deepseek_forwards_explicit_json_mode(self) -> None:
        provider = OpenAICompatProvider(
            spec=ProviderSpec(name="deepseek", keywords=("deepseek",), env_key="TEST_KEY"),
        )

        kwargs = provider._build_kwargs(
            self.messages, None, None, 256, 0.7, None, None, self.response_format
        )

        self.assertEqual(kwargs["response_format"], self.response_format)

    def test_non_deepseek_ignores_voice_json_mode(self) -> None:
        provider = OpenAICompatProvider(
            spec=ProviderSpec(name="dashscope", keywords=("qwen",), env_key="TEST_KEY"),
        )

        kwargs = provider._build_kwargs(
            self.messages, None, None, 256, 0.7, None, None, self.response_format
        )

        self.assertNotIn("response_format", kwargs)

    def test_default_request_has_no_response_format(self) -> None:
        provider = OpenAICompatProvider(
            spec=ProviderSpec(name="deepseek", keywords=("deepseek",), env_key="TEST_KEY"),
        )

        kwargs = provider._build_kwargs(self.messages, None, None, 256, 0.7, None, None, None)

        self.assertNotIn("response_format", kwargs)


if __name__ == "__main__":
    unittest.main()
