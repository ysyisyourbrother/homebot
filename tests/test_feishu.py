import unittest
from unittest.mock import MagicMock

from homebot.bus.queue import MessageBus
from homebot.channels.feishu import FeishuChannel, _FeishuStreamBuf


class FeishuStreamingTest(unittest.IsolatedAsyncioTestCase):
    async def test_resuming_end_keeps_stream_buffer_until_final_end(self) -> None:
        channel = FeishuChannel.__new__(FeishuChannel)
        channel._client = MagicMock()
        channel._stream_bufs = {"user": _FeishuStreamBuf(text="未确认的回复")}
        channel._send_message_sync = MagicMock(return_value=True)

        await channel.send_delta("user", "", {"_stream_end": True, "_resuming": True})

        self.assertIn("user", channel._stream_bufs)
        channel._send_message_sync.assert_not_called()

        await channel.send_delta("user", "", {"_stream_end": True})

        self.assertNotIn("user", channel._stream_bufs)
        channel._send_message_sync.assert_called_once()


if __name__ == "__main__":
    unittest.main()
