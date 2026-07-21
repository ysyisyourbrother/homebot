import unittest

from homebot.agent.hook import AgentHook, AgentHookContext
from homebot.agent.runner import AgentRunSpec, AgentRunner
from homebot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class FakeProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.kwargs: dict | None = None

    async def chat(self, messages, **kwargs):
        self.kwargs = kwargs
        return LLMResponse(content="完成")

    def get_default_model(self) -> str:
        return "fake"


class EmptyTools:
    def get_definitions(self):
        return []


class SequencedProvider(FakeProvider):
    def __init__(self, contents: list[str]) -> None:
        super().__init__()
        self.contents = iter(contents)

    async def chat(self, messages, **kwargs):
        return LLMResponse(content=next(self.contents))


class LengthThenFinalProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.responses = iter([
            LLMResponse(content='{"reply":"第一段', finish_reason="length"),
            LLMResponse(content='，第二段。","dialogue_state":"end"}'),
        ])

    async def chat(self, messages, **kwargs):
        return next(self.responses)


class ToolCallProvider(FakeProvider):
    async def chat(self, messages, **kwargs):
        return LLMResponse(
            content='{"reply":"正在查询。","dialogue_state":"continuous"}',
            tool_calls=[ToolCallRequest(id="call-1", name="lookup", arguments={})],
            finish_reason="tool_calls",
        )


class ToolProvider:
    def get_definitions(self):
        return [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]

    async def execute(self, name, arguments):
        return "查询结果"


class StreamingHook(AgentHook):
    def __init__(self) -> None:
        super().__init__()
        self.deltas: list[str] = []
        self.stream_ends: list[bool] = []

    def wants_streaming(self) -> bool:
        return True

    async def on_stream(self, context, delta: str) -> None:
        self.deltas.append(delta)

    async def on_stream_end(self, context, *, resuming: bool) -> None:
        self.stream_ends.append(resuming)


class AgentRunnerResponseFormatTest(unittest.IsolatedAsyncioTestCase):
    async def test_response_format_is_opt_in(self) -> None:
        provider = FakeProvider()
        runner = AgentRunner(provider)
        await runner.run(AgentRunSpec(
            initial_messages=[{"role": "user", "content": "你好"}],
            tools=EmptyTools(),
            model="fake",
            max_iterations=1,
            max_tool_result_chars=100,
            response_format={"type": "json_object"},
        ))

        self.assertEqual(provider.kwargs["response_format"], {"type": "json_object"})

    async def test_default_request_has_no_response_format(self) -> None:
        provider = FakeProvider()
        runner = AgentRunner(provider)
        spec = AgentRunSpec(
            initial_messages=[{"role": "user", "content": "你好"}],
            tools=EmptyTools(),
            model="fake",
            max_iterations=1,
            max_tool_result_chars=100,
        )

        kwargs = runner._build_request_kwargs(spec, spec.initial_messages, tools=[])

        self.assertNotIn("response_format", kwargs)
    async def test_empty_stream_response_stays_open_for_retry(self) -> None:
        provider = SequencedProvider(["", '{"reply":"请说时间。","dialogue_state":"continuous"}'])
        hook = StreamingHook()
        result = await AgentRunner(provider).run(AgentRunSpec(
            initial_messages=[{"role": "user", "content": "提醒我"}],
            tools=EmptyTools(),
            model="fake",
            max_iterations=2,
            max_tool_result_chars=100,
            hook=hook,
        ))

        self.assertEqual(result.final_content, '{"reply":"请说时间。","dialogue_state":"continuous"}')
        self.assertEqual(hook.deltas, ['{"reply":"请说时间。","dialogue_state":"continuous"}'])
        self.assertEqual(hook.stream_ends, [True, False])

    async def test_finalization_retry_remains_streaming(self) -> None:
        provider = SequencedProvider(["", "", '{"reply":"请说时间。","dialogue_state":"continuous"}'])
        hook = StreamingHook()
        result = await AgentRunner(provider).run(AgentRunSpec(
            initial_messages=[{"role": "user", "content": "提醒我"}],
            tools=EmptyTools(),
            model="fake",
            max_iterations=2,
            max_tool_result_chars=100,
            hook=hook,
        ))

        self.assertEqual(result.final_content, '{"reply":"请说时间。","dialogue_state":"continuous"}')
        self.assertEqual(hook.deltas, ['{"reply":"请说时间。","dialogue_state":"continuous"}'])
        self.assertEqual(hook.stream_ends, [True, True, False])
    async def test_length_recovery_keeps_voice_json_in_one_stream(self) -> None:
        hook = StreamingHook()
        result = await AgentRunner(LengthThenFinalProvider()).run(AgentRunSpec(
            initial_messages=[{"role": "user", "content": "说一句话"}],
            tools=EmptyTools(),
            model="fake",
            max_iterations=2,
            max_tool_result_chars=100,
            hook=hook,
            defer_stream_until_no_tools=True,
        ))

        self.assertEqual(
            result.final_content,
            '，第二段。","dialogue_state":"end"}',
        )
        self.assertEqual(
            hook.deltas,
            ['{"reply":"第一段', '，第二段。","dialogue_state":"end"}'],
        )
        self.assertEqual(hook.stream_ends, [True, False])

    async def test_tool_call_stream_is_not_forwarded_when_deferred(self) -> None:
        hook = StreamingHook()
        result = await AgentRunner(ToolCallProvider()).run(AgentRunSpec(
            initial_messages=[{"role": "user", "content": "查一下"}],
            tools=ToolProvider(),
            model="fake",
            max_iterations=1,
            max_tool_result_chars=100,
            hook=hook,
            defer_stream_until_no_tools=True,
        ))

        self.assertEqual(result.tools_used, ["lookup"])
        self.assertEqual(hook.deltas, [])
        self.assertEqual(hook.stream_ends, [True])

    async def test_final_stream_is_forwarded_when_deferred(self) -> None:
        hook = StreamingHook()
        result = await AgentRunner(FakeProvider()).run(AgentRunSpec(
            initial_messages=[{"role": "user", "content": "你好"}],
            tools=EmptyTools(),
            model="fake",
            max_iterations=1,
            max_tool_result_chars=100,
            hook=hook,
            defer_stream_until_no_tools=True,
        ))

        self.assertEqual(result.final_content, "完成")
        self.assertEqual(hook.deltas, ["完成"])
        self.assertEqual(hook.stream_ends, [False])


if __name__ == "__main__":
    unittest.main()
